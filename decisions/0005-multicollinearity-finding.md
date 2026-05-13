# ADR 0005 — 100레벨 회귀 후 발견: shot_pressure ≈ -density (다중공선성)

- **상태**: 확정 (실험 후 보정 결정)
- **일자**: 2026-05-06
- **선행 결정**: [ADR 0003 — 6차원 벡터](0003-feature-vector.md)

---

## 맥락

100개 생성 레벨에서 6차원 벡터로 `clear_rate`/`EAC`를 회귀했더니
- 15레벨 파일럿의 R² 0.85 → 100레벨에서 **R² 0.22~0.29**로 급락
- `density` 계수와 `shot_pressure` 계수가 *둘 다 음수*인데 의미가 충돌
  ("밀도 ↑ 어려움" + "압박 ↑ 어려움" — 둘이 동시에 어려움 방향?)

상관계수를 직접 계산: **corr(density, shot_pressure) = −0.976**.
즉 *거의 완벽한 음의 상관*. 다중공선성 폭발.

원인:
- `shot_pressure = shots_remaining / occupied_count`
- `shots_remaining`은 14로 고정, `occupied_count = density × total_cells`
- 따라서 `shot_pressure ≡ 14 / (density × cells)`, 즉 **density의 역수**.
- ADR 0003은 "두 차원이 서로 독립"이라고 판단했지만, **shots_remaining이 고정**된 상황에서는 동일 정보. 가변 shots를 가정한 ADR 0003 논거는 *실제 실험 셋업과 어긋남*.

다른 발견:
- `shot_pressure` 제거 후 재회귀: density 계수도 무너져 0 근처
  → 둘이 합쳐 들고 있던 신호가 *주로 한 차원의 효과였음*을 시사
- `avg_cluster_size`가 가장 안정된 단일 예측 변수로 부상 (clear_rate +0.04~0.06, EAC −2.66)
- StrongBot은 평균 89% 클리어 → **천장 효과**. 어려운 레벨에서만 변별력. 회귀 종속변수로는 weak/medium이 더 적절

## 결정

1. 다음 이터레이션의 **6차원 벡터에서 `shot_pressure`를 제거**한다. 5차원으로 재정의한다 (또는 이를 보충할 새 차원을 추가).
2. 회귀 분석 시 **종속변수는 weak/medium clear_rate 우선**. strong은 difficulty의 상단을 본다고 명시.
3. 100레벨 결과를 *그대로 보존*한다. 포트폴리오의 가치는 *실수까지 정직하게 기록*하는 데 있다.

## 트레이드오프

- 차원을 줄이면 LLM 보조 입력 스키마 변경. 그러나 한 키 제거뿐 — 영향 작다.
- 코드(`features.py`)는 5차원만 계산하도록 즉시 수정 가능. 다만 *지금* 수정하지 않는다 — 100레벨 결과 보존이 우선이고, 이미 모든 보드 JSON에 6차원이 박혀있다.

## 후속

- (선택) shots_remaining을 spec sampling에 변량화 → shot_pressure가 진짜 독립 차원으로 살아남는지 검증.
- (선택) 보드의 *천장 거리 평균*을 shot_pressure 대신 추가 후보로 검토.
- 회귀 R² 0.20대를 *보완*하기 위해, 6차원 외에 *2차 항*(예: density × cluster_size)을 추가 → R² 어디까지 올라가는지 본다.
