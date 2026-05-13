"""Batch generation, calibration, and regression analysis.

Pipeline:
    1. Sample diverse `LevelSpec` targets (vary entropy/chain/floating).
    2. For each target, generate a board (`generator.generate_level`).
    3. Compute its 6-dim feature vector.
    4. Calibrate three bots, get clear_rate and EAC for each.
    5. Persist per-level rows; run OLS regression to find which features
       predict difficulty (clear_rate, log EAC) best.

Outputs go to `levels/` (per-level JSON) and `reports/` (summary CSV +
regression results + charts).
"""

from __future__ import annotations

import csv
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np

from .board import Board
from .features import FeatureVector, compute_features
from .generator import LevelSpec, generate_level, colors_for_level
from .rationale import make_rationale
from .solver import calibrate_triplet, CalibrationResult


# --- per-level record ------------------------------------------------------

@dataclass
class LevelRecord:
    level_id: str
    seed: int
    spec: dict
    features: dict
    bots: dict[str, dict]
    rationale: dict | None = None

    def flat_row(self) -> dict:
        row = {"level_id": self.level_id, "seed": self.seed}
        row.update({f"feat_{k}": v for k, v in self.features.items()})
        for bot_name, bot in self.bots.items():
            row[f"{bot_name}_clear_rate"] = bot["clear_rate"]
            eac = bot["eac"]
            row[f"{bot_name}_eac"] = eac if math.isfinite(eac) else None
            row[f"{bot_name}_eac_all"] = bot["eac_all"]
        return row


# --- spec sampling ---------------------------------------------------------

def sample_specs(n: int, rng: np.random.Generator,
                 base: dict | None = None,
                 symmetric: bool = True,
                 progressive_colors: bool = True,
                 level_indices: list[int] | None = None) -> list[LevelSpec]:
    """Sample level specs for Iteration 4 (ADR 0008).

    Changes vs iter2/iter3:
    - `shot_pressure` is now sampled INDEPENDENTLY from density
      (ADR 0008). `shots_remaining` is then derived from both.
      This breaks the structural anti-correlation that dominated
      earlier iterations.
    - `level_indices` lets a smoke run target specific bands instead
      of the default 0..n-1 sweep.
    """
    import random as _random

    base = base or {}
    rows = base.get("rows", 8)
    cols = base.get("cols", 10)
    total_cells = rows * cols
    weights = {
        "color_entropy": 1.0,
        "max_chain_depth": 0.5,
        "floating_potential": 1.0,
        "density": 2.0,
    }

    if level_indices is None:
        level_indices = list(range(n))
    else:
        level_indices = list(level_indices)
        if n != len(level_indices):
            n = len(level_indices)

    specs: list[LevelSpec] = []
    rng_py = _random.Random(int(rng.integers(0, 2**32 - 1)))
    for slot, level_idx in enumerate(level_indices):
        if progressive_colors:
            num_colors = colors_for_level(level_idx, rng_py)
        else:
            num_colors = int(base.get("num_colors", 4))

        density = float(rng.uniform(0.35, 0.65))
        shot_pressure = float(rng.uniform(0.30, 0.65))
        shots = max(6, round(density * total_cells * shot_pressure))

        target = {
            "color_entropy": float(rng.uniform(1.2, 2.0)),
            "max_chain_depth": int(rng.integers(4, 12)),
            "floating_potential": float(rng.uniform(0.4, 1.6)),
            "density": density,
        }
        # ADR 0007: only horizontal mirror or no symmetry are physically
        # valid. 2026-05-13: asymmetric layouts disabled by user decision —
        # commercial puzzles align on horizontal symmetry and 25% noise
        # didn't earn a clear regression win in iter1~iter3.
        axis = "horizontal" if symmetric else "none"
        specs.append(LevelSpec(
            rows=rows, cols=cols,
            num_colors=num_colors,
            shots_remaining=shots,
            target_density=density,
            num_seeds=int(rng.integers(4, 9)),
            target_features=target,
            weights=weights,
            max_generations=600,
            level_index=level_idx,
            symmetric=False,
            symmetry_axis=axis,
        ))
    return specs


# --- batch run -------------------------------------------------------------

