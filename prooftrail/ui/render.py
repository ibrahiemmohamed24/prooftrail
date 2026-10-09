"""HTML for the static ProofTrail UI.

Every value that comes from the evidence passes through ``_e`` before it reaches
a page. Colors belong to the tokens in ``assets/prooftrail.css``: this module
names semantic classes such as ``badge--contradicted`` and never writes a color.
"""
from __future__ import annotations

import html
import json
import re
from typing import Any

from .model import CaseView, MetricRow, Overview, Site

ICON_PATHS = {
    "check": '<path d="M3.5 8.5l3 3 6-6.5"/>',
    "cross": '<path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/>',
    "alert": '<path d="M8 4.5v4.5M8 11.5v.5"/>',
    "warning": '<path d="M8 2.5l6 10.5H2z"/><path d="M8 6.5v3M8 11.3v.2"/>',
    "info": '<circle cx="8" cy="8" r="5.5"/><path d="M8 7.2v3.6M8 5v.2"/>',
    "up": '<path d="M8 12.5v-9M4.5 7L8 3.5 11.5 7"/>',
    "down": '<path d="M8 3.5v9M4.5 9L8 12.5 11.5 9"/>',
    "overview": (
        '<rect x="2.5" y="2.5" width="4.5" height="4.5" rx="1"/>'
        '<rect x="9" y="2.5" width="4.5" height="4.5" rx="1"/>'
        '<rect x="2.5" y="9" width="4.5" height="4.5" rx="1"/>'
        '<rect x="9" y="9" width="4.5" height="4.5" rx="1"/>'
    ),
    "cases": '<path d="M6 4h7.5M6 8h7.5M6 12h7.5"/><path d="M2.5 4h1M2.5 8h1M2.5 12h1"/>',
    "menu": '<path d="M2.5 4h11M2.5 8h11M2.5 12h11"/>',
    "copy": (
        '<rect x="5.5" y="5.5" width="8" height="8" rx="1.5"/>'
        '<path d="M10.5 5.5V4A1.5 1.5 0 0 0 9 2.5H4A1.5 1.5 0 0 0 2.5 4v5A1.5 1.5 0 0 0 4 10.5h1.5"/>'
    ),
    "print": '<path d="M4.5 6V2.5h7V6"/><path d="M4.5 11.5h-2v-5h11v5h-2"/><rect x="4.5" y="9" width="7" height="4.5"/>',
    "back": '<path d="M9.5 4L5.5 8l4 4"/>',
    "jump": '<path d="M3.5 8h9M9 4.5L12.5 8 9 11.5"/>',
}

STATUS_STYLE = {
    "SUPPORTED": ("supported", "check"),
    "CONTRADICTED": ("contradicted", "cross"),
    "UNVERIFIABLE": ("unverifiable", "alert"),
}

REVIEW_TEXT = {
    "APPROVE": "Human-verified, approved",
    "AMEND": "Human-verified, amended",
    "ABSTAIN": "Human abstained",
}

NAV = (
    ("overview", "Overview", "index.html", "overview"),
    ("cases", "Cases", "cases.html", "cases"),
    ("audit", "New audit", "audit.html", "check"),
    ("benchmark", "Benchmark", "benchmark.html", "overview"),
    ("integrations", "Integrations", "integrations.html", "jump"),
)

NO_CLAIMS_LI = '<li class="muted">No claims were extracted from the final report.</li>'
NO_CLAIMS_ROW = '<tr><td colspan="6">No claims were extracted from the final report.</td></tr>'
NO_EVIDENCE_ROW = '<tr><td colspan="5">No ledger event is cited by any claim.</td></tr>'
NO_STATE_ROW = '<tr><td colspan="4">No state fields were recorded for this event.</td></tr>'


def render_new_audit() -> str:
    body = (
        '<header class="page-head"><p class="eyebrow">Bring your own evidence</p>'
        '<h1>Audit a new trace</h1><p class="lede">Compare a refund agent’s final report with its sealed ledger. '
        'No model calls. No saved uploads. No changes to the frozen benchmark.</p></header>'
        '<section class="table-card audit-workspace"><h2>Upload evidence</h2>'
        '<p>Use a schema-v1 case.json containing trace and ledger, or paste that JSON below. '
        'Maximum 2 MiB / 2,000 ledger events. This auditor supports the existing refund-domain contract, not arbitrary agent workflows.</p>'
        '<p><label for="evidence-file">JSON evidence file</label></p>'
        '<input id="evidence-file" type="file" accept=".json,application/json" data-evidence-file>'
        '<p><label for="evidence-json">Evidence JSON</label></p>'
        '<textarea id="evidence-json" rows="12" spellcheck="false" data-evidence-json placeholder="Paste trace + ledger JSON here"></textarea>'
        '<div class="audit-actions"><button class="btn btn--primary" type="button" data-audit-submit>Run audit</button>'
        '<button class="btn btn--ghost" type="button" data-audit-example>Load frozen example</button></div>'
        '<p role="status" aria-live="polite" data-audit-status>Requires the local application: python -m prooftrail.web</p>'
        '<noscript>JavaScript is required to submit evidence. Use the Python application interface otherwise.</noscript></section>'
        '<section class="table-card audit-workspace" data-audit-result hidden aria-label="Audit result"></section>'
    )
    return _page(title="New audit", description="Audit supplied refund evidence locally.", body=body,
                 root="", active="audit", body_class="page-audit")


