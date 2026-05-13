"""Sanity tests for the 6-dimension feature vector."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bubble.board import Board
from bubble.features import (
    FeatureVector,
    color_entropy,
    avg_cluster_size,
    density,
    shot_pressure,
    compute_features,
)


def _trivial_board() -> Board:
    """3x3 board: top row all color 1, second row two color 2."""
    b = Board(rows=3, cols=3, num_colors=3, shots_remaining=10)
    b.set(0, 0, 1); b.set(0, 1, 1); b.set(0, 2, 1)
    b.set(1, 0, 2); b.set(1, 1, 2)
    return b


def test_entropy_uniform_vs_skewed() -> None:
    # Uniform 50/50 of two colors -> entropy = 1.0 bit.
    # Single-row board (all wide) for clean 50/50 in alternating layout.
    b = Board(rows=1, cols=4, num_colors=2, shots_remaining=5)
    b.set(0, 0, 1); b.set(0, 1, 1); b.set(0, 2, 2); b.set(0, 3, 2)
    assert abs(color_entropy(b) - 1.0) < 1e-9

    # Single color -> entropy = 0.
    b2 = Board(rows=1, cols=3, num_colors=2, shots_remaining=5)
    b2.set(0, 0, 1); b2.set(0, 1, 1); b2.set(0, 2, 1)
    assert color_entropy(b2) == 0.0


def test_avg_cluster_size_separates_groups() -> None:
    b = _trivial_board()
    # Two clusters: size 3 and size 2 -> mean 2.5.
    assert avg_cluster_size(b) == 2.5


def test_density_and_shot_pressure() -> None:
    b = _trivial_board()
    # 3x3 alternating-width board: row widths 3, 2, 3 → 8 total cells.
    # 5 occupied / 8 cells.
    assert abs(density(b) - 5 / 8) < 1e-9
    # 10 shots / 5 occupied = 2.0.
    assert abs(shot_pressure(b) - 2.0) < 1e-9


def test_full_feature_vector_has_all_keys() -> None:
    b = _trivial_board()
    fv = compute_features(b)
    assert isinstance(fv, FeatureVector)
    d = fv.as_dict()
    assert set(d.keys()) == set(FeatureVector.keys())
    # Every dimension must be a finite number.
    for k, v in d.items():
        assert v == v, f"{k} is NaN"  # NaN check
        assert v != float("inf"), f"{k} is inf"


def test_chain_depth_picks_up_a_match() -> None:
    # Set up a board where shooting a color-1 bubble pops 3+.
    b = Board(rows=3, cols=4, num_colors=3, shots_remaining=10)
    b.set(0, 0, 1); b.set(0, 1, 1)  # two colour-1 on ceiling
    b.set(1, 0, 1)                  # third colour-1 below
    fv = compute_features(b)
    # Some shot trial should match >= 3 bubbles. The test just confirms the
    # measurement isn't always zero on a board where matches are possible.
    assert fv.max_chain_depth >= 3


def main() -> None:
    tests = [
        test_entropy_uniform_vs_skewed,
        test_avg_cluster_size_separates_groups,
        test_density_and_shot_pressure,
        test_full_feature_vector_has_all_keys,
        test_chain_depth_picks_up_a_match,
    ]
    for t in tests:
        t()
        print(f"  PASS  {t.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    main()
