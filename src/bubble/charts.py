"""Matplotlib charts summarizing batch analytics."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .analytics import LevelRecord, RegressionResult
from .features import FeatureVector


def difficulty_distribution(records: list[LevelRecord], path: Path) -> None:
    """Three-bot clear-rate histogram on one canvas."""
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), sharey=True)
    for ax, name in zip(axes, ("weak", "medium", "strong")):
        rates = [r.bots[name]["clear_rate"] for r in records]
        ax.hist(rates, bins=12, range=(0, 1), edgecolor="black", alpha=0.85)
        ax.set_title(f"{name} clear rate")
        ax.set_xlabel("clear rate")
        ax.set_xlim(0, 1)
    axes[0].set_ylabel("levels")
    fig.suptitle(f"Bot clear-rate distribution across {len(records)} levels")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def feature_vs_target(records: list[LevelRecord], target_key: str,
                      path: Path) -> None:
    """Six scatter plots: each feature vs the target metric."""
    keys = list(FeatureVector.keys())
    targets = [r.flat_row().get(target_key) for r in records]
    targets = [t if t is not None else float("nan") for t in targets]

    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    for ax, key in zip(axes.flat, keys):
        xs = [r.features[key] for r in records]
        ax.scatter(xs, targets, s=22, alpha=0.7)
        ax.set_xlabel(key)
        ax.set_ylabel(target_key)
        ax.grid(True, alpha=0.3)
    fig.suptitle(f"Feature vs {target_key}")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def regression_bars(reg: RegressionResult, path: Path) -> None:
    """Standardized regression coefficients bar chart."""
    names = reg.feature_names
    coefs = reg.coefficients
    order = np.argsort(np.abs(coefs))[::-1]
    names = [names[i] for i in order]
    coefs = [coefs[i] for i in order]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.barh(names[::-1], coefs[::-1],
                   color=["#2b8cbe" if c >= 0 else "#e34a33" for c in coefs[::-1]])
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("standardized coefficient")
    ax.set_title(f"Regressing {reg.target}  (R^2 = {reg.r_squared:.2f}, n = {reg.n})")
    for bar, val in zip(bars, coefs[::-1]):
        ax.text(val, bar.get_y() + bar.get_height() / 2,
                f"  {val:+.2f}",
                va="center", ha="left" if val >= 0 else "right",
                fontsize=9)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)
