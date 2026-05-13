"""LLM design assistant.

Closes the loop between designer intent (natural language + target features)
and the procedural pipeline. The flow is:

    1. Designer hands the assistant: current_board + current_features +
       desired_features + (optional regression context).
    2. The assistant proposes a *patch* (a list of cell mutations) plus a
       short rationale in natural language.
    3. We apply the patch to a clone, recompute features, and report back.

Why a structured patch instead of free-form chat
------------------------------------------------
- Reproducible: same input -> same patch (with deterministic temperature).
- Verifiable: every patch is checked against the feature delta, not taken
  on the LLM's word.
- Cheap: the response is a small JSON document, not a full board.

Provider
--------
Uses the Anthropic Python SDK (`anthropic`). If `ANTHROPIC_API_KEY` is not
set, falls back to a deterministic *mock proposer* that picks low-impact
mutations toward the target. This keeps the demo runnable without secrets.
"""

from __future__ import annotations

import json
import math
import os
import random
from dataclasses import dataclass, field
from typing import Any

from .board import Board, EMPTY
from .features import FeatureVector, compute_features


# --- patch model -----------------------------------------------------------

@dataclass(frozen=True)
class CellEdit:
    row: int
    col: int
    color: int  # 0 = clear

    def as_dict(self) -> dict:
        return {"row": self.row, "col": self.col, "color": self.color}

    @classmethod
    def from_dict(cls, d: dict) -> "CellEdit":
        return cls(row=int(d["row"]), col=int(d["col"]), color=int(d["color"]))


@dataclass
class DesignProposal:
    rationale: str
    edits: list[CellEdit] = field(default_factory=list)

    def apply(self, board: Board) -> Board:
        out = board.clone()
        for e in self.edits:
            if not out.in_bounds(e.row, e.col):
                continue
            if 0 <= e.color <= board.num_colors:
                out.set(e.row, e.col, e.color)
        return out


@dataclass
class TuningRound:
    iteration: int
    proposal: DesignProposal
    features_before: dict[str, float]
    features_after: dict[str, float]
    distance_before: float
    distance_after: float
    improved: bool


# --- prompt construction ---------------------------------------------------

_SYSTEM_PROMPT = """\
You are a senior puzzle level designer with 10 years of experience tuning
hexagonal bubble shooters. Given a board, its current 6-dimensional
feature vector, and a target feature vector, propose a SMALL patch of
cell-level edits that pushes the board toward the target. Prefer few
edits over many.

You MUST respond with a single JSON document of the form:

{"rationale": "<one paragraph in plain English>",
 "edits": [{"row": <int>, "col": <int>, "color": <int>}, ...]}

Rules:
- color = 0 clears the cell; color in 1..num_colors places that color.
- Only edit cells that are inside the board.
- Keep patches tight: typically 4-12 edits.
- Do not include any text outside the JSON object.
"""


def _board_ascii(board: Board) -> str:
    return board.render_ascii()


def build_user_message(board: Board,
                       current: dict[str, float],
                       target: dict[str, float],
                       regression_hint: dict[str, float] | None = None) -> str:
    parts: list[str] = []
    parts.append("Board (rows x cols = "
                 f"{board.rows}x{board.cols}, colors=1..{board.num_colors}):")
    parts.append("```")
    parts.append(_board_ascii(board))
    parts.append("```")
    parts.append("Current features:")
    parts.append(json.dumps(current, indent=2))
    parts.append("Target features:")
    parts.append(json.dumps(target, indent=2))
    if regression_hint:
        parts.append("\nRegression context (standardized coefficients on "
                     "strong_clear_rate; positive = increases clear rate):")
        parts.append(json.dumps(regression_hint, indent=2))
    parts.append("\nReturn the JSON proposal now.")
    return "\n".join(parts)


# --- LLM call --------------------------------------------------------------

def _call_anthropic(system: str, user: str, model: str) -> str:
    import anthropic  # local import so the module loads without the SDK

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(block.text for block in resp.content
                   if getattr(block, "type", None) == "text")
    return text


# --- mock fallback ---------------------------------------------------------

