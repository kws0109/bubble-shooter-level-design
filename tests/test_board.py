"""Sanity tests for the hex board.

Run: python -m tests.test_board
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bubble.board import Board, EMPTY, offset_to_axial, axial_to_offset


def test_axial_roundtrip() -> None:
    for row in range(10):
        for col in range(10):
            q, r = offset_to_axial(row, col)
            r2, c2 = axial_to_offset(q, r)
            assert (row, col) == (r2, c2), f"roundtrip failed at {(row, col)}"


def test_neighbors_count() -> None:
    b = Board(rows=8, cols=8, num_colors=4, shots_remaining=10)
    # Interior cell: should have 6 neighbors.
    assert len(list(b.neighbors(4, 4))) == 6
    # Corner: should have 2 or 3.
    n = len(list(b.neighbors(0, 0)))
    assert 2 <= n <= 3, f"corner neighbors: {n}"


def test_cluster_and_floating() -> None:
    b = Board(rows=5, cols=5, num_colors=3, shots_remaining=5)
    # Build a small attached cluster on the ceiling row.
    b.set(0, 0, 1); b.set(0, 1, 1); b.set(0, 2, 1)
    # Build an isolated cluster lower down (no path to ceiling).
    b.set(3, 0, 2); b.set(3, 1, 2)

    cluster_top = b.same_color_cluster(0, 0)
    assert cluster_top == {(0, 0), (0, 1), (0, 2)}

    floating = b.floating_cells()
    assert (3, 0) in floating and (3, 1) in floating
    assert (0, 0) not in floating


def test_serialization_roundtrip() -> None:
    b = Board(rows=4, cols=4, num_colors=3, shots_remaining=8, seed=42)
    b.set(0, 0, 1); b.set(1, 1, 2); b.set(2, 2, 3)
    text = b.to_json()
    b2 = Board.from_json(text)
    assert b2.cells == b.cells
    assert b2.seed == 42


def main() -> None:
    tests = [
        test_axial_roundtrip,
        test_neighbors_count,
        test_cluster_and_floating,
        test_serialization_roundtrip,
    ]
    for t in tests:
        t()
        print(f"  PASS  {t.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    main()
