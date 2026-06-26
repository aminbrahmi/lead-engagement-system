"""
analyst_pdf.py — render Analyst reports to PDF (reportlab, with charts).
"""

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether,
)
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend


# Brand palette (matches the app)
ACCENT = colors.HexColor("#6c5ce7")
HOT    = colors.HexColor("#ff6b6b")
WARM   = colors.HexColor("#fdcb6e")
COLD   = colors.HexColor("#74b9ff")
INK    = colors.HexColor("#2d3436")
MUTE   = colors.HexColor("#636e72")
LIGHT  = colors.HexColor("#f5f6fa")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("H1b", parent=ss["Title"], textColor=INK, fontSize=22, spaceAfter=4))
    ss.add(ParagraphStyle("Sub", parent=ss["Normal"], textColor=MUTE, fontSize=10, spaceAfter=2))
    ss.add(ParagraphStyle("H2b", parent=ss["Heading2"], textColor=ACCENT, fontSize=13,
                          spaceBefore=14, spaceAfter=6))
    ss.add(ParagraphStyle("Body", parent=ss["Normal"], textColor=INK, fontSize=10, leading=15))
    ss.add(ParagraphStyle("Rec", parent=ss["Normal"], textColor=INK, fontSize=10,
                          leading=15, leftIndent=10, spaceAfter=4, bulletIndent=0))
    return ss


def _segment_pie(hot: int, warm: int, cold: int) -> Drawing:
    d = Drawing(240, 150)
    data, labels, cols = [], [], []
    for val, lab, col in [(hot, "Hot", HOT), (warm, "Warm", WARM), (cold, "Cold", COLD)]:
        if val > 0:
            data.append(val); labels.append(f"{lab} ({val})"); cols.append(col)
    if not data:
        data, labels, cols = [1], ["No leads"], [MUTE]
    pie = Pie()
    pie.x, pie.y, pie.width, pie.height = 10, 15, 120, 120
    pie.data = data
    pie.labels = None
    pie.slices.strokeWidth = 0.5
    pie.slices.strokeColor = colors.white
    for i, col in enumerate(cols):
        pie.slices[i].fillColor = col
    d.add(pie)
    legend = Legend()
    legend.x, legend.y = 150, 110
    legend.dx, legend.dy = 8, 8
    legend.fontName, legend.fontSize = "Helvetica", 9
    legend.alignment = "right"
    legend.colorNamePairs = list(zip(cols, labels))
    d.add(legend)
    return d


def _engagement_bars(click_rate, reply_rate, bounce_rate) -> Drawing:
    d = Drawing(260, 160)
    bc = VerticalBarChart()
    bc.x, bc.y, bc.width, bc.height = 30, 25, 210, 115
    bc.data = [[click_rate, reply_rate, bounce_rate]]
    bc.categoryAxis.categoryNames = ["Click", "Reply", "Bounce"]
    bc.categoryAxis.labels.fontSize = 9
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = max(100, click_rate + 5)
    bc.valueAxis.labels.fontSize = 8
    bc.bars[0].fillColor = ACCENT
    bc.barWidth = 14
    d.add(bc)
    return d


def _variant_bars(variants: dict) -> Drawing:
    """Grouped bars: click/reply rate per variant."""
    d = Drawing(280, 170)
    keys = sorted(variants.keys())
    bc = VerticalBarChart()
    bc.x, bc.y, bc.width, bc.height = 30, 30, 230, 120
    # rows = variants, columns = metric → grouped per metric
    bc.data = [
        [variants[k]["click_rate"] for k in keys],
        [variants[k]["reply_rate"] for k in keys],
    ]
    bc.categoryAxis.categoryNames = ["Click %", "Reply %"]
    bc.categoryAxis.labels.fontSize = 9
    bc.valueAxis.valueMin = 0
    bc.valueAxis.labels.fontSize = 8
    palette = [ACCENT, HOT, WARM, COLD]
    for i in range(len(keys)):
        bc.bars[i].fillColor = palette[i % len(palette)]
    d.add(bc)
    legend = Legend()
    legend.x, legend.y = 30, 160
    legend.dx, legend.dy = 8, 8
    legend.fontSize = 9
    legend.colorNamePairs = [(palette[i % len(palette)], f"Variant {k}") for i, k in enumerate(keys)]
    legend.columnMaximum = 1
    d.add(legend)
    return d


def _metric_table(rows, col_widths=None):
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe4ea")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _header(elements, ss, title, subtitle):
    elements.append(Paragraph(title, ss["H1b"]))
    elements.append(Paragraph(subtitle, ss["Sub"]))
    elements.append(Paragraph(
        f"Generated {datetime.now().strftime('%d %b %Y, %H:%M')} · TheLeadFlow Analyst", ss["Sub"]))
    elements.append(Spacer(1, 8))


def _recommendations_block(elements, ss, summary, recommendations):
    if summary:
        elements.append(Paragraph("Executive summary", ss["H2b"]))
        elements.append(Paragraph(summary, ss["Body"]))
    if recommendations:
        elements.append(Paragraph("Optimization recommendations", ss["H2b"]))
        for i, rec in enumerate(recommendations, 1):
            elements.append(Paragraph(f"{i}. {rec}", ss["Rec"]))


