# -*- coding: utf-8 -*-
"""Generate a per-level dossier PDF (HTML → Chromium via Playwright).

Input  : `experiments/rationale_v2_smoke/levels/L*.json` (10 levels).
Output : `experiments/rationale_v2_smoke/level_dossier_v2_1.pdf`.

Layout : A4 portrait, 11 pages total.
    p1     — cover (design objective + summary, no applicant info).
    p2..11 — one card per level, two-column:
        left  : board SVG, meta, bot triplet, feature vector
        right : design intent (7 fields), formulas (5), patterns (5)

The cover is project-only — no name, contact, or hiring metadata.
Per user decision 2026-05-13.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent
LEVELS_DIR = ROOT / "experiments" / "rationale_v2_smoke" / "levels"
OUT_HTML = ROOT / "experiments" / "rationale_v2_smoke" / "_level_dossier_preview.html"
OUT_PDF = ROOT / "experiments" / "rationale_v2_smoke" / "level_dossier_v2_1.pdf"


# Board cell palette — mirrors viewer/index.html COLORS.
COLORS = {
    0: None,
    1: "#e15759",
    2: "#4e79a7",
    3: "#59a14f",
    4: "#f28e2b",
    5: "#b07aa1",
    6: "#76b7b2",
    7: "#edc948",
    8: "#9c755f",
}


# Display-layer name mappings for the dossier PDF.
# System keys live in src/bubble/rationale.py — these are presentational only.
FORMULA_KO = {
    "band_classification":       "난이도 등급 분류",
    "color_progression":         "색 가짓수 진행",
    "shot_pressure_formula":     "발사 수 압박",
    "weighted_distance_fitness": "가중 거리 적합도",
    "target_sampling_ranges":    "목표 표본 범위",
}
FORMULA_PLAIN = {
    "band_classification":       "레벨 번호를 10으로 나눈 몫. 0–9 사이 밴드.",
    "color_progression":         "밴드가 올라갈수록 색 가짓수 증가 (3색→7색).",
    "shot_pressure_formula":     "주어진 발사 수 ÷ 보드 위 거품 수. 1에 가까울수록 빠듯.",
    "weighted_distance_fitness": "피처별 (목표−실측)²에 가중치를 곱한 값의 평균. 작을수록 의도와 일치.",
    "target_sampling_ranges":    "5개 피처 각각의 균등분포 U(min, max)에서 무작위로 뽑음.",
}

PATTERN_KO = {
    "two_stage_generation":     "2단계 생성",
    "ceiling_anchor":           "천장 앵커",
    "drop_floating":            "낙하 처리",
    "horizontal_mirror":        "좌우 대칭",
    "bot_triplet_calibration":  "봇 트리오 캘리브레이션",
}

FEATURE_KO = {
    "color_entropy":      "색 분포 균등도",
    "density":            "거품 밀도",
    "shot_pressure":      "발사 수 압박",
    "max_chain_depth":    "최대 연쇄 깊이",
    "floating_potential": "낙하 잠재력",
    "chain_avg_depth":    "평균 연쇄 깊이",
    "avg_cluster_size":   "평균 클러스터 크기",
    "rows":               "행 수",
    "cols":               "열 수",
    "num_colors":         "색 가짓수",
    "shots_remaining":    "주어진 발사 수",
    "total_bubbles":      "거품 총수",
}

BOT_KO = {"weak": "초보 봇", "medium": "중수 봇", "strong": "고수 봇"}


CSS = r"""
@page { size: A4 portrait; margin: 14mm; }

@font-face {
  font-family: "Pretendard";
  font-weight: 400;
  src: local("Malgun Gothic"), local("맑은 고딕"), local("Apple SD Gothic Neo");
}
@font-face {
  font-family: "Pretendard";
  font-weight: 600;
  src: local("Malgun Gothic Bold"), local("맑은 고딕 Bold"), local("Apple SD Gothic Neo Bold");
}

:root {
  --ink-1: #111418;
  --ink-2: #3d434b;
  --ink-3: #6b7280;
  --ink-4: #9aa3af;
  --line-1: #e5e7eb;
  --line-2: #d1d5db;
  --surf-1: #ffffff;
  --surf-2: #f7f8fa;
  --surf-3: #eef1f5;
  --accent: #1f5bd0;
  --formula: #4e79a7;
  --pattern: #59a14f;
}

* { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0;
  font-family: "Pretendard", -apple-system, "Segoe UI", sans-serif;
  color: var(--ink-1);
  font-size: 10pt;
  line-height: 1.5;
}

.page {
  page-break-after: always;
  break-after: page;
}
.page:last-child {
  page-break-after: auto;
  break-after: auto;
}

