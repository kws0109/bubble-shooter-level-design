"""Invariant: every generated level has zero floating cells.

A bubble shooter level must always start with all bubbles attached to
the ceiling — otherwise the game would auto-drop them on shot 1 and the
displayed level would not match the playable state.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bubble.board import Board
from bubble.generator import LevelSpec, generate_level


def _spec(level_index: int, axis: str) -> LevelSpec:
    return LevelSpec(
        rows=8, cols=10,
        num_colors=4,
        shots_remaining=16,
        target_density=0.5,
        num_seeds=6,
        target_features={
            "color_entropy": 1.6,
            "max_chain_depth": 6,
            "floating_potential": 0.8,
            "density": 0.5,
        },
        weights={"color_entropy": 1.0, "max_chain_depth": 0.5,
                 "floating_potential": 1.0, "density": 2.0},
        max_generations=400,
        level_index=level_index,
        symmetry_axis=axis,
    )


def test_horizontal_symmetric_levels_have_no_floating() -> None:
    for seed in (1, 7, 13, 31, 99):
        board, _ = generate_level(_spec(level_index=10, axis="horizontal"), seed=seed)
        floating = board.floating_cells()
        assert not floating, (
            f"horizontal seed={seed}: {len(floating)} floating cell(s) — "
            f"{sorted(floating)[:6]}"
        )


def test_asymmetric_levels_have_no_floating() -> None:
    for seed in (2, 8, 14, 32, 100):
        board, _ = generate_level(_spec(level_index=5, axis="none"), seed=seed)
        floating = board.floating_cells()
        assert not floating, (
            f"none seed={seed}: {len(floating)} floating cell(s)"
        )


def test_horizontal_symmetric_layout_is_actually_symmetric() -> None:
    board, _ = generate_level(_spec(level_index=20, axis="horizontal"), seed=42)
    for r in range(board.rows):
        w = board.row_width(r)
        for c in range(w):
            mc = w - 1 - c
            assert board.get(r, c) == board.get(r, mc), (
                f"asymmetry at ({r},{c}) vs ({r},{mc})"
            )


def test_all_spec_colors_appear_on_board() -> None:
    """Generated boards must contain every color in 1..num_colors."""
    for level_index, axis in [(64, "horizontal"), (84, "horizontal"),
                              (44, "none")]:
        spec = _spec(level_index=level_index, axis=axis)
        # Override num_colors per band logic: high-color cases.
        spec_high = LevelSpec(
            rows=spec.rows, cols=spec.cols,
            num_colors=7,
            shots_remaining=spec.shots_remaining,
            target_density=spec.target_density,
            num_seeds=spec.num_seeds,
            target_features=spec.target_features,
            weights=spec.weights,
            max_generations=spec.max_generations,
            level_index=spec.level_index,
            symmetry_axis=axis,
        )
        for seed in (11, 27, 53):
            board, _ = generate_level(spec_high, seed=seed)
            present = {board.get(r, c) for r, c in board.occupied_cells()}
            missing = set(range(1, 8)) - present
            assert not missing, (
                f"axis={axis} level={level_index} seed={seed}: "
                f"missing colors {sorted(missing)} "
                f"(present: {sorted(present)})"
            )


def test_alternating_row_widths() -> None:
    """ADR 0009: even rows wide (cols), odd rows narrow (cols-1)."""
    b = Board(rows=8, cols=10, num_colors=4, shots_remaining=12)
    for r in range(b.rows):
        expected = b.cols if (r & 1) == 0 else b.cols - 1
        assert b.row_width(r) == expected, (
            f"row {r} expected width {expected}, got {b.row_width(r)}"
        )
        assert len(b.cells[r]) == expected, (
            f"row {r} cells len mismatch: {len(b.cells[r])} vs {expected}"
        )
    # Total = 4 wide * 10 + 4 narrow * 9 = 76.
    assert b.total_cells() == 4 * 10 + 4 * 9


def main() -> None:
    tests = [
        test_horizontal_symmetric_levels_have_no_floating,
        test_asymmetric_levels_have_no_floating,
        test_horizontal_symmetric_layout_is_actually_symmetric,
        test_alternating_row_widths,
        test_all_spec_colors_appear_on_board,
    ]
    for t in tests:
        t()
        print(f"  PASS  {t.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    main()