def _mock_proposer(board: Board,
                   current: dict[str, float],
                   target: dict[str, float],
                   rng: random.Random) -> DesignProposal:
    """Deterministic placeholder when ANTHROPIC_API_KEY is missing.

    Strategy: pick the feature with the largest absolute gap and propose
    a few targeted edits. Crude but useful for demoing the loop.
    """
    rationale_parts = ["[mock] No Anthropic key set; using a heuristic proposer."]
    edits: list[CellEdit] = []

    gaps = {k: target[k] - current.get(k, 0.0) for k in target}
    if not gaps:
        return DesignProposal(rationale=" ".join(rationale_parts), edits=[])
    primary = max(gaps, key=lambda k: abs(gaps[k]))
    direction = "increase" if gaps[primary] > 0 else "decrease"
    rationale_parts.append(f"Targeting {primary} ({direction}).")

    occupied = list(board.occupied_cells())
    empties = [(r, c) for r in range(board.rows) for c in range(board.cols)
               if board.is_empty(r, c)]

    if primary == "density":
        if direction == "increase" and empties:
            for r, c in rng.sample(empties, min(6, len(empties))):
                edits.append(CellEdit(r, c, rng.randint(1, board.num_colors)))
        elif occupied:
            for r, c in rng.sample(occupied, min(6, len(occupied))):
                edits.append(CellEdit(r, c, EMPTY))
    elif primary == "color_entropy":
        if occupied:
            sample = rng.sample(occupied, min(6, len(occupied)))
            for r, c in sample:
                old = board.get(r, c)
                choices = [k for k in range(1, board.num_colors + 1) if k != old]
                if choices:
                    edits.append(CellEdit(r, c, rng.choice(choices)))
    else:
        # fallback: small mixed mutation
        targets = rng.sample(occupied, min(4, len(occupied))) if occupied else []
        for r, c in targets:
            edits.append(CellEdit(r, c, rng.randint(1, board.num_colors)))

    return DesignProposal(rationale=" ".join(rationale_parts), edits=edits)


# --- proposer entry point --------------------------------------------------

def propose_patch(board: Board,
                  current: dict[str, float],
                  target: dict[str, float],
                  regression_hint: dict[str, float] | None = None,
                  model: str = "claude-haiku-4-5-20251001",
                  rng: random.Random | None = None) -> DesignProposal:
    """Return a `DesignProposal` from either the LLM or the mock proposer."""
    rng = rng or random.Random()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _mock_proposer(board, current, target, rng)

    system = _SYSTEM_PROMPT
    user = build_user_message(board, current, target, regression_hint)
    try:
        raw = _call_anthropic(system, user, model)
        data = _extract_json(raw)
        rationale = str(data.get("rationale", ""))
        edits = [CellEdit.from_dict(e) for e in data.get("edits", [])]
        return DesignProposal(rationale=rationale, edits=edits)
    except Exception as exc:  # noqa: BLE001 - network/parse errors fall back
        return DesignProposal(
            rationale=f"[fallback] LLM call failed: {exc}",
            edits=[],
        )


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of an LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object found in response: {text!r}")
    return json.loads(text[start: end + 1])


# --- closed-loop tuning ----------------------------------------------------

def _distance(current: dict[str, float], target: dict[str, float],
              weights: dict[str, float] | None = None) -> float:
    weights = weights or {}
    total = 0.0
    for k, goal in target.items():
        w = weights.get(k, 1.0)
        diff = current.get(k, 0.0) - goal
        total += w * diff * diff
    return math.sqrt(total)


def tune(board: Board, target: dict[str, float],
         weights: dict[str, float] | None = None,
         rounds: int = 5,
         regression_hint: dict[str, float] | None = None,
         seed: int = 0) -> tuple[Board, list[TuningRound]]:
    """Iterate propose -> apply -> measure until target is reached or rounds end."""
    history: list[TuningRound] = []
    rng = random.Random(seed)
    current_board = board.clone()
    current_features = compute_features(current_board).as_dict()

    for it in range(rounds):
        proposal = propose_patch(current_board, current_features,
                                 target, regression_hint, rng=rng)
        candidate = proposal.apply(current_board)
        new_features = compute_features(candidate).as_dict()
        before = _distance(current_features, target, weights)
        after = _distance(new_features, target, weights)
        improved = after < before - 1e-9
        history.append(TuningRound(
            iteration=it,
            proposal=proposal,
            features_before=current_features,
            features_after=new_features,
            distance_before=before,
            distance_after=after,
            improved=improved,
        ))
        if improved:
            current_board = candidate
            current_features = new_features
        if after < 1e-3:
            break

    return current_board, history