/* ------------------- COVER ------------------- */
.cover h1 {
  font-size: 22pt;
  margin: 0 0 6px;
  letter-spacing: -0.3px;
}
.cover .subtitle {
  font-size: 11pt;
  color: var(--ink-3);
  margin: 0 0 28px;
}
.cover h2 {
  font-size: 13pt;
  margin: 28px 0 10px;
  border-bottom: 1.5px solid var(--ink-1);
  padding-bottom: 4px;
  letter-spacing: -0.2px;
}
.cover h3 {
  font-size: 10.5pt;
  margin: 16px 0 8px;
  color: var(--ink-2);
}
.cover p {
  margin: 0 0 10px;
  color: var(--ink-2);
}
.cover code {
  background: var(--surf-3);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 9.5pt;
  font-family: "Consolas", "Menlo", monospace;
}
.cover ul {
  margin: 6px 0 0; padding-left: 18px;
  color: var(--ink-2);
}
.cover ul li { margin-bottom: 4px; }
.summary-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 6px;
}
.summary-table th, .summary-table td {
  text-align: left;
  padding: 5px 8px;
  border-bottom: 1px solid var(--line-1);
  font-size: 10pt;
}
.summary-table th {
  color: var(--ink-3); font-weight: 400;
  width: 45%;
}
.summary-table td {
  color: var(--ink-1); font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.bands {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin-top: 4px;
}
.band-row {
  display: flex; justify-content: space-between;
  padding: 5px 10px;
  background: var(--surf-2);
  border-radius: 5px;
  font-size: 9.5pt;
}
.band-name { color: var(--ink-2); }
.band-count { color: var(--ink-1); font-weight: 600; }
.cover .note {
  font-size: 9pt;
  color: var(--ink-3);
  background: var(--surf-2);
  padding: 8px 12px;
  border-left: 3px solid var(--accent);
  border-radius: 4px;
  margin-top: 8px;
}

/* ------------------- LEVEL CARD ------------------- */
.level-card .card-head-block {
  margin-bottom: 10px;
  border-bottom: 1.5px solid var(--ink-1);
  padding-bottom: 6px;
}
.level-card h1 {
  font-size: 15pt;
  margin: 0;
  letter-spacing: -0.2px;
}
.level-card .band-line {
  font-size: 9.5pt;
  color: var(--ink-3);
  margin: 2px 0 0;
}
.two-col {
  display: grid;
  grid-template-columns: 38% 62%;
  gap: 12px;
}
.level-card h3 {
  font-size: 8.5pt;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: var(--ink-3);
  margin: 8px 0 4px;
  font-weight: 600;
}
.level-card h3:first-child { margin-top: 0; }
.board-box {
  text-align: center;
  margin-bottom: 6px;
}
.kv-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 9pt;
}
.kv-table td {
  padding: 3px 0;
}
.kv-table td.k { color: var(--ink-3); }
.kv-table td.v {
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--ink-1);
}
.bots-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 5px;
}
.bot {
  text-align: center;
  background: var(--surf-2);
  border-radius: 5px;
  padding: 6px 4px;
}
.bot-name {
  font-size: 8pt;
  text-transform: uppercase;
  color: var(--ink-3);
  letter-spacing: 0.4px;
}
.bot-clear {
  font-size: 14pt;
  font-weight: 600;
  margin-top: 1px;
  font-variant-numeric: tabular-nums;
}
.bot-eac {
  font-size: 8.5pt;
  color: var(--ink-3);
  font-variant-numeric: tabular-nums;
}