def render_benchmark(site: Site) -> str:
    overview = site.overview
    rows = ''.join(f'<tr><th scope="row">{_e(row.label)}</th><td>{_pct(row.proof_trail)}</td>'
                   f'<td>{_pct(row.b1_mean)} ± {_pct(row.b1_stddev)}</td></tr>' for row in overview.metrics)
    report = site.benchmark
    detail = ""
    if report:
        family_rows = []
        for family, value in sorted(report["prooftrail"]["metrics"]["per_family"].items()):
            means = [run["metrics"]["per_family"][family]["accuracy"] for run in report["b1"]["runs"]]
            family_rows.append(f'<tr><th scope="row">{_e(family)}</th><td>{value["total"]}</td><td>{_pct(value["accuracy"])}</td><td>{_pct(sum(means) / len(means))}</td></tr>')
        detail = ('<section class="table-card audit-workspace"><h2>Per-family accuracy</h2><div class="table-wrap">'
                  '<table><thead><tr><th scope="col">Family</th><th scope="col">Cases</th><th scope="col">ProofTrail</th><th scope="col">B1 mean</th></tr></thead>'
                  f'<tbody>{"".join(family_rows)}</tbody></table></div></section>')
        for title, value in (("Repeated-run stability", report["b1"]["stability"]),
                             ("Failure analysis", report["failure_analysis"]),
                             ("Ablation: temporal verifier removed", report["ablations"]["prooftrail_without_temporal_verifier"]["metric_values"])):
            detail += f'<section class="table-card audit-workspace"><h2>{_e(title)}</h2><pre class="json">{_e(json.dumps(value, indent=2))}</pre></section>'
        detail += ('<section class="table-card audit-workspace"><h2>Ablation conclusion</h2>'
                   f'<p>Cases changed without temporal verification: {len(report["ablations"]["changed_cases_without_temporal"])}. '
                   'This dataset does not demonstrate a marginal benefit from that component; no improvement is claimed.</p></section>')
    body = (
        '<header class="page-head"><p class="eyebrow">Frozen, human-reviewed evaluation</p><h1>Benchmark</h1>'
        f'<p class="lede">{overview.case_count} cases across {overview.family_count} families. '
        f'B1 uses the same evidence over {overview.b1_run_count} runs.</p></header>'
        '<section class="table-card audit-workspace"><div class="table-wrap"><table><caption>Measured comparison</caption>'
        '<thead><tr><th scope="col">Metric</th><th scope="col">ProofTrail</th><th scope="col">B1 mean ± population SD</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div></section>'
        + detail + '<section class="table-card audit-workspace"><h2>What these results do not prove</h2>'
        '<p>This is a small, synthetic refund-domain dataset. Variants within a family are correlated. '
        '100% on this benchmark does not mean 100% on new evidence or general-purpose agents. '
        'Evidence coverage is lower than B1 and must not be hidden.</p>'
        '<p>Hash chains detect alteration relative to recorded hashes; they do not authenticate who produced the ledger. '
        'The deterministic extractor can miss unsupported language. No confidence calibration is claimed.</p>'
        '<p><a href="benchmark.json" download>Download the complete comparison JSON</a></p></section>'
    )
    return _page(title="Benchmark", description="Measured outcomes and limitations.", body=body,
                 root="", active="benchmark", body_class="page-benchmark")


def render_integrations() -> str:
    body = (
        '<header class="page-head"><p class="eyebrow">One engine, multiple entry points</p><h1>Integrations</h1>'
        '<p class="lede">Local UI and HTTP API share the same read-only application boundary.</p></header>'
        '<section class="table-card audit-workspace"><h2>No provider needed</h2>'
        '<p>Auditing supplied evidence needs no Gemini, Anthropic or OpenAI account. '
        'Live agent generation remains an optional, separate workflow; never upload credentials in evidence.</p>'
        '<h2>Application contracts</h2><ul><li>audit_trace: trace + sealed ledger → verdict and certificate</li>'
        '<li>verify_ledger: sealed ledger → integrity status and first invalid sequence</li>'
        '<li>list_frozen_cases / get_case: allow-listed, read-only frozen evidence</li>'
        '<li>get_evidence_certificate: original certificate for an allow-listed case</li>'
        '<li>get_benchmark_summary: full recorded benchmark comparison</li></ul>'
        '<h2>HTTP</h2><pre class="json">POST /api/v1/audits\nPOST /api/v1/ledgers/verify\nGET /api/v1/health\n'
        'GET /api/v1/overview\nGET /api/v1/cases\nGET /api/v1/cases/{case_id}\n'
        'GET /api/v1/cases/{case_id}/certificate\nGET /api/v1/benchmark</pre>'
        '<h2>Codex / Claude / Manus</h2><p>A local stdio MCP server is implemented and protocol-tested: '
        'python -m prooftrail.mcp_server (requires the optional mcp extra). '
        'A portable prooftrail-audit skill is included under integrations/skills/. '
        'Host installation is separate; no installed or marketplace plugin is claimed. '
        'Manus connectivity has not been validated.</p>'
        '<p>Local development server only: no remote hosting, user accounts or multi-user access control. '
        'Bind address is intentionally restricted to 127.0.0.1.</p></section>'
    )
    return _page(title="Integrations", description="Local API contracts and integration status.", body=body,
                 root="", active="integrations", body_class="page-integrations")


def _e(value: object) -> str:
    return html.escape("—" if value is None else str(value), quote=True)


def _icon(name: str) -> str:
    return f'<svg class="icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">{ICON_PATHS[name]}</svg>'


def _json_text(value: object) -> str:
    if value is None:
        return "—"
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _copy(value: object) -> str:
    if value is None:
        return ""
    return (
        f'<button class="copy-btn" type="button" data-copy="{_e(value)}">'
        f'{_icon("copy")}<span>Copy</span></button>'
    )


def _badge(status: str, *, large: bool = False) -> str:
    tone, icon = STATUS_STYLE[status]
    size = " badge--lg" if large else ""
    return f'<span class="badge badge--{tone}{size}">{_icon(icon)}<span>{_e(status)}</span></span>'


def _chip(icon: str, text: str, tone: str) -> str:
    return f'<span class="chip chip--{tone}">{_icon(icon)}<span>{_e(text)}</span></span>'


def _chip_list(chips: list[str], label: str, extra: str = "") -> str:
    items = "".join(f"<li>{chip}</li>" for chip in chips)
    return f'<ul class="chip-row {extra}" aria-label="{_e(label)}">{items}</ul>'


def _chain_chip(valid: bool) -> str:
    if valid:
        return _chip("check", "Hash chain valid", "supported")
    return _chip("cross", "Hash chain broken", "contradicted")


