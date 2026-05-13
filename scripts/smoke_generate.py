"""Smoke test: generate one level and print stats + ASCII rendering."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bubble.features import compute_features
from bubble.generator import LevelSpec, generate_level, seed_and_grow
import random


def main() -> None:
    spec = LevelSpec(
        rows=8,
        cols=10,
        num_colors=4,
        shots_remaining=14,
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
    )

    # Stage 1 only — show what 'designed shape' looks like.
    rng = random.Random(7)
    seeded = seed_and_grow(spec, rng)
    print("=== Stage 1 (seed_and_grow) ===")
    print(seeded.render_ascii())
    print("features:", compute_features(seeded).as_dict())

    # Both stages — show what 'manufactured to spec' looks like.
    final, history = generate_level(spec, seed=7)
    print("\n=== Stage 2 (after evolution) ===")
    print(final.render_ascii())
    print("features:", compute_features(final).as_dict())
    print(f"\ngenerations run: {len(history) - 1}")
    print(f"fitness: {history[0]:.4f} -> {history[-1]:.4f}")


if __name__ == "__main__":
    main()
