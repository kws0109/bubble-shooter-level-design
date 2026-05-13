"""Smoke test: take an existing level and ask the AI designer to nudge density."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bubble.ai_designer import tune
from bubble.board import Board
from bubble.features import compute_features


def main() -> None:
    levels_dir = ROOT / "levels"
    sample = next(iter(sorted(levels_dir.glob("L*.json"))), None)
    if sample is None:
        print("No level files yet. Run scripts/generate_batch.py first.")
        return

    with open(sample, encoding="utf-8") as f:
        data = json.load(f)
    board = Board.from_dict(data["board"])
    print(f"Loaded {data['level_id']} from {sample.name}")
    fv = compute_features(board)
    print("Current features:")
    for k, v in fv.as_dict().items():
        print(f"  {k:>20}  {v:.3f}")

    target = {
        "color_entropy": fv.color_entropy + 0.2,
        "density": min(0.8, fv.density + 0.1),
    }
    print("\nTarget: nudge entropy and density up.")
    print(json.dumps(target, indent=2))

    final, history = tune(board, target, rounds=4, seed=42)
    print(f"\nRan {len(history)} tuning rounds.")
    for h in history:
        print(f"  iter {h.iteration}: dist {h.distance_before:.3f} -> "
              f"{h.distance_after:.3f}  ({'kept' if h.improved else 'rejected'})  "
              f"{len(h.proposal.edits)} edits")
        print(f"    rationale: {h.proposal.rationale}")

    print("\nFinal features:")
    for k, v in compute_features(final).as_dict().items():
        print(f"  {k:>20}  {v:.3f}")


if __name__ == "__main__":
    main()