def _review_text(action: str | None) -> str:
    return REVIEW_TEXT.get(action or "", "Provisional label")


def _label_chip(action: str | None) -> str:
    if action:
        return _chip("check", _review_text(action), "verified")
    return _chip("info", "Provisional", "neutral")


def _kv(label: str, value: object, *, as_json: bool = False) -> str:
    if as_json:
        shown = f'<pre class="json">{_e(_json_text(value))}</pre>'
    else:
        shown = f'<span class="mono break">{_e(value)}</span>{_copy(value)}'
    return f"<div><dt>{_e(label)}</dt><dd>{shown}</dd></div>"


def _default_claim(case: CaseView) -> str | None:
    """Preselect the first contradicted claim so the case opens on the problem."""
    for claim in case.claims:
        if claim["status"] == "CONTRADICTED":
            return _slug(claim["claim_id"])
    return _slug(case.claims[0]["claim_id"]) if case.claims else None


def _report_segments(report: str, claims: tuple[dict[str, Any], ...]) -> list[tuple[str, dict[str, Any] | None]]:
    """Split the agent's report into plain text and verbatim claim spans."""
    spans: list[tuple[int, int, dict[str, Any]]] = []
    for claim in claims:
        text = claim["claim_text"]
        start = report.find(text) if text else -1
        if start < 0:
            continue
        end = start + len(text)
        if any(start < other_end and other_start < end for other_start, other_end, _ in spans):
            continue
        spans.append((start, end, claim))
    segments: list[tuple[str, dict[str, Any] | None]] = []
    cursor = 0
    for start, end, claim in sorted(spans, key=lambda span: span[0]):
        if start > cursor:
            segments.append((report[cursor:start], None))
        segments.append((report[start:end], claim))
        cursor = end
    if cursor < len(report):
        segments.append((report[cursor:], None))
    return segments


def _render_report(case: CaseView, selected: str | None) -> tuple[str, set[str]]:
    parts: list[str] = []
    matched: set[str] = set()
    for text, claim in _report_segments(case.final_report, case.claims):
        if claim is None:
            parts.append(_e(text))
            continue
        slug = _slug(claim["claim_id"])
        matched.add(slug)
        tone = STATUS_STYLE[claim["status"]][0]
        on = " is-selected" if slug == selected else ""
        parts.append(
            f'<mark class="claim-span claim-span--{tone}{on}" id="span-{slug}" '
            f'data-select-claim="{slug}">{_e(text)}</mark>'
        )
    return "".join(parts), matched


def _page(*, title: str, description: str, body: str, root: str, active: str, body_class: str) -> str:
    nav_items = []
    for key, label, href, icon in NAV:
        current = ' aria-current="page"' if key == active else ""
        nav_items.append(
            f'<li><a href="{root}{href}"{current}>{_icon(icon)}<span class="nav-label">{label}</span></a></li>'
        )
    nav_html = "".join(nav_items)
    sidebar = (
        '<aside class="sidebar no-print" id="sidebar" aria-label="Primary">'
        f'<a class="brand" href="{root}index.html"><span class="brand-mark" aria-hidden="true"></span>'
        '<span class="brand-name">ProofTrail</span></a>'
        '<button class="sidebar-toggle" type="button" data-sidebar-toggle aria-expanded="false" '
        'aria-controls="sidebar">'
        f'{_icon("menu")}<span class="sr-only">Toggle navigation</span></button>'
        f'<nav aria-label="Main"><ul class="nav-list">{nav_html}</ul></nav>'
        '<p class="sidebar-foot">Offline-first evidence<br>No cloud or model calls</p>'
        "</aside>"
    )
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_e(title)} · ProofTrail</title>\n"
        f'<meta name="description" content="{_e(description)}">\n'
        f'<link rel="stylesheet" href="{root}assets/fonts.css">\n'
        f'<link rel="stylesheet" href="{root}assets/prooftrail.css">\n'
        f'<script src="{root}assets/app.js" defer></script>\n'
        f'<script src="{root}assets/control-room.js" defer></script>\n'
        "</head>\n"
        f'<body class="{body_class}">\n'
        '<a class="skip-link" href="#main">Skip to content</a>\n'
        '<div class="app" data-sidebar="collapsed">\n'
        f"{sidebar}\n"
        f'<main id="main" class="main" tabindex="-1">\n{body}\n</main>\n'
        "</div>\n</body>\n</html>\n"
    )


# --------------------------------------------------------------------------- #
# Overview
# --------------------------------------------------------------------------- #
def render_overview(site: Site) -> str:
    overview = site.overview
    cases = site.cases
    valid = sum(case.chain_valid for case in cases)
    example = next((case for case in cases if case.first_bad_event_seq is not None), cases[0])
    if overview.headline_eligible:
        label_chip = _chip("check", f"Human-verified labels {overview.review_accepted}/{overview.review_expected}", "verified")
    else:
        label_chip = _chip("alert", "Provisional labels: not a headline result", "unverifiable")
    chain_text = f"Ledger hash chains valid {valid}/{len(cases)}"
    if valid == len(cases):
        chain_chip = _chip("check", chain_text, "supported")
    else:
        chain_chip = _chip("cross", chain_text, "contradicted")
    status = _chip_list(
        [label_chip, chain_chip, _chip("info", f"ProofTrail model calls: {overview.proof_trail_llm_calls}", "info")],
        "Verification status",
    )
    hero = (
        '<header class="hero">'
        '<p class="eyebrow">Evidence control room for AI agents</p>'
        "<h1>Check what an agent says it did against what the ledger proves</h1>"
        '<p class="tagline">Same evidence. Independent truth. Frozen traces.</p>'
        '<p class="lede">ProofTrail compares each action in an agent\'s final report with an '
        "append-only, hash-chained ledger. Every verdict links to the ledger events that support "
        "or contradict it, and points to the first event where things went wrong.</p>"
        '<div class="actions">'
        f'<a class="btn btn--primary" href="cases.html">Review the {overview.case_count} audited cases</a>'
        f'<a class="btn btn--secondary" href="certificates/{_e(example.case_id)}.html">'
        "Open an example certificate</a>"
        "</div>"
        f"{status}"
        "</header>"
    )
    body = (
        hero
        + _metrics_section(overview)
        + _compare_section(overview)
        + _limits_section(overview)
        + _provenance(overview)
    )
    return _page(
        title="Overview",
        description="ProofTrail checks what an AI agent claims against an append-only ledger.",
        body=body,
        root="",
        active="overview",
        body_class="page-overview",
    )


