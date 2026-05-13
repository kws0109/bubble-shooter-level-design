# ADR 0009 — Alternating row widths (홀수 행 10, 짝수 행 9)

- **상태**: 확정
- **일자**: 2026-05-06
- **선행 결정**: [ADR 0007](0007-floating-and-rationale.md), [ADR 0008](0008-shot-pressure-decoupling.md)

---

## 맥락

iter4 스모크의 좌우 대칭 레벨이 viewer에서 *비대칭으로* 보임. 원인:

기존 레이아웃은 모든 행이 `cols`(예: 10) 셀을 가지면서 홀수 행만 시각적으로 반 셀 우측 시프트. 결과:
- 짝수 행 cell 9의 우측 끝: x = 9
- 홀수 행 cell 9의 우측 끝: x = 9.5  ← 직사각형 경계 밖

미러 축이 각 행에서 다르게 위치하게 됨. mirror(c) = cols-1-c는 *셀 인덱스* 미러일 뿐 *시각 미러*가 아님.

표준 버블슈터(Bubble Pop Origin, Frozen Bubble, Snood) 레이아웃은:
- 짝수 행: `cols` 셀 (예: 10)
- 홀수 행: `cols - 1` 셀 (예: 9)
- 두 행이 직사각형 경계 안에서 *세로축에 대해 진짜 대칭*

## 결정

**행별 가변 폭** 도입. 행 r의 셀 개수:
```
row_width(r) = cols      if r % 2 == 0    # 짝수 코드 인덱스 = "홀수번째" 표시 = 넓음
row_width(r) = cols - 1  if r % 2 == 1    # 홀수 코드 인덱스 = "짝수번째" 표시 = 좁음
```

영향:
- `Board.cells`: 행마다 길이가 다름 (`cells[r]` 길이 = `row_width(r)`)
- `Board.in_bounds`, `valid_shot_positions`: 폭 인지
- `Board.neighbors`: 정통 hex 인접 6방향 (행 폭에 따라 위/아래 인덱스 다름)
- `Board.total_cells`: 행 폭 합 (8행 기준 76, 기존 80)
- `_mirror_positions(horizontal)`: `mirror_col = row_width(r) - 1 - c`

미러 축 좌표:
- 짝수 행 (10셀, x=0..9): 축 = 4.5
- 홀수 행 (9셀, x=0.5..8.5): 축 = (0.5 + 8.5)/2 = 4.5  ✓

모든 행에서 축이 같아 *진짜 시각 대칭*.

## 트레이드오프

- 기존 4개 배치(iter1~iter3, iter4_smoke v1)와 호환 안 됨. JSON 셀 폭이 다름.
  → viewer는 `cells[r].length`를 셀 카운트로 사용해 *둘 다 렌더링* 가능. 이전 배치는 이전 모습 그대로 보존.
- 코드 변경 범위: Board의 거의 전 메서드. 그러나 *하부 모델 한 곳*만 바뀌고 features/generator/solver는 자동 따라옴.
- 8x10 보드: 80 → 76 셀 (5% 감소). density·shots 자동 재계산.

## 후속

- iter4 스모크를 새 레이아웃으로 재생성 후 시각 확인.
- 통과 시 100레벨 본 배치.
- 이전 4개 배치는 *이전 형식 그대로* 보존하여 viewer에서 비교 가능.
