"""Visual smoke for strict symmetry. Generates 4 levels (2 horizontal,
2 vertical) and prints ASCII renderings + features."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bubble.features import compute_features
from bubble.generator import LevelSpec, generate_level


def main() -> None:
    base_target = {
        "color_entropy": 1.6,
        "max_chain_depth": 6,
        "floating_potential": 0.8,
        "density": 0.5,
    }
    weights = {"color_entropy": 1.0, "max_chain_depth": 0.5,
               "floating_potential": 1.0, "density": 2.0}

    cases = [
        ("horizontal", 11),
        ("horizontal", 22),
        ("vertical", 33),
        ("vertical", 44),
    ]
    for axis, seed in cases:
        spec = LevelSpec(
            rows=8, cols=10, num_colors=5, shots_remaining=18,
            target_density=0.5, num_seeds=6,
            target_features=base_target, weights=weights,
            max_generations=600,
            level_index=20, symmetry_axis=axis,
        )
        board, history = generate_level(spec, seed=seed)
        fv = compute_features(board)
        print(f"=== axis={axis}  seed={seed} ===")
        print(board.render_ascii())
        print(f"  fitness {history[0]:.2f} -> {history[-1]:.2f}  "
              f"entropy={fv.color_entropy:.2f}  density={fv.density:.2f}")
        print()


if __name__ == "__main__":
    main()