def run_batch(n: int, output_dir: Path,
              calibration_runs: int = 60,
              base_seed: int = 1000,
              quiet: bool = False,
              level_indices: list[int] | None = None) -> list[LevelRecord]:
    rng = np.random.default_rng(base_seed)
    specs = sample_specs(n, rng, level_indices=level_indices)
    levels_dir = output_dir / "levels"
    levels_dir.mkdir(parents=True, exist_ok=True)

    records: list[LevelRecord] = []
    t0 = time.time()
    for i, spec in enumerate(specs):
        seed = base_seed + i
        board, _ = generate_level(spec, seed=seed)
        features = compute_features(board)
        cal = calibrate_triplet(board, runs=calibration_runs, base_seed=seed * 7919)

        level_id = f"L{i:03d}"
        cal_dicts = {k: r.as_dict() for k, r in cal.items()}
        rationale = make_rationale(spec, features, cal_dicts,
                                   axis=spec.effective_axis).as_dict()
        record = LevelRecord(
            level_id=level_id,
            seed=seed,
            spec={
                "target_features": spec.target_features,
                "weights": spec.weights,
                "rows": spec.rows, "cols": spec.cols,
                "num_colors": spec.num_colors,
                "shots_remaining": spec.shots_remaining,
                "target_density": spec.target_density,
                "num_seeds": spec.num_seeds,
                "level_index": spec.level_index,
                "symmetric": spec.symmetric,
                "symmetry_axis": spec.effective_axis,
            },
            features=features.as_dict(),
            bots=cal_dicts,
            rationale=rationale,
        )
        records.append(record)

        with open(levels_dir / f"{level_id}.json", "w", encoding="utf-8") as f:
            json.dump({
                "level_id": level_id,
                "board": board.to_dict(),
                "features": features.as_dict(),
                "bots": cal_dicts,
                "spec": record.spec,
                "rationale": rationale,
            }, f, indent=2, ensure_ascii=False)

        if not quiet:
            elapsed = time.time() - t0
            avg = elapsed / (i + 1)
            remaining = avg * (n - i - 1)
            print(f"  [{i+1:3d}/{n}] {level_id} "
                  f"weak={cal['weak'].clear_rate:.0%} "
                  f"med={cal['medium'].clear_rate:.0%} "
                  f"str={cal['strong'].clear_rate:.0%}  "
                  f"({elapsed:.0f}s elapsed, ~{remaining:.0f}s left)")
    return records


# --- regression ------------------------------------------------------------

@dataclass
class RegressionResult:
    target: str
    feature_names: list[str]
    coefficients: list[float]
    intercept: float
    r_squared: float
    n: int

    def as_dict(self) -> dict:
        return {
            "target": self.target,
            "n": self.n,
            "r_squared": self.r_squared,
            "intercept": self.intercept,
            "coefficients": dict(zip(self.feature_names, self.coefficients)),
        }


def _z_standardize(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mu = matrix.mean(axis=0)
    sigma = matrix.std(axis=0, ddof=0)
    sigma[sigma == 0] = 1.0
    return (matrix - mu) / sigma, mu, sigma


def regress(records: list[LevelRecord], target: str) -> RegressionResult:
    """OLS regression of `target` on the standardized 6-d feature vector."""
    feature_names = list(FeatureVector.keys())
    rows = []
    ys = []
    for r in records:
        y_val = r.flat_row().get(target)
        if y_val is None or (isinstance(y_val, float) and not math.isfinite(y_val)):
            continue
        rows.append([r.features[k] for k in feature_names])
        ys.append(float(y_val))
    if len(rows) < len(feature_names) + 2:
        raise ValueError(f"not enough samples ({len(rows)}) for regression")
    X = np.asarray(rows, dtype=float)
    y = np.asarray(ys, dtype=float)
    Xz, _, _ = _z_standardize(X)
    Xb = np.hstack([Xz, np.ones((Xz.shape[0], 1))])
    beta, *_ = np.linalg.lstsq(Xb, y, rcond=None)
    coefs, intercept = beta[:-1], float(beta[-1])
    y_pred = Xb @ beta
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return RegressionResult(
        target=target,
        feature_names=feature_names,
        coefficients=[float(c) for c in coefs],
        intercept=intercept,
        r_squared=r2,
        n=len(rows),
    )


# --- persistence -----------------------------------------------------------

def write_csv(records: list[LevelRecord], path: Path) -> None:
    if not records:
        return
    rows = [r.flat_row() for r in records]
    keys = sorted({k for row in rows for k in row.keys()})
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(records: list[LevelRecord],
                  regressions: dict[str, RegressionResult],
                  path: Path) -> None:
    summary = {
        "n_levels": len(records),
        "regressions": {k: r.as_dict() for k, r in regressions.items()},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