def _metric_card(metric: MetricRow) -> str:
    delta = (metric.proof_trail - metric.b1_mean) * 100
    if abs(delta) < 0.05:
        icon, direction, text = "info", "level", "Level with B1"
    elif delta > 0:
        icon, direction, text = "up", "up", f"+{delta:.1f} pp vs B1"
    else:
        icon, direction, text = "down", "down", f"-{abs(delta):.1f} pp vs B1"
    return (
        '<article class="metric-card">'
        f'<p class="metric-label">{_e(metric.label)}</p>'
        f'<p class="metric-value">{_pct(metric.proof_trail)}</p>'
        f'<p class="metric-b1">B1 {_pct(metric.b1_mean)} ± {metric.b1_stddev * 100:.1f} pp</p>'
        f'<p class="metric-delta metric-delta--{direction}">{_icon(icon)}<span>{_e(text)}</span></p>'
        "</article>"
    )


def _metrics_section(overview: Overview) -> str:
    cards = "".join(_metric_card(metric) for metric in overview.metrics)
    return (
        '<section class="section" aria-labelledby="metrics-title">'
        '<div class="section-head"><h2 id="metrics-title">ProofTrail against B1</h2>'
        f'<p>Same {overview.case_count} cases and the same evidence. B1 is a one-shot LLM judge, '
        f"averaged over {overview.b1_run_count} runs.</p></div>"
        f'<div class="metric-grid">{cards}</div>'
        "</section>"
    )


def _bar_row(metric: MetricRow) -> str:
    band_start = max(0.0, metric.b1_mean - metric.b1_stddev) * 100
    band_end = min(1.0, metric.b1_mean + metric.b1_stddev) * 100
    return (
        '<li class="bar-row">'
        f'<p class="bar-label">{_e(metric.label)}</p>'
        '<div class="bar-group">'
        '<div class="bar-line"><span class="bar-name">ProofTrail</span>'
        f'<div class="bar bar--pt" style="--value: {metric.proof_trail * 100:.1f}">'
        '<span class="bar-fill"></span></div>'
        f'<span class="bar-value">{_pct(metric.proof_trail)}</span></div>'
        '<div class="bar-line"><span class="bar-name">B1</span>'
        f'<div class="bar bar--b1" style="--value: {metric.b1_mean * 100:.1f}; '
        f'--band-start: {band_start:.1f}; --band-end: {band_end:.1f}">'
        '<span class="bar-fill"></span><span class="bar-band"></span></div>'
        f'<span class="bar-value">{_pct(metric.b1_mean)} ± {metric.b1_stddev * 100:.1f}</span></div>'
        "</div></li>"
    )


def _compare_section(overview: Overview) -> str:
    rows = "".join(_bar_row(metric) for metric in overview.metrics)
    return (
        '<section class="section" aria-labelledby="compare-title">'
        '<h2 id="compare-title">Side by side</h2>'
        '<p class="section-note">Bars show family means over the cases. The light band on each B1 bar '
        "is ±1 population SD across the runs.</p>"
        f'<ul class="bar-list">{rows}</ul>'
        "</section>"
    )


def _limits_section(overview: Overview) -> str:
    coverage = next(metric for metric in overview.metrics if metric.key == "evidence_coverage")
    if coverage.proof_trail < coverage.b1_mean:
        direction = "lower"
    elif coverage.proof_trail > coverage.b1_mean:
        direction = "higher"
    else:
        direction = "equal"
    lines = [
        f"{overview.case_count} synthetic refund-domain cases across {overview.family_count} families. "
        "Nothing here has been tested on other domains.",
        "One author-affiliated human reviewer and no inter-annotator agreement. "
        f"{overview.review_accepted} of {overview.review_expected} decisions accepted, "
        f"{overview.review_amended} amended.",
        f"Evidence coverage is {direction} for ProofTrail ({_pct(coverage.proof_trail)} against "
        f"{_pct(coverage.b1_mean)} for B1). The claim extractor is deterministic and refund-specific, "
        "so wording it does not recognise is marked UNVERIFIABLE instead of guessed.",
        f"The temporal verifier changed {overview.temporal_changed_cases} case outcome(s) on this dataset, "
        "so no gain is claimed for it.",
        "Human time with and without ProofTrail was not measured.",
    ]
    items = "".join(f"<li>{_e(line)}</li>" for line in lines)
    return (
        '<section class="section" aria-labelledby="limits-title">'
        '<h2 id="limits-title">What this does not claim</h2>'
        f'<div class="panel"><ul class="limits">{items}</ul></div>'
        "</section>"
    )


def _provenance(overview: Overview) -> str:
    sha = overview.manifest_sha256
    return (
        '<footer class="provenance">'
        f'<p>Dataset manifest SHA-256 <span class="mono break">{_e(sha)}</span>{_copy(sha)}</p>'
        "<p>Built only from committed files under data/ and evidence/. "
        "No network, no model calls and no timestamps.</p>"
        "</footer>"
    )


