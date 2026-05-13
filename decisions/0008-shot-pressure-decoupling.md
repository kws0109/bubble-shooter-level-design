# ADR 0008 — `shot_pressure`를 디자이너 노브로 격상 (다중공선성 직교화)

- **상태**: 확정
- **일자**: 2026-05-06
- **선행 결정**: [ADR 0005](0005-multicollinearity-finding.md), [ADR 0006](0006-iteration-2-spec.md), [ADR 0007](0007-floating-and-rationale.md)

---

## 맥락

iter3 회귀에서 `corr(density, shot_pressure) = -0.780`. 여전히 강한 다중공선성. 원인:

- `shot_pressure = shots / occupied_count`
- `occupied_count ≈ density × total_cells`
- iter3까지 `shots = 12 + 2 × (num_colors − 2)` — *num_colors 그룹별 고정*
- 같은 그룹 내에서 `shots`가 상수 → `shot_pressure ≈ k / density`

이 구조적 anti-correlation은 *데이터에 들어간 후엔 풀리지 않음*. 회귀 단계에서 ridge나 VIF로 *해석*은 가능해도 *추정 분산 자체*는 그대로.

## 결정

**`shot_pressure`를 직접 샘플링 → `shots`는 도출**.

```python
density       ~ U(0.35, 0.65)         # 보드 밀도
shot_pressure ~ U(0.30, 0.65)         # 발사 자원 풍요/궁핍
shots = round(density × total_cells × shot_pressure)
```

두 값이 *독립 uniform*에서 추출되므로 모집단 단계에서 상관 0. 표본에서는 약간의 편차가 있겠지만 -0.78 같은 강한 상관은 사라진다.

`num_colors`는 여전히 `level_index`로 결정 (난이도 진행). 이제:
- **density**: 보드의 *공간 압박*
- **shot_pressure**: 디자이너의 *발사 자원 디자인 의도*  
- **num_colors**: *난이도 단계*

세 차원이 모두 직교적인 디자이너 노브로 정리.

## 근거

1. **수학적 정합성**: 다중공선성을 *데이터 생성 단계에서* 끊는 게 정석. 사후 분해(VIF/ridge)는 해석 도구일 뿐.
2. **디자인 표현력 ↑**: 기존엔 "shots는 colors가 정함"으로 디자이너 통제 불가. 이제 "후반 레벨인데 일부러 발사 풍요롭게 줘서 콤보 화려함을 과시" 같은 의도가 가능.
3. **회귀 안정성**: density와 shot_pressure 계수가 *각자 의미*를 가짐. 더 이상 신호를 반반 나눠 들지 않음.

## 트레이드오프

- shots 범위가 벌어짐: density 0.35×cells×shot_pressure 0.30 = ~8, density 0.65×cells×shot_pressure 0.65 = ~34. 8발은 간혹 빠듯할 수 있음. 모니터링.
- 후반 레벨(7색)에 우연히 shots=10이 걸리면 봇 클리어율 폭락. spec sampling에 *level별 floor* 추가 가능 (옵션, 확장 시).
- 기존 결과(iter1~iter3)와 직접 비교 어려움 → 비교 시 통제변수로 num_colors와 shots 동시 보정 필요.

## 검증 계획

100레벨 풀 배치 *전에* **10레벨 스모크**로 안정성 확인:
- 각 10레벨 band에서 mid-band 인덱스 1개 (L4, L14, ..., L94 = 10레벨)
- 측정: `corr(density, shot_pressure)`, 봇 클리어율 분포, shots 범위
- 통과 시 100레벨 배치 (iter4)
- iter3 산출물은 `levels_iter3/`, `reports_iter3/`로 보존

## 후속

- 통과 시 iter4 (n=100) 실시.
- 실패(여전히 강한 상관 / shots 너무 빠듯 / 봇 결과 깨짐) 시 ADR 0009로 보정.
