# ADR 0010 — 레벨 진행에 따른 행 수 확장 (Vertical only)

- **상태**: 결정 (구현 대기)
- **일자**: 2026-05-06
- **선행 결정**: [ADR 0006](0006-iteration-2-spec.md), [ADR 0008](0008-shot-pressure-decoupling.md), [ADR 0009](0009-alternating-row-widths.md)

---

## 맥락

색 진행(ADR 0006)과 shot_pressure 직교화(ADR 0008)에 더해, 디자이너 피드백:

> "레벨이 늘어나면 사용 가능한 칸 수를 늘리는건 어떨까? Horizontal 말고 Vertical로만 늘어나게 해서 난이도와 플레이 시간을 더 늘릴 수 있을 것 같은데."

## 결정 (Option A — 결정적 밴드)

`cols = 10` 고정. `rows`를 level_index에 따라 단조 증가.

```python
rows = min(6 + level_index // 10, 10)
```

| 레벨대 | rows | total_cells | colors |
|---|---|---|---|
| L1–10  | 6  | 57 | 2~3 |
| L11–20 | 7  | 67 | 3~4 |
| L21–30 | 8  | 76 | 4~5 |
| L31–40 | 9  | 86 | 5~6 |
| L41+   | 10 | 95 | 6~7 |

## 근거

1. **3축 난이도 곡선** — 색·발사·공간이 함께 진행. 라이브 게임의 정석 페이싱.
2. **자동 연동** — `shots = round(density × total_cells × shot_pressure)`이므로 발사 수도 함께 증가. 추가 공식 불필요.
3. **밴드 구조 일관성** — colors와 같은 `level_index // 10` 공식. 디자이너가 한 밴드에서 색·행·shots를 동시 추론 가능.

## 트레이드오프

- 봇 계산 비용 ~선형 증가 → 100레벨 배치 ~95분 → ~130분 예상.
- viewer canvas는 동적 크기 조정 필요 (작은 보드의 셀이 너무 작아지지 않게).

## 후속 (내일 진행)

1. `analytics.sample_specs`에 `rows = min(6 + level_index // 10, 10)` 한 줄 추가.
2. viewer 캔버스 높이 동적 계산 (rows 기반).
3. 10레벨 스모크 — mid-band 인덱스로 6/7/8/9/10 행을 모두 검증.
4. 통과 시 100레벨 본 배치 (iter4) — 첫 *완전한* 배치가 됨 (ADR 0006~0010 모두 적용).
