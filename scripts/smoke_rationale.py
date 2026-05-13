"""Generate one level + calibrate + render its rationale to stdout."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Force UTF-8 stdout so em-dashes etc. render on Windows cp949 consoles.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bubble.features import compute_features
from bubble.generator import LevelSpec, generate_level
from bubble.rationale import make_rationale
from bubble.solver import calibrate_triplet


def show(level_index: int, axis: str, seed: int) -> None:
    spec = LevelSpec(
        rows=8, cols=10,
        num_colors=2 + min(level_index // 10, 4) + (level_index % 2),
        shots_remaining=12 + 2 * (min(level_index // 10, 4)),
        target_density=0.50,
        num_seeds=6,
        target_features={
            "color_entropy": 1.6,
            "max_chain_depth": 7,
            "floating_potential": 1.1,
            "density": 0.50,
        },
        weights={"color_entropy": 1.0, "max_chain_depth": 0.5,
                 "floating_potential": 1.0, "density": 2.0},
        max_generations=400,
        level_index=level_index,
        symmetry_axis=axis,
    )
    board, _ = generate_level(spec, seed=seed)
    fv = compute_features(board)
    cal = {k: r.as_dict()
           for k, r in calibrate_triplet(board, runs=40, base_seed=seed * 7919).items()}
    r = make_rationale(spec, fv, cal, axis=axis).as_dict()

    print(f"=== L{level_index:03d}  axis={axis}  seed={seed} ===")
    print(board.render_ascii())
    print(f"floating_cells: {len(board.floating_cells())}")
    print()
    print(json.dumps(r, indent=2, ensure_ascii=False))
    print()


def main() -> None:
    show(level_index=2, axis="horizontal", seed=11)
    show(level_index=18, axis="horizontal", seed=22)
    show(level_index=35, axis="none", seed=33)


if __name__ == "__main__":
    main()
