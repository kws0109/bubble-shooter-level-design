"""Two-stage bubble level generator (ADR 0004).

Stage 1 — `seed_and_grow`
    Place K seeds with a minimum-distance constraint (poisson-disk-style),
    assign each a random color, then grow each seed by BFS into adjacent
    empty cells until the target density is reached. Produces boards with
    natural-looking clusters rather than salt-and-pepper noise.

Stage 2 — `evolve_to_target`
    (1+1) evolution strategy. Each generation mutates a single cell
    (recolor / place / clear) and keeps the change only if the weighted
    distance to the target feature vector decreases. Cheap, deterministic
    given a seed, and easy to extend with EAC fitness once the bot solver
    is built.

Top-level entry: `generate_level(spec, seed)` runs both stages.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .board import Board, EMPTY
from .features import FeatureVector, compute_features


# --- specification ---------------------------------------------------------

@dataclass(frozen=True)
class LevelSpec:
    """Designer-facing knobs for one level.

    `target_features` is partial: only specified keys participate in the
    fitness. Unspecified keys are free. `weights` lets the designer say
    'I care more about chain depth than density.'

    `symmetry_axis` controls strict mirroring:
        "none"        - no symmetry
        "horizontal"  - left-right mirror (cols flipped)
        "vertical"    - top-bottom mirror (rows flipped)
        "both"        - 4-fold (horizontal + vertical)

    When set, EVERY placement (Stage 1 grow, Stage 2 mutate) is applied
    to the cell AND all its mirror twins with the same color. This makes
    both position and color provably symmetric.

    The legacy `symmetric: bool` flag is mapped to "horizontal" if axis
    is "none".
    """
    rows: int = 10
    cols: int = 10
    num_colors: int = 4
    shots_remaining: int = 12
    target_density: float = 0.5
    num_seeds: int = 6
    target_features: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    max_generations: int = 800
    level_index: int | None = None
    symmetric: bool = False
    symmetry_axis: str = "none"
    paired_mutation_rate: float = 1.0  # kept for compat; ignored under strict axis

    @property
    def effective_axis(self) -> str:
        """Resolve `symmetric=True` legacy flag into an axis string."""
        if self.symmetry_axis != "none":
            return self.symmetry_axis
        return "horizontal" if self.symmetric else "none"

    @property
    def total_cells(self) -> int:
        # Alternating-width layout (ADR 0009): even rows wide, odd narrow.
        wide = (self.rows + 1) // 2
        narrow = self.rows // 2
        return wide * self.cols + narrow * (self.cols - 1)


def colors_for_level(level_index: int, rng: random.Random) -> int:
    """ADR 0006 progression: L1-10 -> 2|3, ..., L41-50 -> 6|7, L51+ fixed.

    `level_index` is 0-based.
    """
    bucket = min(level_index // 10, 4)
    return rng.randint(2 + bucket, 3 + bucket)


# --- stage 1: seed and grow ------------------------------------------------

def _hex_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Approximate hex distance via offset coordinates.

    Good enough for seed placement spacing — we don't need exact axial
    distance here, only a 'spread them out' heuristic.
    """
    dr = abs(a[0] - b[0])
    dc = abs(a[1] - b[1])
    return max(dr, dc, dr + dc - dr // 2)


def _place_seeds(rows: int, cols: int, k: int, rng: random.Random,
                 min_distance: int) -> list[tuple[int, int]]:
    """Reject-sample seed positions with a min-distance constraint."""
    candidates = [(r, c) for r in range(rows) for c in range(cols)]
    rng.shuffle(candidates)
    seeds: list[tuple[int, int]] = []
    for pos in candidates:
        if len(seeds) >= k:
            break
        if all(_hex_distance(pos, s) >= min_distance for s in seeds):
            seeds.append(pos)
    return seeds


def _mirror_positions(board: Board, r: int, c: int,
                      axis: str) -> tuple[tuple[int, int], ...]:
    """All cells equivalent to (r, c) under the given symmetry axis,
    including (r, c) itself.

    Width-aware: for horizontal mirror the mirror column is computed as
    `row_width(r) - 1 - c`. With alternating widths (ADR 0009) the visual
    mirror axis sits at x = (cols - 1) / 2 in every row, so the resulting
    layout is symmetric *visually* — not just by index.
    """
    if axis == "none":
        return ((r, c),)
    out: set[tuple[int, int]] = {(r, c)}
    if axis in ("horizontal", "both"):
        out.add((r, board.row_width(r) - 1 - c))
    if axis in ("vertical", "both"):
        # Vertical is unsupported under the ceiling-attachment invariant,
        # but the math is kept for future radial/180-degree symmetry.
        out.add((board.rows - 1 - r, c))
    if axis == "both":
        nr = board.rows - 1 - r
        out.add((nr, board.row_width(nr) - 1 - c))
    return tuple(out)


def _canonical_region(rows: int, cols: int, axis: str) -> list[tuple[int, int]]:
    """Cells in the canonical (non-mirrored) region. Each canonical cell
    is the lexicographically smallest among its mirror equivalents.
    """
    points: list[tuple[int, int]] = []
    for r in range(rows):
        for c in range(cols):
            equiv = _mirror_positions(r, c, rows, cols, axis)
            if (r, c) == min(equiv):
                points.append((r, c))
    return points


def _place_anchored_seeds(spec: LevelSpec, rng: random.Random,
                          axis: str) -> list[tuple[int, int]]:
    """Place seeds on row 0 only (ceiling-anchored).

    Under horizontal mirror, only canonical columns 0..(cols+1)//2 - 1
    are used; mirrors are added by `_set_mirrored` during growth.
    Anchoring to row 0 guarantees that every grown cell, reached via
    BFS from a seed, has a path back to the ceiling — therefore no
    floating clusters in the final board.
    """
    if axis == "horizontal":
        max_col_excl = (spec.cols + 1) // 2
        canonical_target = max(1, (spec.num_seeds + 1) // 2)
    else:
        max_col_excl = spec.cols
        canonical_target = max(1, spec.num_seeds)

    min_dist = max(2, max_col_excl // max(1, canonical_target))
    cols = list(range(max_col_excl))
    rng.shuffle(cols)
    placed: list[int] = []
    for c in cols:
        if len(placed) >= canonical_target:
            break
        if all(abs(c - p) >= min_dist for p in placed):
            placed.append(c)
    return [(0, c) for c in placed]


def _set_mirrored(board: Board, r: int, c: int, color: int,
                  axis: str) -> tuple[tuple[int, int], ...]:
    """Set color at (r, c) and all mirror positions. Returns positions touched."""
    positions = _mirror_positions(board, r, c, axis)
    for mr, mc in positions:
        board.set(mr, mc, color)
    return positions


def _seed_colors(num_seeds: int, num_colors: int,
                 rng: random.Random) -> list[int]:
    """Assign colors to seeds using a shuffled cycle.

    Guarantees that the first `min(num_seeds, num_colors)` seeds have
    distinct colors — without this, sampling colors with replacement
    causes high-color levels to silently use very few colors when the
    canonical seed region is small (ADR 0009 narrows row 0 canonical
    region to (cols+1)//2 cells).
    """
    bag = list(range(1, num_colors + 1))
    rng.shuffle(bag)
    out: list[int] = []
    for i in range(num_seeds):
        if i > 0 and i % num_colors == 0:
            rng.shuffle(bag)
        out.append(bag[i % num_colors])
    return out


def _ensure_all_colors_present(board: Board, num_colors: int,
                               axis: str, rng: random.Random) -> int:
    """Inject any missing colors by recoloring cells of the most abundant
    color, in a way that never zeros out an existing color.

    Background: when the canonical seed region (row 0 left half) is too
    small to host one seed per color, Stage 1 cannot produce all colors;
    Stage 2 evolution may also drop colors that no fitness term defends.
    Without this step, a level marked `num_colors=7` in the spec might
    actually display only 3 colors, contradicting the rationale.

    Algorithm: for each missing color, pick a cell from the *most
    abundant* color whose mirror set wouldn't push any color to zero,
    recolor it (and its mirror twins) to the missing color.
    """
    from collections import Counter

    counts = Counter(board.get(r, c) for r, c in board.occupied_cells())
    missing = [k for k in range(1, num_colors + 1) if counts.get(k, 0) == 0]
    if not missing:
        return 0
    injected = 0
    used: set[tuple[int, int]] = set()
    for new_color in missing:
        # Sort live colors by descending count so we recolor abundant
        # cells first, preserving rare colors.
        live_colors = sorted(
            (c for c in counts if counts[c] > 0),
            key=lambda c: -counts[c],
        )
        applied = False
        for src_color in live_colors:
            cells = [
                (r, c) for r, c in board.occupied_cells()
                if board.get(r, c) == src_color and (r, c) not in used
            ]
            rng.shuffle(cells)
            for r, c in cells:
                mirror = _mirror_positions(board, r, c, axis)
                if any(m in used for m in mirror):
                    continue
                # Count how many cells in the mirror set currently hold
                # src_color — recoloring will remove that many.
                n_src_in_mirror = sum(1 for m in mirror
                                       if board.get(*m) == src_color)
                if counts[src_color] - n_src_in_mirror < 1:
                    continue  # would zero out src_color
                for mr, mc in mirror:
                    cur = board.get(mr, mc)
                    board.set(mr, mc, new_color)
                    counts[cur] -= 1
                    counts[new_color] = counts.get(new_color, 0) + 1
                    used.add((mr, mc))
                applied = True
                break
            if applied:
                break
        if not applied:
            break  # no safe injection possible — exit
        injected += 1
    return injected


def seed_and_grow(spec: LevelSpec, rng: random.Random) -> Board:
    """Stage 1. Seeds are anchored to row 0; mirror placements share color.

    All grown cells are guaranteed connected to the ceiling because
    growth proceeds via adjacency from a row-0 anchor. A defensive
    `drop_floating()` is applied at the end to enforce the invariant
    even if future code paths break the assumption.
    """
    board = Board(
        rows=spec.rows, cols=spec.cols,
        num_colors=spec.num_colors,
        shots_remaining=spec.shots_remaining,
    )
    target_count = int(board.total_cells() * spec.target_density)
    axis = spec.effective_axis

    seeds = _place_anchored_seeds(spec, rng, axis)
    if not seeds:
        return board
    colors = _seed_colors(len(seeds), spec.num_colors, rng)

    placed = 0
    frontiers: list[list[tuple[int, int]]] = []
    for i, (r, c) in enumerate(seeds):
        positions = _set_mirrored(board, r, c, colors[i], axis)
        placed += len(positions)
        f: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for p in positions:
            for n in board.neighbors(*p):
                if board.is_empty(*n) and n not in seen:
                    seen.add(n)
                    f.append(n)
        frontiers.append(f)

    while placed < target_count:
        active = [i for i, f in enumerate(frontiers) if f]
        if not active:
            break
        idx = rng.choice(active)
        cell = frontiers[idx].pop(rng.randrange(len(frontiers[idx])))
        if not board.is_empty(*cell):
            continue
        positions = _set_mirrored(board, *cell, colors[idx], axis)
        placed += len(positions)
        for p in positions:
            for n in board.neighbors(*p):
                if board.is_empty(*n) and n not in frontiers[idx]:
                    frontiers[idx].append(n)

    board.drop_floating()
    _ensure_all_colors_present(board, spec.num_colors, axis, rng)
    return board


# --- stage 2: (1+1) evolution ----------------------------------------------

def _feature_distance(features: FeatureVector,
                      target: dict[str, float],
                      weights: dict[str, float]) -> float:
    if not target:
        return 0.0
    fv = features.as_dict()
    total = 0.0
    for key, goal in target.items():
        w = weights.get(key, 1.0)
        diff = fv[key] - goal
        total += w * diff * diff
    return total


def _decide_new_color(board: Board, r: int, c: int,
                      rng: random.Random) -> int:
    old = board.cells[r][c]
    roll = rng.random()
    if old != EMPTY and roll < 0.85:
        choices = [k for k in range(1, board.num_colors + 1) if k != old]
        return rng.choice(choices) if choices else old
    if old == EMPTY and roll < 0.7:
        if r == 0 or any(True for _ in board.occupied_neighbors(r, c)):
            return rng.randint(1, board.num_colors)
        return EMPTY
    return EMPTY if old != EMPTY else rng.randint(1, board.num_colors)


def _mutate(board: Board, rng: random.Random, axis: str = "none") -> None:
    """Mutate one cell (with mirrors). Drop any cells the change detached."""
    r = rng.randrange(board.rows)
    c = rng.randrange(board.row_width(r))
    new = _decide_new_color(board, r, c, rng)
    if axis == "none":
        board.set(r, c, new)
    else:
        for mr, mc in _mirror_positions(board, r, c, axis):
            board.set(mr, mc, new)
    # Clearing a load-bearing cell can detach others — drop them so the
    # board always represents a playable post-physics state.
    board.drop_floating()


def evolve_to_target(board: Board, spec: LevelSpec,
                     rng: random.Random,
                     max_generations: int | None = None) -> tuple[Board, list[float]]:
    """(1+1)-ES. Returns (best_board, fitness_history)."""
    if not spec.target_features:
        return board, []

    best = board.clone()
    best_fit = _feature_distance(compute_features(best),
                                 spec.target_features, spec.weights)
    history: list[float] = [best_fit]
    gens = max_generations if max_generations is not None else spec.max_generations
    axis = spec.effective_axis

    for _ in range(gens):
        candidate = best.clone()
        _mutate(candidate, rng, axis=axis)
        fit = _feature_distance(compute_features(candidate),
                                spec.target_features, spec.weights)
        if fit < best_fit:
            best, best_fit = candidate, fit
        history.append(best_fit)
        if best_fit < 1e-6:
            break
    return best, history


# --- top-level entry -------------------------------------------------------

def generate_level(spec: LevelSpec, seed: int) -> tuple[Board, list[float]]:
    """Run both stages with a seed for full reproducibility."""
    rng = random.Random(seed)
    board = seed_and_grow(spec, rng)
    board.seed = seed
    final, history = evolve_to_target(board, spec, rng)
    # Stage 2 may have evolved away from spec.num_colors. Re-inject any
    # missing colors so the saved board matches the rationale's claimed
    # color count.
    _ensure_all_colors_present(final, spec.num_colors, spec.effective_axis, rng)
    final.seed = seed
    return final, history
