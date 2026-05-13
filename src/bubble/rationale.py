"""Per-level design rationale ("Why").

Each generated level gets a structured note explaining:
- the difficulty band and color count behind the choice,
- which feature target dominates the design,
- how achieved features deviate from target,
- what the bot calibration says about expected play,
- what skill the level is meant to train,
- which axis (horizontal mirror or none) was used and why.

The generator is deterministic — same inputs yield the same prose. This
keeps the portfolio reproducible and lets us audit every claim. An LLM
upgrade hook is documented at the bottom for future prose enrichment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .features import FeatureVector
from .generator import LevelSpec


# --- output shape ---------------------------------------------------------

@dataclass
class FormulaApplication:
    """A mathematical formula applied to this level — what it computes
    and why the system uses it. ADR-traceable.
    """
    name: str       # short identifier, e.g. "color_progression"
    formula: str    # the equation itself
    value: str      # the equation evaluated on this level's inputs
    function: str   # what the formula computes
    why: str        # design rationale (ADR reference)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "formula": self.formula,
            "value": self.value,
            "function": self.function,
            "why": self.why,
        }


@dataclass
class PatternApplication:
    """An algorithmic pattern applied to this level — its effect and
    the reason it's in the pipeline. ADR-traceable.
    """
    name: str       # short identifier, e.g. "ceiling_anchor"
    effect: str     # what the pattern produces on the board
    why: str        # design rationale (ADR reference)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "effect": self.effect,
            "why": self.why,
        }


@dataclass
class Rationale:
    summary: str            # single-line designer headline
    band: str               # e.g. "L23 — 중반 (4색)"
    axis: str               # "좌우 대칭 패턴" / "비대칭 자유 배치"
    intent: str             # 2-3 sentences of design intent
    key_feature: str        # dimension name driving the design
    achieved: str           # delta vs target on the key feature
    expected_play: str      # bot calibration translated to designer language
    skill_trained: str      # what the player learns
    notes: list[str] = field(default_factory=list)  # optional flags
    formulas: list[FormulaApplication] = field(default_factory=list)
    patterns: list[PatternApplication] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "summary": self.summary,
            "band": self.band,
            "axis": self.axis,
            "intent": self.intent,
            "key_feature": self.key_feature,
            "achieved": self.achieved,
            "expected_play": self.expected_play,
            "skill_trained": self.skill_trained,
            "notes": self.notes,
            "formulas": [f.as_dict() for f in self.formulas],
            "patterns": [p.as_dict() for p in self.patterns],
        }


# --- helpers -------------------------------------------------------------

_FEATURE_LABEL_KO = {
    "color_entropy": "색 분리",
    "max_chain_depth": "큰 콤보",
    "floating_potential": "키스톤 부유",
    "density": "공간 압박",
    "avg_cluster_size": "정밀 사격",
}

# Sampling ranges from analytics.sample_specs — used to normalize each
# target into a 0..1 'extremeness' score so we can pick the dominant key.
_TARGET_RANGE = {
    "color_entropy": (1.2, 2.0),
    "max_chain_depth": (4, 12),
    "floating_potential": (0.4, 1.6),
}


def _band(level_index: int) -> str:
    if level_index < 10:
        return "초입"
    if level_index < 20:
        return "초반"
    if level_index < 30:
        return "중반"
    if level_index < 40:
        return "후반"
    if level_index < 50:
        return "마지막 단계"
    return "엔드게임"


def _key_feature(target: Mapping[str, float]) -> str:
    """Pick the target dimension whose value is most extreme within
    its sampled range. Falls back to 'density' when target is empty.
    """
    if not target:
        return "density"
    best = "density"
    best_score = -1.0
    for name, (lo, hi) in _TARGET_RANGE.items():
        if name not in target:
            continue
        v = float(target[name])
        score = (v - lo) / (hi - lo) if hi != lo else 0.0
        # symmetric extremeness — far from center counts equally low/high
        score = abs(score - 0.5) * 2.0
        if score > best_score:
            best_score = score
            best = name
    return best


def _intent(key: str, target: Mapping[str, float], num_colors: int) -> str:
    if key == "max_chain_depth":
        v = target.get("max_chain_depth", 7)
        return (f"한 발에 {v:.0f}개 이상이 깨지는 클러스터를 의도적으로 배치해, "
                f"플레이어가 큰 콤보의 시각·청각 보상을 경험하도록 만든다.")
    if key == "floating_potential":
        v = target.get("floating_potential", 1.0)
        return (f"부유 잠재력 {v:.1f} — 천장과 약하게 연결된 키스톤 버블을 "
                f"한 둘 떨어뜨리면 그 아래 부유 그룹이 함께 풀리도록 설계.")
    if key == "color_entropy":
        v = target.get("color_entropy", 1.6)
        return (f"색 엔트로피 {v:.2f}로 색 분포를 균등화. {num_colors}색 중 "
                f"매칭 후보를 빠르게 골라내는 시야 훈련.")
    if key == "density":
        v = target.get("density", 0.5)
        return (f"밀도 {v:.2f}. 보드 압박과 발사 수 관리가 핵심.")
    return "표준 보드 — 균형 잡힌 6차원 타겟."


def _achieved_summary(target: Mapping[str, float],
                      achieved: Mapping[str, float],
                      key: str) -> str:
    if key not in target:
        return "타겟 미설정"
    t = float(target[key])
    a = float(achieved.get(key, 0.0))
    delta = a - t
    rel = abs(delta) / max(abs(t), 1e-3)
    if rel < 0.10:
        return f"{key} 일치 (목표 {t:.2f} → 도달 {a:.2f})"
    sign = "+" if delta > 0 else ""
    return f"{key} {sign}{delta:.2f} 이탈 (목표 {t:.2f} → 도달 {a:.2f})"


def _expected_play(calibration: Mapping[str, Mapping[str, float]] | None) -> str:
    if not calibration:
        return "봇 데이터 없음."
    weak = float(calibration["weak"]["clear_rate"])
    strong = float(calibration["strong"]["clear_rate"])
    eac = float(calibration["strong"]["eac_all"])
    spread = strong - weak

    if spread > 0.30:
        diag = "기술 격차가 큰 레벨 — 키스톤 패턴 인식이 결과를 가른다."
    elif weak > 0.70:
        diag = "기초 — 즉각 클리어 가능, 온보딩 적합."
    elif strong < 0.60:
        diag = "고난도 — 정확도와 운 둘 다 요구."
    else:
        diag = "표준 난이도 — 평균적 플레이어가 1-2회 시도로 클리어."

    return (f"{diag} 봇 W{weak:.0%} / S{strong:.0%}, "
            f"평균 {eac:.0f}발.")


def _skill(key: str, num_colors: int) -> str:
    if key == "max_chain_depth":
        return "큰 클러스터 식별과 한 발 콤보."
    if key == "floating_potential":
        return "키스톤 버블 인식 — 부수면 풍성한 부유."
    if key == "color_entropy":
        return f"{num_colors}색 분리와 빠른 색 탐색."
    if key == "density":
        return "발사 자원 관리와 보드 압축 회피."
    return "보드 읽기 종합."


_AXIS_LABEL = {
    "horizontal": "좌우 대칭 패턴 — 시각적 일관성, 양쪽 동시 학습 가능.",
    "none": "비대칭 자유 배치 — 패턴 의존을 막고 즉흥 판단을 요구.",
}


# --- formulas applied to this level --------------------------------------

def _make_formulas(spec: LevelSpec) -> list[FormulaApplication]:
    """Extract the math formulas the system applied to build this level.

    Each entry carries the equation, its evaluated value on this spec,
    what it computes, and the ADR-backed reason it exists.
    """
    out: list[FormulaApplication] = []
    level_index = spec.level_index if spec.level_index is not None else 0
    bucket = min(level_index // 10, 4)
    band_label = _band(level_index)

    out.append(FormulaApplication(
        name="band_classification",
        formula=('band = ["초입", "초반", "중반", "후반", '
                 '"마지막 단계", "엔드게임"][min(L // 10, 5)]'),
        value=f"L{level_index + 1:03d} (idx={level_index}) → {band_label}",
        function="레벨 인덱스로 난이도 밴드 라벨을 결정한다.",
        why=("라이브 운영의 진행 페이싱 기본 단위. 10레벨마다 밴드가 "
             "바뀌면서 색 수·메커닉이 단계적으로 도입되도록 잡는 골격."),
    ))

    out.append(FormulaApplication(
        name="color_progression",
        formula="colors = randint(2 + bucket, 3 + bucket), bucket = min(L // 10, 4)",
        value=(f"L{level_index + 1:03d} (bucket={bucket}) → "
               f"후보 {2 + bucket}~{3 + bucket}색, 실제 {spec.num_colors}색"),
        function="레벨 인덱스에 따라 색 수 후보 범위를 점진 확장한다.",
        why=("초입은 2색으로 학습 부담을 최소화하고 10레벨마다 +1색으로 "
             "시야 부하를 단계적으로 증가시키는 ADR 0006 표준 진행."),
    ))

    total_cells = spec.total_cells
    density = spec.target_density
    shots = spec.shots_remaining
    pressure = shots / max(density * total_cells, 1e-3)
    out.append(FormulaApplication(
        name="shot_pressure_formula",
        formula="shots = round(density × cells × shot_pressure)",
        value=(f"density {density:.2f} × cells {total_cells} × "
               f"pressure {pressure:.2f} ≈ {shots}발"),
        function="보드 면적·밀도·압박 비율의 곱으로 발사 수를 결정한다.",
        why=("shot_pressure를 density와 독립 변수로 두어 다중공선성을 "
             "해소. iter1 corr=-0.976 → iter4 독립 샘플링으로 회귀 신뢰도 "
             "회복 (ADR 0008)."),
    ))

    if spec.weights:
        weight_str = ", ".join(f"{k}={v}" for k, v in spec.weights.items())
        out.append(FormulaApplication(
            name="weighted_distance_fitness",
            formula="fitness = Σ weight_i × |achieved_i - target_i|",
            value=f"가중치 ({weight_str})",
            function=("목표 벡터와 현재 보드 벡터의 가중 거리를 (1+1) "
                      "진화 적합도로 사용한다."),
            why=("디자이너가 어떤 차원을 더 중요하게 보는지를 가중치로 "
                 "표현. 변형이 가중치 큰 차원부터 수렴하도록 유도 "
                 "(ADR 0004)."),
        ))

    target = spec.target_features or {}
    sampled_parts = []
    if "color_entropy" in target:
        sampled_parts.append(f"entropy={float(target['color_entropy']):.2f}")
    if "max_chain_depth" in target:
        sampled_parts.append(f"chain={int(target['max_chain_depth'])}")
    if "floating_potential" in target:
        sampled_parts.append(f"floating={float(target['floating_potential']):.2f}")
    sampled_parts.append(f"density={density:.2f}")
    sampled_parts.append(f"pressure={pressure:.2f}")
    out.append(FormulaApplication(
        name="target_sampling_ranges",
        formula=("density ∈ U(0.35, 0.65), shot_pressure ∈ U(0.30, 0.65), "
                 "color_entropy ∈ U(1.2, 2.0), max_chain_depth ∈ U(4, 12), "
                 "floating_potential ∈ U(0.4, 1.6)"),
        value=", ".join(sampled_parts),
        function="각 타겟 차원의 변량 샘플링 범위를 명시한다.",
        why=("100레벨 배치가 어느 폭 안에서 만들어지는지 한눈에 보고, "
             "본 레벨이 그 폭의 어디에 위치하는지 비교 가능하도록 둠 "
             "(sample_specs의 uniform 샘플링 범위)."),
    ))
    return out


# --- patterns applied to this level --------------------------------------

def _make_patterns(spec: LevelSpec) -> list[PatternApplication]:
    """Extract the algorithmic patterns applied by the pipeline.

    Common patterns (two-stage, ceiling anchor, drop floating, bot
    triplet) appear on every level. The symmetry pattern varies by
    spec.effective_axis.
    """
    out: list[PatternApplication] = []
    out.append(PatternApplication(
        name="two_stage_generation",
        effect=("Stage 1 (시드 + BFS 성장)이 형태적 의도를 박고, "
                "Stage 2 ((1+1) 진화)가 목표 벡터에 수렴시킨다."),
        why=("결정론적 생성으로 재현성을 확보하면서 적합도 626 → 0.5의 "
             "1000배 감소가 첫 실험에서 검증된 구조 (ADR 0004)."),
    ))
    out.append(PatternApplication(
        name="ceiling_anchor",
        effect=("시드를 row 0에만 배치 → BFS 성장으로 모든 셀이 "
                "천장과 연결되도록 보장한다."),
        why=("버블슈터의 기본 규칙(천장 또는 다른 버블과 연결)을 시드 "
             "단계에서 강제. 부유 셀 발생 확률 0 (ADR 0007)."),
    ))
    out.append(PatternApplication(
        name="drop_floating",
        effect=("변형 후 즉시 떠 있는 셀을 제거해 playable 상태에서만 "
                "fitness를 평가한다."),
        why=("부유 셀이 회귀 노이즈로 작용한 iter1·iter2 결함을 정정. "
             "R² weak +0.10·medium +0.13 회복 (ADR 0007)."),
    ))

    # 2026-05-13: 사용자 결정으로 비대칭 패턴은 sample_specs에서
    # 제거됨. 모든 신규 레벨은 좌우 대칭으로 강제 생성된다.
    out.append(PatternApplication(
        name="horizontal_mirror",
        effect=("모든 셀 배치가 좌우 미러 쌍에 동시 적용 → 시각적 "
                "일관성과 양쪽 동시 학습이 가능해진다."),
        why=("라이브 게임 표준 패턴 — 디자이너 의도가 잘 보이는 "
             "구조. iter2 soft → strict 전환으로 시각 완성도 확보 "
             "(ADR 0006). 2026-05-13 결정으로 비대칭 분기 제거, "
             "신규 레벨은 100% 좌우 대칭."),
    ))

    out.append(PatternApplication(
        name="bot_triplet_calibration",
        effect=("weak/medium/strong 세 봇의 클리어율 spread를 신호로 "
                "난이도를 측정한다."),
        why=("단일 EAC 봇은 어려운 레벨에서 못 끝내 통계가 빠지는 "
             "함정이 있어, 트리플렛으로 측정 유효 범위를 확보 "
             "(ADR 0005)."),
    ))
    return out


# --- entry point ---------------------------------------------------------

def make_rationale(spec: LevelSpec,
                   achieved: FeatureVector,
                   calibration: Mapping[str, Mapping[str, float]] | None,
                   axis: str | None = None) -> Rationale:
    target = spec.target_features
    level_index = spec.level_index if spec.level_index is not None else 0
    axis = axis or spec.effective_axis
    key = _key_feature(target)
    band_label = _band(level_index)
    achieved_dict = achieved.as_dict()

    summary = (f"{band_label} {spec.num_colors}색 — "
               f"{_FEATURE_LABEL_KO[key]} 훈련")
    band = f"L{level_index + 1:03d}: {band_label} ({spec.num_colors}색)"
    axis_text = _AXIS_LABEL.get(axis, axis)

    notes: list[str] = []
    if achieved.density < 0.30:
        notes.append("밀도 0.3 미만 — 거의 빈 보드. 발사 수 점검 필요.")
    if achieved.color_entropy < 0.5:
        notes.append("엔트로피 매우 낮음 — 한두 색 지배. 회귀 표본으로는 외곽치.")

    return Rationale(
        summary=summary,
        band=band,
        axis=axis_text,
        intent=_intent(key, target, spec.num_colors),
        key_feature=key,
        achieved=_achieved_summary(target, achieved_dict, key),
        expected_play=_expected_play(calibration),
        skill_trained=_skill(key, spec.num_colors),
        notes=notes,
        formulas=_make_formulas(spec),
        patterns=_make_patterns(spec),
    )


# --- LLM upgrade hook (future) -------------------------------------------
#
# When richer prose is desired, replace `make_rationale` with a wrapper
# that:
#   1. Calls `make_rationale` to obtain the deterministic baseline.
#   2. Sends (spec, features, calibration, baseline) to Claude with a
#      system prompt asking for a single-paragraph designer note in
#      Korean, returning JSON.
#   3. Merges LLM prose into the `intent` field, keeping all other
#      structured fields deterministic.
# This keeps reproducibility on the data and only the narrative becomes
# stochastic.