def build_campaign_pdf(report: dict) -> bytes:
    """Render a single-campaign report dict (from build_campaign_report) to PDF bytes."""
    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm)
    el = []

    camp = report.get("campaign", {})
    prompt = camp.get("prompt", "")
    _header(el, ss, "Campaign Performance Report",
            f"Campaign: {prompt[:90]}")

    leads = report["leads"]
    emails = report["emails"]

    # ── Key metrics tables ──
    el.append(Paragraph("Key metrics", ss["H2b"]))
    leads_tbl = _metric_table([
        ["Leads", "Hot", "Warm", "Cold", "Avg score", "Email coverage", "Verified"],
        [leads["total"], leads["hot"], leads["warm"], leads["cold"],
         leads["avg_score"], f"{leads['email_coverage']}%", f"{leads['verified_pct']}%"],
    ])
    el.append(leads_tbl)
    el.append(Spacer(1, 8))
    emails_tbl = _metric_table([
        ["Sent", "Clicked", "Replied", "Bounced", "Unsub", "Meetings"],
        [emails["sent"], emails["clicked"], emails["replied"],
         emails["bounced"], emails["unsubscribed"], emails["meetings"]],
    ])
    el.append(emails_tbl)
    el.append(Spacer(1, 4))
    rates_tbl = _metric_table([
        ["Click rate", "Reply rate", "Bounce rate"],
        [f"{emails['click_rate']}%", f"{emails['reply_rate']}%", f"{emails['bounce_rate']}%"],
    ])
    el.append(rates_tbl)

    # ── Charts ──
    el.append(Paragraph("Performance charts", ss["H2b"]))
    charts = Table(
        [[_segment_pie(leads["hot"], leads["warm"], leads["cold"]),
          _engagement_bars(emails["click_rate"], emails["reply_rate"], emails["bounce_rate"])]],
        colWidths=[85 * mm, 85 * mm],
    )
    charts.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el.append(charts)

    # ── A/B variant comparison ──
    variants = report.get("variants", {})
    if variants:
        el.append(Paragraph("A/B variant performance", ss["H2b"]))
        header = ["Variant", "Sent", "Clicked", "Replied", "Click %", "Reply %"]
        rows = [header]
        for k in sorted(variants.keys()):
            v = variants[k]
            label = f"{k}  ★" if report.get("best_variant") == k else k
            rows.append([label, v["sent"], v["clicked"], v["replied"],
                         f"{v['click_rate']}%", f"{v['reply_rate']}%"])
        el.append(_metric_table(rows))
        if report.get("best_variant"):
            el.append(Spacer(1, 4))
            el.append(Paragraph(
                f"Best performing variant: <b>{report['best_variant']}</b> "
                f"(by reply, then click rate).", ss["Body"]))
        if len(variants) >= 2:
            el.append(Spacer(1, 6))
            el.append(_variant_bars(variants))

    # ── Recommendations ──
    _recommendations_block(el, ss, report.get("summary", ""), report.get("recommendations", []))

    doc.build(el)
    buf.seek(0)
    return buf.read()


def build_weekly_pdf(report: dict) -> bytes:
    """Render a weekly report dict (from build_weekly_report) to PDF bytes."""
    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm)
    el = []

    start = report.get("period_start", "")[:10]
    end = report.get("period_end", "")[:10]
    _header(el, ss, "Weekly Performance Report", f"Period: {start} → {end}")

    t = report["totals"]
    el.append(Paragraph("Totals across all campaigns", ss["H2b"]))
    el.append(_metric_table([
        ["Campaigns", "Leads", "Sent", "Clicked", "Replied", "Meetings"],
        [len(report["campaigns"]), t["leads"], t["sent"],
         t["clicked"], t["replied"], t["meetings"]],
    ]))
    el.append(Spacer(1, 4))
    el.append(_metric_table([
        ["Click rate", "Reply rate", "Bounce rate"],
        [f"{t['click_rate']}%", f"{t['reply_rate']}%", f"{t['bounce_rate']}%"],
    ]))

    el.append(Paragraph("Lead quality", ss["H2b"]))
    el.append(Table(
        [[_segment_pie(t["hot"], t["warm"], t["cold"])]],
        colWidths=[120 * mm],
    ))

    # ── Per-campaign breakdown ──
    el.append(Paragraph("Per-campaign breakdown", ss["H2b"]))
    rows = [["Campaign", "Leads", "Sent", "Click %", "Reply %", "Best variant"]]
    for c in report["campaigns"]:
        m = c["metrics"]
        rows.append([
            (c["prompt"] or "")[:40],
            m["leads"]["total"], m["emails"]["sent"],
            f"{m['emails']['click_rate']}%",
            f"{m['emails']['reply_rate']}%", m.get("best_variant") or "—",
        ])
    el.append(_metric_table(rows, col_widths=[62 * mm, 18 * mm, 16 * mm, 20 * mm, 20 * mm, 26 * mm]))

    _recommendations_block(el, ss, report.get("summary", ""), report.get("recommendations", []))

    doc.build(el)
    buf.seek(0)
    return buf.read()