/* design intent (right panel) */
.intent {
  background: linear-gradient(120deg, #eef5ff, #f0f2f8);
  padding: 6px 9px;
  border-radius: 6px;
}
.intent-row {
  display: flex; gap: 6px;
  font-size: 8.4pt;
  padding: 1.5px 0;
  line-height: 1.35;
}
.intent-lbl {
  flex: 0 0 56px;
  color: var(--ink-3);
  font-size: 7.5pt;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  padding-top: 1px;
}
.intent-val { flex: 1; color: var(--ink-1); }

/* method table (compact, replaces method cards for 1-level-per-page layout) */
.method-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 8.2pt;
  line-height: 1.35;
  margin-top: 2px;
  table-layout: fixed;
}
.method-table col.c-name { width: 20%; }
.method-table col.c-body { width: 35%; }
.method-table col.c-why  { width: 45%; }
.method-table td {
  vertical-align: top;
  padding: 2.5px 5px 2.5px 7px;
  border-bottom: 1px solid var(--line-1);
  word-break: keep-all;
  overflow-wrap: anywhere;
}
.method-table tr.formula td { border-left: 2px solid var(--formula); }
.method-table tr.pattern td { border-left: 2px solid var(--pattern); }
.method-table td.name {
  font-weight: 600;
  color: var(--ink-1);
  font-size: 8.4pt;
  word-break: break-all;
}
.method-table td.body {
  color: var(--ink-2);
}
.method-table td.body .plain {
  display: block;
  color: var(--ink-1);
}
.method-table td.body .formula-expr {
  display: block;
  font-family: "Consolas", "Menlo", monospace;
  font-size: 7pt;
  color: var(--ink-4);
  word-break: break-all;
  margin-top: 2px;
}
.method-table td.name .sys {
  display: block;
  font-family: "Consolas", "Menlo", monospace;
  font-size: 6.6pt;
  color: var(--ink-4);
  font-weight: 400;
  letter-spacing: 0;
  margin-top: 1px;
  word-break: break-all;
}
.method-table td.why {
  color: var(--ink-1);
}
.method-section-head {
  display: flex; align-items: baseline; gap: 6px;
  font-size: 8.5pt;
  font-weight: 600;
  color: var(--ink-2);
  margin: 8px 0 3px;
  letter-spacing: 0.2px;
}
.method-section-head:first-child { margin-top: 0; }
.method-section-head .pill {
  font-size: 6.8pt;
  padding: 1px 6px;
  border-radius: 8px;
  color: #fff;
  letter-spacing: 0.3px;
}
.method-section-head .pill.formula { background: var(--formula); }
.method-section-head .pill.pattern { background: var(--pattern); }
.method-section-head .colhint {
  margin-left: auto;
  font-size: 6.8pt;
  font-weight: 400;
  color: var(--ink-4);
  letter-spacing: 0.3px;
}