# --------------------------------------------------------------------------- #
# Case list
# --------------------------------------------------------------------------- #
def render_cases(site: Site) -> str:
    families: dict[str, str] = {}
    for case in site.cases:
        families.setdefault(case.family_id, case.family_name)
    family_options = "".join(
        f'<option value="{_e(family_id)}">{_e(family_id)} · {_e(name)}</option>'
        for family_id, name in families.items()
    )
    verdict_options = "".join(f'<option value="{status}">{status}</option>' for status in STATUS_STYLE)
    total = len(site.cases)
    rows = "".join(_case_row(case) for case in site.cases)
    head = (
        '<header class="page-head">'
        "<div>"
        '<p class="eyebrow">Audit trail</p>'
        "<h1>Audited cases</h1>"
        f'<p class="lede">{total} cases across {len(families)} families. Each case opens with the '
        "agent's claims, the ledger events and the first harmful event.</p>"
        "</div>"
        '<button class="btn btn--secondary filters-open" type="button" data-open-filters '
        'aria-controls="filters">Filters</button>'
        "</header>"
    )
    filters = (
        '<dialog class="filters" id="filters" aria-labelledby="filters-title">'
        '<div class="filters-body">'
        '<div class="filters-head"><h2 id="filters-title">Filters</h2>'
        '<button class="btn btn--ghost filters-close" type="button" data-close-filters>Done</button></div>'
        '<div class="field"><label for="case-search">Search cases</label>'
        '<input id="case-search" type="search" data-case-search placeholder="Case ID, family or verdict"></div>'
        '<div class="field"><label for="case-sort">Sort</label>'
        '<select id="case-sort" data-case-sort><option value="asc">Case ID ascending</option>'
        '<option value="desc">Case ID descending</option></select></div>'
        '<div class="field"><label for="f-verdict">Verdict</label>'
        '<select id="f-verdict" data-filter="verdict"><option value="">All verdicts</option>'
        f"{verdict_options}</select></div>"
        '<div class="field"><label for="f-family">Family</label>'
        '<select id="f-family" data-filter="family"><option value="">All families</option>'
        f"{family_options}</select></div>"
        '<div class="field"><label for="f-bad">First bad event</label>'
        '<select id="f-bad" data-filter="bad"><option value="">Any</option>'
        '<option value="yes">Present</option><option value="no">None</option></select></div>'
        '<div class="field"><label for="f-model">Agent model</label>'
        '<select id="f-model" data-filter="model"><option value="">All models</option>'
        + ''.join(f'<option value="{_e(model)}">{_e(model)}</option>' for model in sorted({case.agent_model for case in site.cases}))
        + '</select></div>'
        '<div class="field"><label for="f-review">Labels</label>'
        '<select id="f-review" data-filter="review"><option value="">All labels</option>'
        '<option value="verified">Human-verified</option>'
        '<option value="provisional">Provisional</option></select></div>'
        f'<p class="count" aria-live="polite" data-count>Showing {total} of {total} cases</p>'
        '<button class="btn btn--ghost" type="button" data-reset-filters>Reset filters</button>'
        "</div></dialog>"
    )
    table = (
        '<div class="table-card">'
        '<div class="table-wrap">'
        '<table class="case-table" data-case-table>'
        '<caption class="sr-only">Audited cases</caption>'
        "<thead><tr>"
        '<th scope="col">Case</th><th scope="col">Family</th><th scope="col">Verdict</th>'
        '<th scope="col">First harmful event</th><th scope="col">Claims cited</th>'
        '<th scope="col">Hash chain</th><th scope="col">Labels</th><th scope="col">Certificate</th>'
        "</tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
        '<p class="empty" data-empty hidden>No cases match these filters.</p>'
        "</div>"
    )
    return _page(
        title="Cases",
        description="Audited cases with verdicts, first harmful events and label status.",
        body=head + '<div class="cases-layout">' + filters + table + "</div>",
        root="",
        active="cases",
        body_class="page-cases",
    )


def _case_row(case: CaseView) -> str:
    cited, total = case.coverage
    review_key = "verified" if case.review_action else "provisional"
    first_bad = "None" if case.first_bad_event_seq is None else f"#{case.first_bad_event_seq}"
    return (
        f'<tr data-verdict="{_e(case.verdict)}" data-family="{_e(case.family_id)}" '
        f'data-review="{review_key}" data-model="{_e(case.agent_model)}" data-bad="{"yes" if case.first_bad_event_seq is not None else "no"}">'
        f'<th scope="row" data-label="Case"><a class="mono" href="cases/{_e(case.case_id)}.html">'
        f"{_e(case.case_id)}</a></th>"
        f'<td data-label="Family">{_e(case.family_name)}</td>'
        f'<td data-label="Verdict">{_badge(case.verdict)}</td>'
        f'<td data-label="First harmful event" class="mono">{_e(first_bad)}</td>'
        f'<td data-label="Claims cited">{cited}/{total}</td>'
        f'<td data-label="Hash chain">{_chain_chip(case.chain_valid)}</td>'
        f'<td data-label="Labels">{_label_chip(case.review_action)}</td>'
        f'<td data-label="Certificate"><a href="certificates/{_e(case.case_id)}.html">View</a></td>'
        "</tr>"
    )


# --------------------------------------------------------------------------- #
# Case detail: AGENT SAID | LEDGER PROVED | evidence inspector
# --------------------------------------------------------------------------- #
def render_case(case: CaseView) -> str:
    cited, total = case.coverage
    selected = _default_claim(case)
    report_html, matched = _render_report(case, selected)
    body = (
        _crumbs(case)
        + _case_head(case)
        + _first_bad_callout(case)
        + _summary_strip(case, cited, total)
        + '<div class="case-grid">'
        + _said_panel(case, report_html, matched, selected)
        + _proved_panel(case, selected)
        + _inspector(case, selected)
        + "</div>"
    )
    return _page(
        title=f"Case {case.case_id}",
        description=f"Case {case.case_id}: {case.verdict}. {case.explanation}",
        body=body,
        root="../",
        active="cases",
        body_class="page-case",
    )


def _crumbs(case: CaseView) -> str:
    return (
        '<nav class="crumbs" aria-label="Breadcrumb">'
        '<a href="../index.html">Overview</a><span aria-hidden="true">/</span>'
        '<a href="../cases.html">Cases</a><span aria-hidden="true">/</span>'
        f'<span class="mono" aria-current="page">{_e(case.case_id)}</span></nav>'
    )


