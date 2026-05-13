# ADR 0007 — 부유 셀 금지 + 좌우 대칭 only + 레벨별 Rationale

- **상태**: 확정
- **일자**: 2026-05-06
- **선행 결정**: [ADR 0006](0006-iteration-2-spec.md)

---

## 맥락

iter2 strict 배치(b7dbbcaru)의 L008을 보던 중 **고립된 부유 셀**(천장과 연결 안 된 단일 버블)이 발견됨. 게임의 가장 기본 규칙 — *"버블은 천장 또는 다른 버블에 연결되어야 한다"* — 위반.

원인 추적:
1. **Stage 1 시드**가 row 0에 앵커되지 않음 → 임의 위치에 시드를 두면 자연 부유.
2. **Stage 2 변형**이 천장과 연결 끊는 셀을 비울 수 있음. 변형 후 부유 정리 없음.
3. **상하 대칭 (vertical mirror)**: 정의상 바닥 절반은 천장과 연결 불가 → *모두 부유*. 좌우 대칭은 row 0 앵커가 좌우 미러 수직축을 따라 이어지지만, 상하 미러는 연결성을 깨뜨림.

또한 디자이너 피드백:
> "각 레벨 디자인의 배치 시 Why에 대한 내용을 같이 작성할 수 있도록 변경"

— 레벨마다 *디자인 의도*를 자동 생성·저장.

## 결정

### #1 시드 앵커링
Stage 1의 모든 시드는 **row 0에만 배치**. 좌우 대칭 시 canonical 영역도 (0, 0..(cols+1)//2-1)로 한정.

### #2 자동 부유 제거
- Stage 1 종료 시 `Board.drop_floating()` 1회 (방어).
- Stage 2 변형 직후 매번 `drop_floating()` 호출 → fitness는 *playable* 상태로 평가.

### #3 좌우 대칭 only
상하 대칭은 게임 물리와 충돌 → 폐기. `analytics.sample_specs`는 axis ∈ {horizontal, none} 만 사용.

### #4 레벨별 Rationale 자동 생성
새 모듈 `src/bubble/rationale.py`. 입력: `(spec, achieved_features, calibration, level_index, axis)`. 출력: 디자이너 노트 형태의 dict (summary / band / axis / intent / key_feature / achieved / expected_play / skill).
- 룰베이스 (deterministic, 재현 가능)
- 각 레벨 JSON의 `rationale` 필드에 저장
- viewer에 panel 추가

## 트레이드오프

- **상하 대칭 손실**: 시각 변동성 일부 감소. 좌우 대칭과 비대칭의 혼합으로 보완.
- **시드 row 0 제한**: 보드 모양이 *위에서 아래로* 자라는 표준 패턴으로 일관됨 — 이는 *결점이 아니라 라이브 게임 표준*.
- **fitness 평가 비용 +5%**: 매 변형마다 floating BFS 추가. 무시할 만한 수준.

## 후속

- `tests/test_connectivity.py`: 모든 생성 보드의 `floating_cells()` == ∅ 검증.
- iter2 strict v2 → **iter3 (post-fix)**로 재배치. 이전 배치는 `levels_iter2_strict_v2/`로 보존.
- viewer에 Rationale 패널 추가.