/* HTML 측정상 카드는 268mm 이하지만 PDF print 렌더에선 1-3mm 추가됨. */
/* 가드 없이 두면 일부 레벨이 다음 페이지로 흘러 14페이지가 됨. */
.level-card { max-height: 269mm; overflow: hidden; }
"""


def load_levels() -> list[dict]:
    return [
        json.load(open(p, encoding="utf-8"))
        for p in sorted(LEVELS_DIR.glob("L*.json"))
    ]


def board_svg(board: dict, size: int = 300) -> str:
    rows = board["rows"]
    cols = board["cols"]
    cells = board["cells"]
    padding = 6
    w = size - padding * 2
    h = size - padding * 2
    r1 = w / (cols * math.sqrt(3))
    r2 = h / (1.5 * rows + 0.5)
    r = min(r1, r2)
    dx = math.sqrt(3) * r
    dy = 1.5 * r

    parts = [f'<svg width="{size}" height="{size}" '
             f'xmlns="http://www.w3.org/2000/svg" '
             f'style="background:#f0f2f8;border-radius:6px">']
    for row in range(rows):
        row_cells = cells[row] if row < len(cells) else []
        offset = dx / 2 if (row & 1) else 0
        for col, val in enumerate(row_cells):
            cx = padding + dx / 2 + col * dx + offset
            cy = padding + r + row * dy
            pts = []
            for i in range(6):
                a = math.pi / 6 + i * math.pi / 3
                pts.append(f"{cx + r * math.cos(a):.1f},"
                           f"{cy + r * math.sin(a):.1f}")
            color = COLORS.get(val)
            if color:
                parts.append(f'<polygon points="{" ".join(pts)}" '
                             f'fill="{color}" stroke="rgba(0,0,0,0.15)" '
                             f'stroke-width="0.6"/>')
            else:
                parts.append(f'<polygon points="{" ".join(pts)}" '
                             f'fill="none" stroke="rgba(0,0,0,0.07)" '
                             f'stroke-width="0.5"/>')
    parts.append("</svg>")
    return "".join(parts)


def make_summary(levels: list[dict]) -> dict:
    bands: dict[str, int] = {}
    weak, medium, strong = [], [], []
    for j in levels:
        r = j.get("rationale", {})
        band = r.get("band", "—").split(":", 1)[-1].strip() if r.get("band") else "—"
        bands[band] = bands.get(band, 0) + 1
        bots = j.get("bots", {})
        if "weak" in bots: weak.append(bots["weak"]["clear_rate"])
        if "medium" in bots: medium.append(bots["medium"]["clear_rate"])
        if "strong" in bots: strong.append(bots["strong"]["clear_rate"])
    return {
        "count": len(levels),
        "bands": bands,
        "weak_avg": statistics.mean(weak) if weak else 0.0,
        "medium_avg": statistics.mean(medium) if medium else 0.0,
        "strong_avg": statistics.mean(strong) if strong else 0.0,
    }


def render_cover(summary: dict) -> str:
    bands_html = "".join(
        f'<div class="band-row"><span class="band-name">{name}</span>'
        f'<span class="band-count">{cnt}레벨</span></div>'
        for name, cnt in summary["bands"].items()
    )
    return f"""
    <section class="page cover">
      <h1>AI 활용 버블슈터 레벨 디자인</h1>
      <p class="subtitle">절차적 생성 + 봇 시뮬레이션 + 룰베이스 설명 자동화 — 10레벨 카드</p>

      <h2>설계 목적</h2>
      <p>
        버블슈터 레벨을 디자이너의 의도(목표 측정 지표)로부터 절차적으로 생성하고,
        초보·중수·고수 세 봇으로 난이도를 계측하며,
        각 레벨에 적용된 <strong>공식·패턴·디자인 의도</strong>를 자동으로 문서화하는
        파이프라인의 산출물이다.
      </p>
      <p>
        본 묶음은 <code>rationale v2.1</code> 사이클의 10레벨 스모크 결과로,
        각 레벨이 어떤 공식과 패턴으로 만들어졌고 어떤 디자인 의도를 담는가를
        코드를 열지 않고 추적할 수 있도록 카드 형식으로 정리한 것이다.
      </p>

      <h2>구성 요약</h2>
      <table class="summary-table">
        <tr><th>총 레벨 수</th><td>{summary["count"]}레벨</td></tr>
        <tr><th>대칭 축</th><td>모두 좌우 대칭</td></tr>
        <tr><th>초보 봇 평균 클리어율</th><td>{summary["weak_avg"]*100:.0f}%</td></tr>
        <tr><th>중수 봇 평균 클리어율</th><td>{summary["medium_avg"]*100:.0f}%</td></tr>
        <tr><th>고수 봇 평균 클리어율</th><td>{summary["strong_avg"]*100:.0f}%</td></tr>
      </table>

      <h3>밴드 분포</h3>
      <div class="bands">{bands_html}</div>

      <h2>각 레벨 카드의 구성</h2>
      <ul>
        <li><strong>좌측 패널</strong>: 보드 시각화, 레벨 메타(씨드·행·열·색·발사 수),
            봇 캘리브레이션, 6차원 측정 지표(피처 벡터), 디자인 의도(7필드).</li>
        <li><strong>우측 패널</strong>: 적용된 공식 5개, 적용된 패턴 5개. 각 항목은 한국어 이름·시스템 키·자연어 풀이·수식·왜 5개 정보를 한 행에 담는다.</li>
      </ul>
      <p class="note">
        각 공식·패턴 항목의 <em>왜</em> 필드는 ADR(0004·0005·0006·0007·0008)에서 인용 —
        시스템의 결정 근거가 매 레벨 카드에 박혀 있다.
      </p>
    </section>
    """


def _compact_formula(expr: str, cap: int = 72) -> str:
    """Trim list-style formulas at a comma boundary, preserving math expressions."""
    if len(expr) <= cap:
        return expr
    head = expr[:cap]
    last_sep = max(head.rfind(","), head.rfind(";"))
    if last_sep > cap * 0.5:
        head = head[:last_sep]
    return head.rstrip() + " …"


def _fmt_num(x) -> str:
    if x is None: return "—"
    if isinstance(x, bool): return str(x)
    if isinstance(x, int): return str(x)
    if isinstance(x, float):
        return "—" if not math.isfinite(x) else f"{x:.3f}"
    return str(x)


def render_level_card(j: dict) -> str:
    rationale = j.get("rationale", {})
    spec = j.get("spec", {})
    bots = j.get("bots", {})
    features = j.get("features", {})
    board = j["board"]

    svg = board_svg(board, size=270)

    meta_rows = [
        ("씨드", j.get("board", {}).get("seed", "—")),
        ("행 × 열", f'{board["rows"]} × {board["cols"]}'),
        ("색 가짓수", board.get("num_colors", "—")),
        ("발사 수", board.get("shots_remaining", "—")),
        ("대칭", spec.get("symmetry_axis", "—")),
    ]
    meta_html = "".join(
        f'<tr><td class="k">{k}</td><td class="v">{v}</td></tr>'
        for k, v in meta_rows
    )

    bots_html = ""
    for name in ("weak", "medium", "strong"):
        b = bots.get(name)
        if not b: continue
        eac = b.get("eac")
        eac_str = (f"{eac:.1f}" if isinstance(eac, (int, float))
                   and math.isfinite(eac) else "—")
        bots_html += (
            f'<div class="bot">'
            f'<div class="bot-name">{BOT_KO.get(name, name)}</div>'
            f'<div class="bot-clear">{b["clear_rate"]*100:.0f}%</div>'
            f'<div class="bot-eac">평균 {eac_str}발</div>'
            f'</div>'
        )

    feat_rows = "".join(
        f'<tr><td class="k">{FEATURE_KO.get(k, k)}</td>'
        f'<td class="v">{_fmt_num(v)}</td></tr>'
        for k, v in features.items()
    )

    intent_pairs = [
        ("레벨대", rationale.get("band", "—")),
        ("대칭", rationale.get("axis", "—")),
        ("의도", rationale.get("intent", "—")),
        ("핵심차원", rationale.get("key_feature", "—")),
        ("타겟대비", rationale.get("achieved", "—")),
        ("예상플레이", rationale.get("expected_play", "—")),
        ("훈련스킬", rationale.get("skill_trained", "—")),
    ]
    intent_html = "".join(
        f'<div class="intent-row">'
        f'<div class="intent-lbl">{lbl}</div>'
        f'<div class="intent-val">{val}</div>'
        f'</div>' for lbl, val in intent_pairs
    )

    formulas_rows = "".join(
        f'<tr class="formula">'
        f'<td class="name">{FORMULA_KO.get(f["name"], f["name"])}'
        f'<span class="sys">{f["name"]}</span></td>'
        f'<td class="body">'
        f'<span class="plain">{FORMULA_PLAIN.get(f["name"], f["function"])}</span>'
        f'<span class="formula-expr">{_compact_formula(f["formula"])}</span></td>'
        f'<td class="why">{f["why"]}</td>'
        f'</tr>'
        for f in rationale.get("formulas", [])
    )

    patterns_rows = "".join(
        f'<tr class="pattern">'
        f'<td class="name">{PATTERN_KO.get(p["name"], p["name"])}'
        f'<span class="sys">{p["name"]}</span></td>'
        f'<td class="body">{p["effect"]}</td>'
        f'<td class="why">{p["why"]}</td>'
        f'</tr>'
        for p in rationale.get("patterns", [])
    )

    formulas_html = (
        '<table class="method-table">'
        '<colgroup><col class="c-name"><col class="c-body"><col class="c-why"></colgroup>'
        f'<tbody>{formulas_rows}</tbody></table>'
    )
    patterns_html = (
        '<table class="method-table">'
        '<colgroup><col class="c-name"><col class="c-body"><col class="c-why"></colgroup>'
        f'<tbody>{patterns_rows}</tbody></table>'
    )

    return f"""
    <section class="page level-card">
      <div class="card-head-block">
        <h1>{j["level_id"]} — {rationale.get("summary", "")}</h1>
        <p class="band-line">{rationale.get("band", "")}</p>
      </div>
      <div class="two-col">
        <div class="col-left">
          <div class="board-box">{svg}</div>
          <h3>레벨 메타</h3>
          <table class="kv-table">{meta_html}</table>
          <h3>봇 캘리브레이션</h3>
          <div class="bots-row">{bots_html}</div>
          <h3>측정 지표 (피처 벡터)</h3>
          <table class="kv-table">{feat_rows}</table>
          <h3>디자인 의도</h3>
          <div class="intent">{intent_html}</div>
        </div>
        <div class="col-right">
          <div class="method-section-head">
            <span class="pill formula">공식</span>적용된 공식 5
            <span class="colhint">이름 · 풀이 + 수식 · 왜 (ADR)</span>
          </div>
          {formulas_html}
          <div class="method-section-head">
            <span class="pill pattern">패턴</span>적용된 패턴 5
            <span class="colhint">이름 · 효과 · 왜 (ADR)</span>
          </div>
          {patterns_html}
        </div>
      </div>
    </section>
    """


def build_html(levels: list[dict]) -> str:
    summary = make_summary(levels)
    pages = render_cover(summary)
    for j in levels:
        pages += render_level_card(j)
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<title>Level Dossier</title><style>{CSS}</style></head>'
            f'<body>{pages}</body></html>')


def main() -> None:
    levels = load_levels()
    if not levels:
        raise SystemExit(f"No levels found in {LEVELS_DIR}")
    html = build_html(levels)
    OUT_HTML.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(OUT_HTML.as_uri())
        page.pdf(
            path=str(OUT_PDF),
            format="A4",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        browser.close()

    size_kb = OUT_PDF.stat().st_size / 1024
    print(f"PDF 생성: {OUT_PDF} ({size_kb:.1f} KB, {len(levels) + 1}페이지)")


if __name__ == "__main__":
    main()