def _case_head(case: CaseView) -> str:
    return (
        '<header class="page-head case-head"><div>'
        f'<p class="eyebrow">{_e(case.family_id)} · {_e(case.family_name)}</p>'
        f'<h1 class="case-title"><span class="mono">{_e(case.case_id)}</span>{_copy(case.case_id)}</h1>'
        f'<p class="lede">{_e(case.family_summary)}</p>'
        "</div>"
        f'<div class="verdict-block">{_badge(case.verdict, large=True)}'
        f'<p class="explain">{_e(case.explanation)}</p></div>'
        "</header>"
    )


def _first_bad_callout(case: CaseView) -> str:
    seq = case.first_bad_event_seq
    if seq is None:
        return (
            '<section class="callout callout--ok" aria-labelledby="no-bad-title">'
            f"{_icon('check')}"
            '<div class="callout-body"><h2 id="no-bad-title">No first harmful event</h2>'
            "<p>No ledger event is marked as the first harmful event for this case.</p></div></section>"
        )
    event = case.events_by_seq().get(seq)
    kind = event["event_type"] if event else "not in ledger"
    return (
        '<section class="callout callout--danger" aria-labelledby="first-bad-title">'
        f"{_icon('warning')}"
        '<div class="callout-body"><h2 id="first-bad-title">First harmful event</h2>'
        f'<p>Ledger event <span class="mono">#{seq}</span> (<span class="mono">{_e(kind)}</span>) '
        "is the earliest event linked to a contradicted claim.</p>"
        f'<a class="btn btn--danger-ghost" href="#event-{seq}">{_icon("jump")}Jump to event #{seq}</a>'
        "</div></section>"
    )


def _summary_strip(case: CaseView, cited: int, total: int) -> str:
    chips = [
        _chip("info", f"Claims cited {cited}/{total}", "info"),
        _chip("info", f"Ledger events {len(case.events)}", "info"),
        _chain_chip(case.chain_valid),
        _chip("info", f"Agent tool calls {case.agent_tool_calls}", "info"),
        _label_chip(case.review_action),
        _chip("info", f"ProofTrail model calls {case.auditor_llm_calls}", "info"),
    ]
    return _chip_list(chips, "Case summary", "summary-strip")


def _claim_item(claim: dict[str, Any], selected: str | None) -> str:
    slug = _slug(claim["claim_id"])
    tone = STATUS_STYLE[claim["status"]][0]
    on = slug == selected
    classes = f"claim-card claim-card--{tone}" + (" is-selected" if on else "")
    pressed = "true" if on else "false"
    refs = ", ".join(f"#{seq}" for seq in claim["evidence_seqs"]) or "no ledger event"
    return (
        "<li>"
        f'<button class="{classes}" id="{slug}" type="button" data-select-claim="{slug}" '
        f'aria-pressed="{pressed}">'
        f'<span class="claim-head">{_badge(claim["status"])}'
        f'<span class="mono claim-type">{_e(claim["claim_type"])}</span></span>'
        f'<span class="claim-text">{_e(claim["claim_text"])}</span>'
        f'<span class="claim-cites">Cites {_e(refs)}</span>'
        "</button></li>"
    )


def _said_panel(case: CaseView, report_html: str, matched: set[str], selected: str | None) -> str:
    unmatched = [claim for claim in case.claims if _slug(claim["claim_id"]) not in matched]
    note = ""
    if unmatched:
        note = '<p class="note">Claims that are not verbatim in the report are listed without highlights.</p>'
    items = "".join(_claim_item(claim, selected) for claim in case.claims) or NO_CLAIMS_LI
    return (
        '<details class="panel panel--said" open data-collapsible>'
        '<summary class="panel-summary">'
        '<h2 class="panel-title">AGENT SAID</h2>'
        '<span class="panel-sub">The final report, with each claim marked</span></summary>'
        f'<blockquote class="report">{report_html}</blockquote>'
        f"{note}"
        f'<ol class="claim-list" aria-label="Claims">{items}</ol>'
        "</details>"
    )


def _event_item(
    event: dict[str, Any],
    cited_by: dict[int, list[str]],
    first_bad: int | None,
    selected: str | None,
) -> str:
    seq = event["seq"]
    claim_slugs = [_slug(claim_id) for claim_id in cited_by.get(seq, [])]
    is_first = seq == first_bad
    classes = ["event"]
    if is_first:
        classes.append("event--first-bad")
    if selected in claim_slugs:
        classes.append("is-cited")
    chips: list[str] = []
    if is_first:
        chips.append(f'<span class="badge badge--contradicted">{_icon("warning")}<span>First harmful event</span></span>')
    for slug in claim_slugs:
        label = slug.replace("-", " ")
        chips.append(f'<a class="chip chip--cited" href="#{slug}">Cited by {_e(label)}</a>')
    chip_row = "".join(chips)
    chip_block = f'<div class="event-chips">{chip_row}</div>' if chip_row else ""
    class_attr = " ".join(classes)
    cited_attr = " ".join(claim_slugs)
    meta_spans = [f'<span class="mono break">{_e(event.get("ts"))}</span>']
    if event.get("entity"):
        meta_spans.append(f'<span class="mono break">{_e(event["entity"])}</span>')
    if event.get("tool_name"):
        meta_spans.append(f'<span class="mono break">{_e(event["tool_name"])}</span>')
    meta = "".join(meta_spans)
    more = (
        '<details class="event-more"><summary>Hashes and payload</summary>'
        '<dl class="kv">'
        + _kv("prev_hash", event.get("prev_hash"))
        + _kv("hash", event.get("hash"))
        + _kv("idempotency_key", event.get("idempotency_key"))
        + _kv("payload", event.get("payload"), as_json=True)
        + "</dl></details>"
    )
    return (
        f'<li class="{class_attr}" id="event-{seq}" data-event-seq="{seq}" '
        f'data-cited-by="{cited_attr}">'
        '<div class="event-marker" aria-hidden="true"></div>'
        '<div class="event-body">'
        '<div class="event-head">'
        f'<span class="event-seq mono">#{seq}</span>'
        f'<span class="event-type mono">{_e(event["event_type"])}</span>'
        "</div>"
        f'<p class="event-meta">{meta}</p>'
        f"{chip_block}{more}</div></li>"
    )


