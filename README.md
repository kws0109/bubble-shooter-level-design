# Bubble Shooter Level Design Pipeline

버블슈터 레벨 디자인 자동화 파이프라인. 절차적 생성기 + 봇 시뮬레이션 + LLM 디자인 보조 + 룰베이스 설명 자동화로 *"디자이너의 의도"*를 시스템으로 다룬다.

> **포트폴리오 본문**: [`PORTFOLIO.md`](PORTFOLIO.md) — 메인 내러티브 문서.

---

## 빠른 둘러보기

```text
generator.py    →  보드 디자인 (시드+성장 → (1+1) 진화)
features.py     →  6차원 설명 변수 계산
solver.py       →  weak/medium/strong 봇 트리플렛 → EAC + clear_rate
analytics.py    →  100레벨 일괄 + OLS 회귀
ai_designer.py  →  LLM 디자인 보조 (Claude API + 모킹 폴백)
rationale.py    →  적용된 공식·패턴 자동 추출
viewer/         →  HTML5 캔버스 뷰어
```

## 실행

```bash
# 의존성
pip install numpy matplotlib playwright pymupdf
playwright install chromium

# 단일 레벨 생성 (smoke)
python scripts/smoke_generate.py
python scripts/smoke_solver.py
python scripts/smoke_designer.py

# 100레벨 일괄 생성 + 회귀 + 차트
python scripts/generate_batch.py 100

# 레벨 도시에 PDF 생성 (10레벨 스모크 기반)
python scripts/generate_level_dossier.py

# 결과 확인: 브라우저로 viewer/index.html 열기
```

## 디자인 결정 ADR

- [`decisions/0002-difficulty-definition.md`](decisions/0002-difficulty-definition.md) — 난이도 = 봇 EAC(스칼라) + 6차원 벡터(설명)
- [`decisions/0003-feature-vector.md`](decisions/0003-feature-vector.md) — 6차원 차원 선정 근거
- [`decisions/0004-generator-strategy.md`](decisions/0004-generator-strategy.md) — 생성기 = 시드+성장 → (1+1) 진화
- [`decisions/0005-multicollinearity-finding.md`](decisions/0005-multicollinearity-finding.md) — 100레벨 회귀 후 발견된 다중공선성
- [`decisions/`](decisions/) — 전체 ADR 목록

## 실험 로그

- [`experiments/`](experiments/) — 실험·튜닝 시도 기록
