"""Static structural feature vector for a bubble board.

Implements the 6 dimensions decided in ADR 0003:
    1. color_entropy       Shannon entropy of color distribution.
    2. max_chain_depth     Largest single-shot pop (matched + floating)
                           across all (position, color) trials.
    3. avg_cluster_size    Mean size of same-color connected components.
    4. floating_potential  Mean popped count across all shot trials.
                           Captures both chain power and structural fragility.
    5. density             Occupied / total cells.
    6. shot_pressure       shots_remaining / occupied_count.

Trade-offs (per ADR 0003 + ADR-lite for shot simulation method):
    - Dimensions 2 and 4 use the *full simulation* approach (Option A):
      every (valid empty cell, color) is tried via `Board.simulate_shot`.
      Cost is O(P x C x BFS) where P = valid shot positions, C = colors.
      For boards <= 12x12 with <= 6 colors this stays well under a second.
    - The same primitive is reused by the solver, so the cost amortizes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .board import Board, EMPTY


@dataclass(frozen=True)
class FeatureVector:
    color_entropy: float
    max_chain_depth: int
    avg_cluster_size: float
    floating_potential: float
    density: float
    shot_pressure: float

    def as_dict(self) -> dict[str, float]:
        return {
            "color_entropy": self.color_entropy,
            "max_chain_depth": float(self.max_chain_depth),
            "avg_cluster_size": self.avg_cluster_size,
            "floating_potential": self.floating_potential,
            "density": self.density,
            "shot_pressure": self.shot_pressure,
        }

    @staticmethod
    def keys() -> tuple[str, ...]:
        return (
            "color_entropy",
            "max_chain_depth",
            "avg_cluster_size",
            "floating_potential",
            "density",
            "shot_pressure",
        )


# --- dimension implementations --------------------------------------------

def color_entropy(board: Board) -> float:
    counts: dict[int, int] = {}
    total = 0
    for r, c in board.occupied_cells():
        color = board.cells[r][c]
        counts[color] = counts.get(color, 0) + 1
        total += 1
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy -= p * math.log2(p)
    return entropy


def avg_cluster_size(board: Board) -> float:
    clusters = board.all_clusters()
    if not clusters:
        return 0.0
    return sum(len(c) for c in clusters) / len(clusters)


def density(board: Board) -> float:
    total = board.total_cells()
    return board.occupied_count() / total if total else 0.0


def shot_pressure(board: Board) -> float:
    occupied = board.occupied_count()
    if occupied == 0:
        return 0.0
    return board.shots_remaining / occupied


def _simulate_all_shots(board: Board) -> list[int]:
    """Pop counts from every (valid_position x color) trial.

    Empty list if there are no valid shot positions. Trials with zero pops
    (no match) are still recorded as 0 — they are part of the difficulty
    signal: many wasted-shot positions = harder.
    """
    positions = board.valid_shot_positions()
    if not positions:
        return []
    pops: list[int] = []
    for row, col in positions:
        for color in range(1, board.num_colors + 1):
            result = board.simulate_shot(row, col, color)
            pops.append(result.popped)
    return pops


def max_chain_depth(board: Board, _pops: list[int] | None = None) -> int:
    pops = _pops if _pops is not None else _simulate_all_shots(board)
    return max(pops) if pops else 0


def floating_potential(board: Board, _pops: list[int] | None = None) -> float:
    pops = _pops if _pops is not None else _simulate_all_shots(board)
    if not pops:
        return 0.0
    return sum(pops) / len(pops)


# --- aggregate ------------------------------------------------------------

def compute_features(board: Board) -> FeatureVector:
    """Compute all 6 dimensions, simulating shots only once."""
    pops = _simulate_all_shots(board)
    return FeatureVector(
        color_entropy=color_entropy(board),
        max_chain_depth=max(pops) if pops else 0,
        avg_cluster_size=avg_cluster_size(board),
        floating_potential=(sum(pops) / len(pops)) if pops else 0.0,
        density=density(board),
        shot_pressure=shot_pressure(board),
    )
