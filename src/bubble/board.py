"""Hexagonal bubble shooter board.

Layout (ADR 0009)
-----------------
Standard pointy-top hex with **alternating row widths**, matching the
visual layout of Bubble Pop Origin / Frozen Bubble:

- Row 0 (and every even index): width = `cols`     (e.g. 10)
- Row 1 (and every odd  index): width = `cols - 1` (e.g.  9)

Odd rows are visually shifted half a cell to the right and contain one
fewer cell, so all rows fit inside the same rectangular bounding box and
the vertical mirror axis sits at x = (cols - 1) / 2 for every row.

Cells are stored as `cells[r][c]` with `c` in `0..row_width(r)-1`. A cell
holds either a color int (1..N) or `EMPTY` (0).

Adjacency
---------
Each cell has up to 6 neighbors, computed by direction tables that depend
on whether the row is wide (even index) or narrow (odd index). No axial
conversion is required.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable, Iterator

EMPTY: int = 0


@dataclass(frozen=True)
class ShotResult:
    """Outcome of one simulated shot.

    `matched` are bubbles popped because they formed a same-color cluster
    of >= min_match. `floating` are subsequently dropped because they lost
    their connection to the ceiling. `popped` is the total eliminated.
    """
    board_after: "Board"
    landed_at: tuple[int, int]
    color: int
    matched: frozenset[tuple[int, int]] | set[tuple[int, int]]
    floating: frozenset[tuple[int, int]] | set[tuple[int, int]]

    @property
    def popped(self) -> int:
        return len(self.matched) + len(self.floating)

    @property
    def is_match(self) -> bool:
        return bool(self.matched)


# --- coordinate conversion (legacy) ---------------------------------------
# These pure-math helpers map between offset (r, c) and axial (q, r) and
# remain exported for tests and external callers. The Board class itself
# no longer uses them — neighbor lookup is direct via the directional
# tables below.

def offset_to_axial(row: int, col: int) -> tuple[int, int]:
    q = col - (row - (row & 1)) // 2
    r = row
    return q, r


def axial_to_offset(q: int, r: int) -> tuple[int, int]:
    row = r
    col = q + (r - (r & 1)) // 2
    return row, col


# Direction tables for alternating-width hex (ADR 0009).
#   Wide row (even index, width = cols):
#     same row  : (0, ±1)
#     narrow row above/below: (±1, -1) and (±1, 0)
#   Narrow row (odd index, width = cols - 1):
#     same row  : (0, ±1)
#     wide row above/below: (±1, 0) and (±1, +1)
_DIRS_WIDE_ROW: tuple[tuple[int, int], ...] = (
    (0, -1), (0, +1),
    (-1, -1), (-1, 0),
    (+1, -1), (+1, 0),
)
_DIRS_NARROW_ROW: tuple[tuple[int, int], ...] = (
    (0, -1), (0, +1),
    (-1, 0), (-1, +1),
    (+1, 0), (+1, +1),
)


# --- board -----------------------------------------------------------------

@dataclass
class Board:
    """Mutable bubble board.

    `cells[row][col]` holds a color int (1..num_colors) or EMPTY.
    """

    rows: int
    cols: int
    num_colors: int
    shots_remaining: int
    cells: list[list[int]] = field(default_factory=list)
    seed: int | None = None

    def __post_init__(self) -> None:
        if not self.cells:
            self.cells = [
                [EMPTY] * self.row_width(r) for r in range(self.rows)
            ]

    # --- layout (alternating widths, ADR 0009) ----------------------------

    def row_width(self, row: int) -> int:
        """Width of a row. Even-index rows are wide, odd-index narrow."""
        return self.cols if (row & 1) == 0 else self.cols - 1

    # --- basic access ------------------------------------------------------

    def in_bounds(self, row: int, col: int) -> bool:
        if not (0 <= row < self.rows):
            return False
        return 0 <= col < self.row_width(row)

    def get(self, row: int, col: int) -> int:
        return self.cells[row][col]

    def set(self, row: int, col: int, color: int) -> None:
        self.cells[row][col] = color

    def is_empty(self, row: int, col: int) -> bool:
        return self.cells[row][col] == EMPTY

    def occupied_cells(self) -> Iterator[tuple[int, int]]:
        for r in range(self.rows):
            for c in range(len(self.cells[r])):
                if self.cells[r][c] != EMPTY:
                    yield r, c

    def occupied_count(self) -> int:
        return sum(1 for _ in self.occupied_cells())

    def total_cells(self) -> int:
        return sum(self.row_width(r) for r in range(self.rows))

    # --- adjacency (direct via directional tables) ------------------------

    def neighbors(self, row: int, col: int) -> Iterator[tuple[int, int]]:
        dirs = _DIRS_WIDE_ROW if (row & 1) == 0 else _DIRS_NARROW_ROW
        for dr, dc in dirs:
            nr, nc = row + dr, col + dc
            if self.in_bounds(nr, nc):
                yield nr, nc

    def occupied_neighbors(self, row: int, col: int) -> Iterator[tuple[int, int]]:
        for nr, nc in self.neighbors(row, col):
            if self.cells[nr][nc] != EMPTY:
                yield nr, nc

    # --- cluster / connectivity --------------------------------------------

    def same_color_cluster(self, row: int, col: int) -> set[tuple[int, int]]:
        """BFS over same-color connected component including (row, col)."""
        color = self.cells[row][col]
        if color == EMPTY:
            return set()
        seen: set[tuple[int, int]] = {(row, col)}
        stack: list[tuple[int, int]] = [(row, col)]
        while stack:
            r, c = stack.pop()
            for nr, nc in self.occupied_neighbors(r, c):
                if (nr, nc) not in seen and self.cells[nr][nc] == color:
                    seen.add((nr, nc))
                    stack.append((nr, nc))
        return seen

    def all_clusters(self) -> list[set[tuple[int, int]]]:
        seen: set[tuple[int, int]] = set()
        clusters: list[set[tuple[int, int]]] = []
        for rc in self.occupied_cells():
            if rc in seen:
                continue
            cluster = self.same_color_cluster(*rc)
            seen |= cluster
            clusters.append(cluster)
        return clusters

    def attached_to_ceiling(self) -> set[tuple[int, int]]:
        """All occupied cells reachable from row 0 through occupied neighbors."""
        seen: set[tuple[int, int]] = set()
        stack: list[tuple[int, int]] = []
        for c in range(self.cols):
            if self.cells[0][c] != EMPTY:
                seen.add((0, c))
                stack.append((0, c))
        while stack:
            r, c = stack.pop()
            for nr, nc in self.occupied_neighbors(r, c):
                if (nr, nc) not in seen:
                    seen.add((nr, nc))
                    stack.append((nr, nc))
        return seen

    def floating_cells(self) -> set[tuple[int, int]]:
        """Occupied cells not attached to the ceiling — these would fall."""
        attached = self.attached_to_ceiling()
        return {rc for rc in self.occupied_cells() if rc not in attached}

    def drop_floating(self) -> int:
        """Clear all floating cells in place. Returns the count dropped.

        A bubble shooter level must never display floating bubbles in its
        initial state — they would fall the moment the game starts. This
        method enforces that invariant and is called after every Stage 1
        completion and Stage 2 mutation.
        """
        floating = self.floating_cells()
        for r, c in floating:
            self.cells[r][c] = EMPTY
        return len(floating)

    # --- valid shot positions ---------------------------------------------

    def valid_shot_positions(self) -> list[tuple[int, int]]:
        """Empty cells where a shot could plausibly land.

        A shot lands at an empty cell that is either on row 0 (ceiling) or
        adjacent to an occupied cell. This filters out unreachable interior
        empties — important because a real shooter cannot "tunnel" past
        existing bubbles.
        """
        positions: list[tuple[int, int]] = []
        for r in range(self.rows):
            for c in range(self.row_width(r)):
                if self.cells[r][c] != EMPTY:
                    continue
                if r == 0 or any(True for _ in self.occupied_neighbors(r, c)):
                    positions.append((r, c))
        return positions

    # --- shot simulation ---------------------------------------------------

    def simulate_shot(self, row: int, col: int, color: int,
                      min_match: int = 3) -> "ShotResult":
        """Place `color` at (row, col) on a clone and resolve the shot.

        Returns the matched/floating sets and a popped count. The original
        board is not modified — callers clone or replay as needed.

        Raises ValueError if the target cell is non-empty.
        """
        if self.cells[row][col] != EMPTY:
            raise ValueError(f"shot target ({row},{col}) is not empty")

        b = self.clone()
        b.set(row, col, color)

        cluster = b.same_color_cluster(row, col)
        matched: set[tuple[int, int]] = set()
        if len(cluster) >= min_match:
            matched = cluster
            for r, c in matched:
                b.set(r, c, EMPTY)

        floating: set[tuple[int, int]] = set()
        if matched:
            floating = b.floating_cells()
            for r, c in floating:
                b.set(r, c, EMPTY)

        return ShotResult(
            board_after=b,
            landed_at=(row, col),
            color=color,
            matched=matched,
            floating=floating,
        )

    # --- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "rows": self.rows,
            "cols": self.cols,
            "num_colors": self.num_colors,
            "shots_remaining": self.shots_remaining,
            "seed": self.seed,
            "cells": self.cells,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Board":
        return cls(
            rows=data["rows"],
            cols=data["cols"],
            num_colors=data["num_colors"],
            shots_remaining=data["shots_remaining"],
            seed=data.get("seed"),
            cells=[row[:] for row in data["cells"]],
        )

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, text: str) -> "Board":
        return cls.from_dict(json.loads(text))

    def clone(self) -> "Board":
        return Board.from_dict(self.to_dict())

    # --- pretty print (debug) ---------------------------------------------

    def render_ascii(self) -> str:
        """ASCII render. Odd rows indented one char (half-cell shift)."""
        symbols = " 123456789ABCDEF"
        lines: list[str] = []
        for r in range(self.rows):
            indent = " " if (r & 1) else ""
            row_chars = [symbols[c] if 0 <= c < len(symbols) else "?"
                         for c in self.cells[r]]
            lines.append(indent + " ".join(row_chars))
        return "\n".join(lines)


# --- factory helpers -------------------------------------------------------

def empty_board(rows: int, cols: int, num_colors: int,
                shots_remaining: int, seed: int | None = None) -> Board:
    return Board(
        rows=rows,
        cols=cols,
        num_colors=num_colors,
        shots_remaining=shots_remaining,
        seed=seed,
    )