def _proved_panel(case: CaseView, selected: str | None) -> str:
    cited_by = case.cited_by()
    items = "".join(
        _event_item(event, cited_by, case.first_bad_event_seq, selected) for event in case.events
    )
    return (
        '<details class="panel panel--proved" open data-collapsible>'
        '<summary class="panel-summary">'
        '<h2 class="panel-title">LEDGER PROVED</h2>'
        '<span class="panel-sub">Committed ledger events, in order</span></summary>'
        f'<ol class="timeline">{items}</ol>'
        "</details>"
    )


def _cited_event(event: dict[str, Any]) -> str:
    before = event.get("state_before") or {}
    after = event.get("state_after") or {}
    rows: list[str] = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        changed = old != new
        row_class = ' class="is-changed"' if changed else ""
        change_text = "changed" if changed else "unchanged"
        rows.append(
            f"<tr{row_class}>"
            f'<th scope="row" class="mono break">{_e(key)}</th>'
            f'<td class="mono break" data-label="Before">{_e(_json_text(old))}</td>'
            f'<td class="mono break" data-label="After">{_e(_json_text(new))}</td>'
            f'<td data-label="Change">{change_text}</td>'
            "</tr>"
        )
    table_rows = "".join(rows) or NO_STATE_ROW
    seq = event["seq"]
    return (
        '<article class="cited-event">'
        f'<h4><a href="#event-{seq}">#{seq} <span class="mono">{_e(event["event_type"])}</span></a></h4>'
        '<div class="table-wrap"><table class="diff-table">'
        f"<caption>State fields for event #{seq}</caption>"
        '<thead><tr><th scope="col">Field</th><th scope="col">Before</th>'
        '<th scope="col">After</th><th scope="col">Change</th></tr></thead>'
        f"<tbody>{table_rows}</tbody></table></div>"
        '<dl class="kv id-list">'
        + _kv("intent_id", event.get("intent_id"))
        + _kv("tool_call_id", event.get("tool_call_id"))
        + _kv("transaction_id", event.get("transaction_id"))
        + "</dl></article>"
    )


def _tool_call(call: dict[str, Any]) -> str:
    call_id = call.get("tool_call_id")
    return (
        '<li class="tool-call">'
        f'<p><span class="mono">{_e(call.get("tool_name"))}</span> '
        f'<span class="mono break">{_e(call_id)}</span>{_copy(call_id)}</p>'
        '<dl class="kv">'
        + _kv("args", call.get("args"), as_json=True)
        + _kv("result", call.get("result"), as_json=True)
        + _kv("error", call.get("error"), as_json=True)
        + "</dl></li>"
    )


def _inspect(claim: dict[str, Any], events: dict[int, dict[str, Any]], selected: str | None) -> str:
    slug = _slug(claim["claim_id"])
    cited_events = [events[seq] for seq in claim["evidence_seqs"] if seq in events]
    if cited_events:
        evidence = "".join(_cited_event(event) for event in cited_events)
    else:
        evidence = '<p class="muted">No ledger event could be linked to this claim.</p>'
    calls = claim.get("tool_calls") or []
    tool_calls = ""
    if calls:
        call_items = "".join(_tool_call(call) for call in calls)
        tool_calls = (
            '<details class="tool-calls">'
            f"<summary>Agent-visible tool calls ({len(calls)})</summary>"
            f'<ol class="tool-call-list">{call_items}</ol></details>'
        )
    hidden = "" if slug == selected else " hidden"
    return (
        f'<section class="inspect" id="inspect-{slug}" data-inspector="{slug}"{hidden} '
        f'aria-label="Evidence for {_e(claim["claim_id"])}">'
        '<header class="inspect-head">'
        f'{_badge(claim["status"])}'
        f'<span class="mono muted">{_e(claim["claim_id"])} · {_e(claim["claim_type"])}</span>'
        "</header>"
        f'<blockquote class="inspect-quote">{_e(claim["claim_text"])}</blockquote>'
        f'<p class="inspect-reason"><span class="label">Reason</span> {_e(claim["reason"])}</p>'
        '<h3 class="subhead">Cited ledger events</h3>'
        f"{evidence}{tool_calls}"
        "</section>"
    )


def _inspector(case: CaseView, selected: str | None) -> str:
    events = case.events_by_seq()
    panels = "".join(_inspect(claim, events, selected) for claim in case.claims)
    if not panels:
        panels = '<p class="muted">No claims to inspect.</p>'
    return (
        '<aside class="panel panel--inspector" aria-labelledby="inspector-title">'
        '<h2 id="inspector-title" class="panel-title">EVIDENCE INSPECTOR</h2>'
        f"{panels}"
        "</aside>"
    )


