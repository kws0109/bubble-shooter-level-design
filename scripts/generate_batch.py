"""Generate a batch of levels, calibrate bots, run regressions, write reports.

Usage:
    python scripts/generate_batch.py [N]   # default 100
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bubble.analytics import (
    run_batch,
    regress,
    write_csv,
    write_summary,
)
from bubble.charts import (
    difficulty_distribution,
    feature_vs_target,
    regression_bars,
)


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    out = ROOT
    reports = out / "reports"

    print(f"Generating {n} levels...")
    t0 = time.time()
    records = run_batch(n, out, calibration_runs=60)
    print(f"\nGenerated {len(records)} levels in {time.time() - t0:.1f}s.")

    print("\nWriting summary CSV...")
    write_csv(records, reports / "levels_summary.csv")

    print("Running regressions...")
    regressions = {}
    for target in ("weak_clear_rate", "medium_clear_rate", "strong_clear_rate",
                   "strong_eac_all"):
        try:
            regressions[target] = regress(records, target)
        except ValueError as e:
            print(f"  skip {target}: {e}")

    write_summary(records, regressions, reports / "regression_summary.json")

    print("Drawing charts...")
    difficulty_distribution(records, reports / "difficulty_distribution.png")
    feature_vs_target(records, "strong_clear_rate",
                      reports / "feature_vs_strong_clear.png")
    feature_vs_target(records, "strong_eac_all",
                      reports / "feature_vs_strong_eac.png")
    for target, reg in regressions.items():
        regression_bars(reg, reports / f"regression_{target}.png")

    print("\nReports:")
    for p in sorted(reports.glob("*")):
        print(f"  {p.relative_to(ROOT)}")

    print("\nRegression summary:")
    for target, reg in regressions.items():
        print(f"  {target:<24}  R^2 = {reg.r_squared:+.3f}  (n={reg.n})")


if __name__ == "__main__":
    main()
