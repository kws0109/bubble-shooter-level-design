"""Smoke test: generate a board, run the bot triplet, print EAC + clear rate."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bubble.features import compute_features
from bubble.generator import LevelSpec, generate_level
from bubble.solver import calibrate_triplet


def main() -> None:
    spec = LevelSpec(
        rows=8,
        cols=10,
        num_colors=4,
        shots_remaining=16,
        target_density=0.5,
        num_seeds=6,
        target_features={
            "color_entropy": 1.8,
            "max_chain_depth": 6,
            "floating_potential": 0.8,
            "density": 0.5,
        },
        weights={
            "color_entropy": 1.0,
            "max_chain_depth": 0.5,
            "floating_potential": 1.0,
            "density": 2.0,
        },
        max_generations=400,
        level_index=10,
        symmetric=True,
    )
    board, _ = generate_level(spec, seed=7)

    print("=== Board (seed 7) ===")
    print(board.render_ascii())
    fv = compute_features(board)
    print("\nFeature vector:")
    for k, v in fv.as_dict().items():
        print(f"  {k:>20}  {v:.3f}")

    print(f"\nRunning bot triplet (100 runs each)...")
    t0 = time.time()
    results = calibrate_triplet(board, runs=100, base_seed=1000)
    dt = time.time() - t0

    print(f"\n=== Bot calibration (took {dt:.1f}s) ===")
    print(f"{'bot':>8}  {'clear_rate':>11}  {'EAC':>8}  {'EAC_all':>8}  {'popped':>8}")
    for name in ("weak", "medium", "strong"):
        r = results[name]
        eac_str = f"{r.eac:.2f}" if r.eac != float("inf") else "  inf"
        print(f"{name:>8}  {r.clear_rate:>10.1%}  {eac_str:>8}  "
              f"{r.eac_all:>8.2f}  {r.avg_popped:>8.1f}")


if __name__ == "__main__":
    main()