# --------------------------------------------------------------------------- #
# Evidence certificate (print-ready)
# --------------------------------------------------------------------------- #
def render_certificate(case: CaseView) -> str:
    cited, total = case.coverage
    events = case.events_by_seq()
    seq = case.first_bad_event_seq
    first_bad = "None" if seq is None else f"#{seq}"
    meta = [
        ("Verdict", _badge(case.verdict)),
        ("First harmful event", _e(first_bad)),
        ("Evidence coverage", _e(f"{cited} of {total} claims cited")),
        ("Ledger hash chain", _e("Valid" if case.chain_valid else "Broken")),
        ("Family", _e(f"{case.family_id} · {case.family_name}")),
        ("Label status", _e(_review_text(case.review_action))),
        ("Auditor", _e(f"prooftrail, deterministic, {case.auditor_llm_calls} model calls")),
        ("Agent tool calls", _e(case.agent_tool_calls)),
    ]
    meta_html = "".join(f"<div><dt>{_e(label)}</dt><dd>{value}</dd></div>" for label, value in meta)
    claim_rows = "".join(_certificate_claim_row(claim) for claim in case.claims) or NO_CLAIMS_ROW
    linked = sorted({seq_no for claim in case.claims for seq_no in claim["evidence_seqs"] if seq_no in events})
    evidence_rows = "".join(_certificate_evidence_row(events[seq_no]) for seq_no in linked) or NO_EVIDENCE_ROW
    calls = _unique_tool_calls(case)
    calls_section = ""
    if calls:
        call_rows = "".join(_certificate_call_row(call) for call in calls)
        calls_section = (
            '<section class="cert-section"><h2>Agent-visible tool calls</h2>'
            '<div class="table-wrap"><table class="cert-table cert-table--calls">'
            '<caption class="sr-only">Tool calls the claims rely on</caption>'
            '<thead><tr><th scope="col">Call</th><th scope="col">Tool</th><th scope="col">Args</th>'
            '<th scope="col">Result</th><th scope="col">Error</th></tr></thead>'
            f"<tbody>{call_rows}</tbody></table></div></section>"
        )
    toolbar = (
        '<div class="toolbar no-print">'
        f'<a class="btn btn--ghost" href="../cases/{_e(case.case_id)}.html">{_icon("back")}Back to case</a>'
        f'<a class="btn btn--ghost" href="{_e(case.case_id)}.json" download>Download JSON</a>'
        f'<a class="btn btn--ghost" href="{_e(case.case_id)}.md" download>Download Markdown</a>'
        '<button class="btn btn--primary" type="button" data-print>'
        f'{_icon("print")}Print or save as PDF</button></div>'
    )
    article = (
        '<article class="certificate">'
        '<header class="cert-head">'
        '<p class="cert-brand"><span class="brand-mark" aria-hidden="true"></span>ProofTrail</p>'
        "<h1>Evidence Certificate</h1>"
        f'<p class="cert-case mono break">{_e(case.case_id)}</p>'
        "</header>"
        f'<dl class="cert-meta">{meta_html}</dl>'
        '<section class="cert-section"><h2>Summary</h2>'
        f"<p>{_e(case.explanation)}</p></section>"
        '<section class="cert-section"><h2>Claims</h2>'
        '<div class="table-wrap"><table class="cert-table cert-table--claims">'
        '<caption class="sr-only">Claims with verdicts and cited ledger events</caption>'
        '<thead><tr><th scope="col">Claim</th><th scope="col">Statement</th>'
        '<th scope="col">Type</th><th scope="col">Verdict</th>'
        '<th scope="col">Evidence</th><th scope="col">Reason</th></tr></thead>'
        f"<tbody>{claim_rows}</tbody></table></div></section>"
        '<section class="cert-section"><h2>Linked ledger evidence</h2>'
        '<div class="table-wrap"><table class="cert-table cert-table--evidence">'
        '<caption class="sr-only">Ledger events cited by the claims</caption>'
        '<thead><tr><th scope="col">Event</th><th scope="col">Entity</th>'
        '<th scope="col">State before</th><th scope="col">State after</th>'
        '<th scope="col">Payload</th></tr></thead>'
        f"<tbody>{evidence_rows}</tbody></table></div></section>"
        f"{calls_section}"
        '<footer class="cert-foot">'
        "<p>Automated evidence for reviewer sign-off. Not a legal attestation.</p>"
        f'<p>Reproduce offline: <code class="break">python -m prooftrail replay --provider gemini '
        f"--case {_e(case.case_id)}</code></p>"
        "</footer>"
        "</article>"
    )
    return _page(
        title=f"Evidence Certificate {case.case_id}",
        description=f"Evidence certificate for case {case.case_id}: {case.verdict}.",
        body=toolbar + article,
        root="../",
        active="cases",
        body_class="page-certificate",
    )


def _certificate_claim_row(claim: dict[str, Any]) -> str:
    refs = ", ".join(f"#{seq}" for seq in claim["evidence_seqs"]) or "none"
    return (
        "<tr>"
        f'<td class="mono break" data-label="Claim">{_e(claim["claim_id"])}</td>'
        f'<td class="break" data-label="Statement">{_e(claim["claim_text"])}</td>'
        f'<td class="mono break" data-label="Type">{_e(claim["claim_type"])}</td>'
        f'<td data-label="Verdict">{_badge(claim["status"])}</td>'
        f'<td class="mono break" data-label="Evidence">{_e(refs)}</td>'
        f'<td class="break" data-label="Reason">{_e(claim["reason"])}</td>'
        "</tr>"
    )


def _certificate_evidence_row(event: dict[str, Any]) -> str:
    seq = event["seq"]
    return (
        "<tr>"
        '<td data-label="Event"><span class="stack">'
        f'<span class="mono">#{seq} {_e(event["event_type"])}</span>'
        f'<span class="mono break">{_e(event.get("ts"))}</span></span></td>'
        f'<td class="mono break" data-label="Entity">{_e(event.get("entity"))}</td>'
        f'<td class="mono break" data-label="State before">{_e(_json_text(event.get("state_before")))}</td>'
        f'<td class="mono break" data-label="State after">{_e(_json_text(event.get("state_after")))}</td>'
        f'<td class="mono break" data-label="Payload">{_e(_json_text(event.get("payload")))}</td>'
        "</tr>"
    )


def _unique_tool_calls(case: CaseView) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for claim in case.claims:
        for call in claim.get("tool_calls") or []:
            seen.setdefault(str(call.get("tool_call_id")), call)
    return [seen[key] for key in sorted(seen)]


def _certificate_call_row(call: dict[str, Any]) -> str:
    return (
        "<tr>"
        f'<td class="mono break" data-label="Call">{_e(call.get("tool_call_id"))}</td>'
        f'<td class="mono break" data-label="Tool">{_e(call.get("tool_name"))}</td>'
        f'<td class="mono break" data-label="Args">{_e(_json_text(call.get("args")))}</td>'
        f'<td class="mono break" data-label="Result">{_e(_json_text(call.get("result")))}</td>'
        f'<td class="mono break" data-label="Error">{_e(_json_text(call.get("error")))}</td>'
        "</tr>"
    )
