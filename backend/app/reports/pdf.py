"""PDF evidence pack for one entity.

Uses reportlab's built-in Type-1 fonts, which ship inside the library itself, so
nothing is fetched at render time.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services import entity_detail, finding_evidence
from app.schema import CAPABILITY_AREAS

NAVY = colors.HexColor("#0f2545")
ACCENT = colors.HexColor("#1f6feb")
GREY = colors.HexColor("#5b6675")
LIGHT = colors.HexColor("#eef1f6")
BAND_COLOURS = {
    "High": colors.HexColor("#b91c1c"),
    "Medium": colors.HexColor("#b45309"),
    "Low": colors.HexColor("#15803d"),
}
SEVERITY_COLOURS = {
    "high": colors.HexColor("#b91c1c"),
    "medium": colors.HexColor("#b45309"),
    "low": colors.HexColor("#475569"),
}
MAX_EVIDENCE_ROWS = 20


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "t", parent=base["Title"], fontName="Helvetica-Bold", fontSize=22,
            textColor=NAVY, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "st", parent=base["Normal"], fontName="Helvetica", fontSize=11,
            textColor=GREY, spaceAfter=14,
        ),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=14,
            textColor=NAVY, spaceBefore=14, spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=11.5,
            textColor=NAVY, spaceBefore=10, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "b", parent=base["Normal"], fontName="Helvetica", fontSize=9.5,
            leading=13.5, alignment=TA_LEFT,
        ),
        "small": ParagraphStyle(
            "s", parent=base["Normal"], fontName="Helvetica", fontSize=8,
            leading=10.5, textColor=GREY,
        ),
        "mono": ParagraphStyle(
            "m", parent=base["Normal"], fontName="Courier", fontSize=7.4, leading=9.2
        ),
    }


def _footer(canvas, doc, run_id: str, data_hash: str) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(GREY)
    canvas.drawString(
        18 * mm,
        12 * mm,
        f"SAT-SA Lens - supervisory analytics - run {run_id} - data hash {data_hash[:24]}",
    )
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"page {doc.page}")
    canvas.setStrokeColor(LIGHT)
    canvas.line(18 * mm, 16 * mm, A4[0] - 18 * mm, 16 * mm)
    canvas.restoreState()


def _kv_table(pairs: list[tuple[str, str]], width: float) -> Table:
    t = Table([[k, v] for k, v in pairs], colWidths=[width * 0.36, width * 0.64])
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (0, 0), (0, -1), NAVY),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return t


def build_entity_report(entity_id: str) -> bytes:
    detail = entity_detail(entity_id)
    if not detail:
        raise ValueError(f"Unknown entity {entity_id}")
    st = _styles()
    entity = detail["entity"]
    scores = detail["scores"] or {}
    run = detail["run"] or {}
    run_id = run.get("run_id", "n/a")
    data_hash = run.get("data_hash", "n/a") or "n/a"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title=f"SAT-SA Lens evidence pack - {entity['name']}",
        author="SAT-SA Lens",
    )
    width = doc.width
    story: list[Any] = []

    # ------------------------------------------------------------------- cover
    story.append(Paragraph("SOC Assessment Evidence Pack", st["title"]))
    story.append(
        Paragraph(
            f"{entity['name']} &nbsp;|&nbsp; {entity['sector'].replace('_', ' ').title()} "
            f"&nbsp;|&nbsp; {entity['size_tier'].title()} tier &nbsp;|&nbsp; "
            f"{entity['analyst_count']} analysts",
            st["subtitle"],
        )
    )
    band = scores.get("risk_band", "Low")
    score = scores.get("risk_score", 0.0)
    head = Table(
        [
            [
                Paragraph(
                    f"<font size=30 color='{BAND_COLOURS.get(band, GREY).hexval()}'>"
                    f"<b>{score:.0f}</b></font><br/>"
                    f"<font size=10 color='#5b6675'>risk score (0-100)</font>",
                    st["body"],
                ),
                Paragraph(
                    f"<font size=15 color='{BAND_COLOURS.get(band, GREY).hexval()}'>"
                    f"<b>{band} risk</b></font><br/>"
                    f"<font size=9 color='#5b6675'>{scores.get('finding_count', 0)} "
                    f"open or validated findings</font>",
                    st["body"],
                ),
                _kv_table(
                    [
                        ("Analysis run", run_id),
                        ("Run at", str(run.get("started_at", ""))[:19]),
                        ("Rules version", str(run.get("rules_version", ""))),
                        ("Code version", str(run.get("code_version", ""))),
                        ("Data hash", (data_hash or "")[:32]),
                        ("Generated", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
                    ],
                    width * 0.42,
                ),
            ]
        ],
        colWidths=[width * 0.22, width * 0.3, width * 0.48],
    )
    head.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (1, 0), LIGHT),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.append(head)
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "<b>This is a supervisory aid, not a verdict.</b> Every item below is a "
            "hypothesis produced by an automated first pass over the organisation's own "
            "submission. Each one states the numbers behind it, a possible innocent "
            "explanation, and the exact records to check. A weakness is only confirmed "
            "once a human supervisor marks it valid.",
            st["small"],
        )
    )

    # --------------------------------------------------------- why this score
    story.append(Paragraph("Why this score", st["h1"]))
    top = scores.get("top_contributors") or []
    if top:
        rows = [["#", "Finding", "Severity", "Confidence", "Points"]]
        for i, c in enumerate(top, 1):
            rows.append(
                [
                    str(i),
                    Paragraph(f"<b>{c['detector_id']}</b> {c['title']}", st["body"]),
                    c["severity"].title(),
                    f"{c['confidence']:.0%}",
                    f"{c['weight']:.0f}",
                ]
            )
        t = Table(rows, colWidths=[width * 0.05, width * 0.55, width * 0.13, width * 0.14, width * 0.13])
        t.setStyle(_grid_style())
        story.append(t)
    else:
        story.append(
            Paragraph(
                "No findings were raised for this organisation in this run.", st["body"]
            )
        )

    # ------------------------------------------------------ capability scorecard
    story.append(Paragraph("Capability scorecard", st["h1"]))
    caps = scores.get("capability_scores") or {a: 100.0 for a in CAPABILITY_AREAS}
    radar = {r["area"]: r for r in detail["radar"]}
    rows = [["Capability area", "Score", "Peer average", "Findings reducing it"]]
    explanations = scores.get("capability_explanations") or {}
    for area in CAPABILITY_AREAS:
        expl = explanations.get(area) or []
        rows.append(
            [
                area.replace("_", " ").title(),
                f"{caps.get(area, 100.0):.0f}",
                f"{radar.get(area, {}).get('peer_average', 100.0):.0f}",
                Paragraph(
                    ", ".join(f"{e['detector_id']} ({e['points_deducted']:.0f})" for e in expl)
                    or "-",
                    st["body"],
                ),
            ]
        )
    t = Table(rows, colWidths=[width * 0.26, width * 0.1, width * 0.14, width * 0.5])
    t.setStyle(_grid_style())
    story.append(t)
    story.append(
        Paragraph(
            "100 means nothing was flagged in that area. Peer average is taken over the "
            f"comparison group: {detail['peer_group']['label']} "
            f"(level used: {detail['peer_group']['comparison_level']}).",
            st["small"],
        )
    )

    # ----------------------------------------------------------------- findings
    story.append(PageBreak())
    story.append(Paragraph("Findings and evidence", st["h1"]))
    counted = [f for f in detail["findings"] if f["status"] in ("open", "valid")]
    dismissed = [f for f in detail["findings"] if f["status"] == "not_valid"]
    if not counted:
        story.append(Paragraph("No findings to report.", st["body"]))
    for f in counted:
        story.extend(_finding_block(f, st, width))
    if dismissed:
        story.append(Paragraph("Findings dismissed by the supervisor", st["h1"]))
        rows = [["Detector", "Title", "Note"]]
        for f in dismissed:
            rows.append(
                [
                    f["detector_id"],
                    Paragraph(f["title"], st["body"]),
                    Paragraph(f.get("supervisor_note") or "-", st["body"]),
                ]
            )
        t = Table(rows, colWidths=[width * 0.12, width * 0.44, width * 0.44])
        t.setStyle(_grid_style())
        story.append(t)

    doc.build(
        story,
        onFirstPage=lambda c, d: _footer(c, d, run_id, data_hash),
        onLaterPages=lambda c, d: _footer(c, d, run_id, data_hash),
    )
    return buf.getvalue()


def _grid_style() -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, LIGHT),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fc")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )


def _finding_block(f: dict[str, Any], st: dict[str, ParagraphStyle], width: float) -> list:
    sev_colour = SEVERITY_COLOURS.get(f["severity"], GREY).hexval()
    parts: list[Any] = [
        Paragraph(
            f"<font color='{sev_colour}'><b>{f['detector_id']}</b></font> &nbsp; "
            f"{f['title']}",
            st["h2"],
        ),
        Paragraph(
            f"<b>{f['severity'].title()} severity</b> &nbsp;|&nbsp; confidence "
            f"{f['confidence']:.0%} &nbsp;|&nbsp; "
            f"{f['gap_type'].replace('_', ' ')} &nbsp;|&nbsp; "
            f"{f['capability_area'].replace('_', ' ')} &nbsp;|&nbsp; status "
            f"<b>{f['status']}</b>",
            st["small"],
        ),
        Spacer(1, 3),
        Paragraph(_clean(f["rationale"]), st["body"]),
        Spacer(1, 3),
        Paragraph(
            f"<b>Possible innocent explanation.</b> {_clean(f['innocent_explanation'])}",
            st["small"],
        ),
    ]
    if f.get("supervisor_note"):
        parts.append(
            Paragraph(f"<b>Supervisor note.</b> {_clean(f['supervisor_note'])}", st["small"])
        )
    metrics = f.get("metrics") or {}
    flat = [
        (k.replace("_", " "), _short(v))
        for k, v in metrics.items()
        if not isinstance(v, (list, dict))
    ][:12]
    if flat:
        parts.append(Spacer(1, 4))
        parts.append(_kv_table(flat, width))

    ev = finding_evidence(f["finding_id"], limit=MAX_EVIDENCE_ROWS)
    rows = ev.get("rows") or []
    if rows:
        cols = [c for c in ev["columns"] if c != "row_id"][:7]
        head = [c.replace("_", " ") for c in cols]
        table_rows = [head]
        for r in rows[:MAX_EVIDENCE_ROWS]:
            table_rows.append([Paragraph(_short(r.get(c), 70), st["mono"]) for c in cols])
        t = Table(table_rows, colWidths=[width / max(len(cols), 1)] * len(cols))
        t.setStyle(_grid_style())
        parts.append(Spacer(1, 4))
        parts.append(
            Paragraph(
                f"Evidence: {ev['total']:,} records; first {min(len(rows), MAX_EVIDENCE_ROWS)} "
                f"shown from table '{ev['evidence_table']}'.",
                st["small"],
            )
        )
        parts.append(t)
    parts.append(Spacer(1, 10))
    # Keep the header, rationale and innocent explanation on one page; let the
    # evidence table flow if it is long.
    head, tail = parts[:6], parts[6:]
    return [KeepTogether(head), *tail]


def _clean(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("**", "")
    )


def _short(value: Any, limit: int = 90) -> str:
    s = "" if value is None else str(value)
    if isinstance(value, float):
        s = f"{value:.4g}"
    s = _clean(s)
    return s if len(s) <= limit else s[: limit - 1] + "&hellip;"
