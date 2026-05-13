"""Iteration-4 smoke (ADR 0008): one level per 10-level band.

Generates 10 levels at indices 4, 14, ..., 94 (one in the middle of
each progression band) using the new independent-shot_pressure spec
sampling. Verifies that the structural anti-correlation between density
and shot_pressure is broken.

Outputs go to `experiments/iter4_smoke/`. Iteration-3 results in
`levels/`, `reports/` are left untouched until the user approves a
full re-batch.
"""

from __future__ import annotations

import csv
import json
import math
import sys
import time
from pathlib import Path

# Force UTF-8 stdout for Windows cp949 consoles.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bubble.analytics import run_batch
from bubble.charts import difficulty_distribution, feature_vs_target


SMOKE_INDICES = [4, 14, 24, 34, 44, 54, 64, 74, 84, 94]  # mid-band picks


def main() -> None:
    out_dir = ROOT / "experiments" / "iter4_smoke"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "levels").mkdir(exist_ok=True)
    (out_dir / "reports").mkdir(exist_ok=True)

    print(f"Generating {len(SMOKE_INDICES)} levels: {SMOKE_INDICES}")
    t0 = time.time()
    records = run_batch(
        n=len(SMOKE_INDICES),
        output_dir=out_dir,
        calibration_runs=60,
        base_seed=20260506,
        level_indices=SMOKE_INDICES,
        quiet=False,
    )
    print(f"\nDone in {time.time() - t0:.0f}s.")

    # CSV summary.
    csv_path = out_dir / "reports" / "levels_summary.csv"
    rows = [r.flat_row() for r in records]
    keys = sorted({k for row in rows for k in row.keys()})
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)

    # Multicollinearity check.
    densities = [r.features["density"] for r in records]
    pressures = [r.features["shot_pressure"] for r in records]
    n = len(densities)
    md = sum(densities) / n
    mp = sum(pressures) / n
    num = sum((densities[i] - md) * (pressures[i] - mp) for i in range(n))
    dx = math.sqrt(sum((d - md) ** 2 for d in densities))
    dy = math.sqrt(sum((p - mp) ** 2 for p in pressures))
    corr = num / (dx * dy) if dx > 0 and dy > 0 else 0.0

    # shots range
    shots_list = [r.spec["shots_remaining"] for r in records]

    print("\n=== Iter4 smoke summary (n = 10) ===")
    print(f"corr(density, shot_pressure) = {corr:+.3f}   "
          f"(iter3 baseline -0.780)")
    print(f"shots range: {min(shots_list)} .. {max(shots_list)}, mean {sum(shots_list)/n:.1f}")
    print()

    print("Per-level (ASCII):")
    print(f"{'L':<5}{'colors':<8}{'shots':<7}{'density':<9}"
          f"{'pressure':<10}{'weak%':<8}{'med%':<8}{'str%':<7}{'rationale.summary'}")
    for r in records:
        bots = r.bots
        sp = r.features["shot_pressure"]
        d = r.features["density"]
        rat = (r.rationale or {}).get("summary", "")
        print(f"L{r.spec['level_index']:<4}"
              f"{r.spec['num_colors']:<8}"
              f"{r.spec['shots_remaining']:<7}"
              f"{d:<9.3f}{sp:<10.3f}"
              f"{bots['weak']['clear_rate']*100:<7.0f}%"
              f"{bots['medium']['clear_rate']*100:<7.0f}%"
              f"{bots['strong']['clear_rate']*100:<6.0f}% "
              f"{rat}")

    # Charts.
    try:
        difficulty_distribution(records, out_dir / "reports" / "difficulty_distribution.png")
        feature_vs_target(records, "strong_clear_rate",
                          out_dir / "reports" / "feature_vs_strong_clear.png")
        print("\nCharts written to experiments/iter4_smoke/reports/")
    except Exception as exc:  # noqa: BLE001
        print(f"chart generation skipped: {exc}")


if __name__ == "__main__":
    main()
