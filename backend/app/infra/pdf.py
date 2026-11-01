"""ReportLab renderer for evidence packs and debit notes. Implements domain PackRenderer.

Look: a controlled audit document. Monochrome ink on white with one amber
accent, built-in Helvetica/Courier (an IBM-Plex-like grotesk + mono pairing),
hairline table rules, and a footer carrying the short pack hash on every page.
The renderer only lays out the document it is given; it computes nothing.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.domain.money import format_inr
from app.domain.schemas.evidence import EvidenceFrame, EvidencePackDocument

INK = colors.HexColor("#141414")
GREY = colors.HexColor("#5C5C5C")
RULE = colors.HexColor("#B8B8B8")
FAINT = colors.HexColor("#F3F3F1")
AMBER = colors.HexColor("#D98B06")
AMBER_TINT = colors.HexColor("#FDF1D8")

SANS, SANS_B, MONO, MONO_B = "Helvetica", "Helvetica-Bold", "Courier", "Courier-Bold"

PAGE_W, PAGE_H = A4
MARGIN_X = 15 * mm
CONTENT_W = PAGE_W - 2 * MARGIN_X
TOP = 24 * mm
BOTTOM = 20 * mm

_RUPEE_FONT = "FMRupee"
_RUPEE_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/Library/Fonts/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
)


def _register_rupee_font() -> bool:
    """Built-in PDF fonts have no rupee glyph; borrow one glyph from a system TTF if present."""
    if _RUPEE_FONT in pdfmetrics.getRegisteredFontNames():
        return True
    for candidate in _RUPEE_CANDIDATES:
        if Path(candidate).exists():
            try:
                pdfmetrics.registerFont(TTFont(_RUPEE_FONT, candidate))
                return True
            except Exception:  # noqa: BLE001 - any bad font file just means fallback text
                continue
    return False


_HAS_RUPEE = _register_rupee_font()


def _text(value: object) -> str:
    """Escape for Paragraph markup; keep the rupee sign (own font, else 'Rs.')
    and replace anything the WinAnsi built-in fonts cannot encode."""
    out: list[str] = []
    for ch in str(value):
        if ch == "₹":
            out.append(f'<font name="{_RUPEE_FONT}">₹</font>' if _HAS_RUPEE else "Rs.&nbsp;")
            continue
        try:
            ch.encode("cp1252")
        except UnicodeEncodeError:
            ch = "?"
        out.append(escape(ch))
    return "".join(out)


def _style(name: str, **kw: Any) -> ParagraphStyle:
    base: dict[str, Any] = {"fontName": SANS, "fontSize": 9, "leading": 12, "textColor": INK}
    base.update(kw)
    return ParagraphStyle(name, **base)


S_BODY = _style("body")
S_SMALL = _style("small", fontSize=7.5, leading=10, textColor=GREY)
S_LABEL = _style("label", fontName=SANS_B, fontSize=6.5, leading=8, textColor=GREY, charSpace=0.8)
S_VALUE = _style("value", fontSize=9, leading=11.5)
S_MONO = _style("mono", fontName=MONO, fontSize=7.5, leading=10)
S_MONO_SMALL = _style("monosmall", fontName=MONO, fontSize=6.5, leading=8.5, textColor=GREY)
S_H = _style("h", fontName=SANS_B, fontSize=8, leading=10, charSpace=1.1)
S_TITLE = _style("title", fontName=SANS_B, fontSize=19, leading=22)
S_EYEBROW = _style("eyebrow", fontName=SANS_B, fontSize=7, leading=9, textColor=GREY, charSpace=1.4)
S_TH = _style("th", fontName=SANS_B, fontSize=6.8, leading=8.5, textColor=INK, charSpace=0.6)
S_TH_R = _style("thr", fontName=SANS_B, fontSize=6.8, leading=8.5, charSpace=0.6, alignment=TA_RIGHT)
S_CELL = _style("cell", fontSize=8.5, leading=10.5)
S_CELL_R = _style("cellr", fontSize=8.5, leading=10.5, alignment=TA_RIGHT)
S_CELL_MONO_R = _style("cellmr", fontName=MONO, fontSize=8.5, leading=10.5, alignment=TA_RIGHT)
S_CELL_SUB = _style("cellsub", fontSize=6.8, leading=8.5, textColor=GREY)
S_CELL_SUB_R = _style("cellsubr", fontSize=6.8, leading=8.5, textColor=GREY, alignment=TA_RIGHT)
S_QUOTE = _style("quote", fontSize=9, leading=12.5)
S_VERDICT = _style("verdict", fontName=SANS_B, fontSize=14, leading=17, charSpace=0.8)
S_AMOUNT = _style("amount", fontName=MONO_B, fontSize=21, leading=24)
S_BANNER = _style("banner", fontName=SANS_B, fontSize=7.2, leading=9.6, charSpace=0.3)

VERDICT_TEXT = {
    "approve": "VERIFIED - APPROVE",
    "partial_pay": "PARTIAL PAY",
    "hold": "PAYMENT ON HOLD",
    "human_review": "NEEDS HUMAN REVIEW",
}


def _p(value: object, style: ParagraphStyle = S_VALUE) -> Paragraph:
    return Paragraph(_text(value), style)


def _label(value: str) -> Paragraph:
    return Paragraph(_text(value.upper()), S_LABEL)


def _section(number: str, title: str) -> list[Any]:
    head = Table(
        [[Paragraph(_text(f"{number}   {title.upper()}"), S_H)]],
        colWidths=[CONTENT_W],
        style=TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.9, INK),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )
    return [Spacer(1, 11), head, Spacer(1, 6)]


def _joined(head: list[Any], first: Any, *rest: Any) -> list[Any]:
    """Keep a section heading on the same page as its first block."""
    return [KeepTogether([*head, first]), *rest]


def _banner(text: str) -> Table:
    return Table(
        [[Paragraph(_text(text), S_BANNER)]],
        colWidths=[CONTENT_W],
        style=TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, AMBER),
                ("BACKGROUND", (0, 0), (-1, -1), AMBER_TINT),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        ),
    )


def _kv_grid(pairs: Sequence[tuple[str, str]], cols: int = 3) -> Table:
    rows: list[list[Any]] = []
    for start in range(0, len(pairs), cols):
        chunk = list(pairs[start : start + cols])
        chunk += [("", "")] * (cols - len(chunk))
        rows.append([[_label(k), _p(v)] if k else "" for k, v in chunk])
    return Table(
        rows,
        colWidths=[CONTENT_W / cols] * cols,
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
            ]
        ),
    )


def _fmt_dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M UTC") if value else "-"


# ---------------------------------------------------------------- canvas
class _NumberedCanvas(rl_canvas.Canvas):
    """Two-pass canvas so the footer can say 'Page x of y'."""

    footer_left = ""
    footer_hash = ""
    header_left = ""
    header_right = ""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved: list[dict[str, Any]] = []

    def showPage(self) -> None:  # noqa: N802 - reportlab API
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self._decorate(total)
            super().showPage()
        super().save()

    def _decorate(self, total: int) -> None:
        self.saveState()
        # header
        self.setFont(SANS_B, 7)
        self.setFillColor(INK)
        self.drawString(MARGIN_X, PAGE_H - 13 * mm, self.header_left)
        self.setFont(MONO, 7)
        self.setFillColor(GREY)
        self.drawRightString(PAGE_W - MARGIN_X, PAGE_H - 13 * mm, self.header_right)
        self.setStrokeColor(AMBER)
        self.setLineWidth(2)
        self.line(MARGIN_X, PAGE_H - 15.2 * mm, PAGE_W - MARGIN_X, PAGE_H - 15.2 * mm)
        # footer
        self.setStrokeColor(RULE)
        self.setLineWidth(0.5)
        self.line(MARGIN_X, 14 * mm, PAGE_W - MARGIN_X, 14 * mm)
        self.setFont(SANS, 6.8)
        self.setFillColor(GREY)
        self.drawString(MARGIN_X, 10 * mm, self.footer_left)
        self.setFont(MONO_B, 7)
        self.setFillColor(INK)
        self.drawCentredString(PAGE_W / 2 + 18 * mm, 10 * mm, self.footer_hash)
        self.setFont(SANS, 6.8)
        self.setFillColor(GREY)
        self.drawRightString(PAGE_W - MARGIN_X, 10 * mm, f"Page {self._pageNumber} of {total}")
        self.restoreState()


def _canvas_class(header_left: str, header_right: str, footer_left: str, footer_hash: str) -> type[_NumberedCanvas]:
    return type(
        "_PackCanvas",
        (_NumberedCanvas,),
        {
            "header_left": header_left,
            "header_right": header_right,
            "footer_left": footer_left,
            "footer_hash": footer_hash,
        },
    )


def _build(story: list[Any], canvas_cls: type[_NumberedCanvas], title: str) -> bytes:
    buffer = io.BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=TOP,
        bottomMargin=BOTTOM,
        title=title,
        author="FourthMatch (synthetic data)",
        subject="Procurement payment-hold evidence (synthetic)",
        invariant=1,  # deterministic bytes for identical content
    )
    frame = Frame(MARGIN_X, BOTTOM, CONTENT_W, PAGE_H - TOP - BOTTOM, id="body", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame])])
    doc.build(story, canvasmaker=canvas_cls)
    return buffer.getvalue()


# ------------------------------------------------------------- sections
def _title_block(doc: EvidencePackDocument) -> Table:
    left = [
        Paragraph("PAYMENT-HOLD EVIDENCE PACK", S_EYEBROW),
        Spacer(1, 3),
        _p(doc.case.po_number, S_TITLE),
        Spacer(1, 2),
        _p(doc.case.vendor_name, _style("vend", fontSize=10.5, leading=13)),
        Spacer(1, 2),
        _p(f"Delivery {doc.case.delivery_id}  |  GRN {doc.case.grn_number or '-'}  |  Invoice {doc.case.invoice_number or '-'}",
           S_SMALL),
    ]
    held_label = "Amount held" if doc.amount_held_paise else "Amount held"
    right = [
        _label("Verdict"),
        Spacer(1, 2),
        Paragraph(_text(VERDICT_TEXT.get(doc.verdict.value, doc.verdict.value.upper())), S_VERDICT),
        Spacer(1, 6),
        _label(held_label),
        Paragraph(_text(doc.amount_held_display), S_AMOUNT),
        Spacer(1, 1),
        _p(f"of {doc.at_risk_display} value at risk", S_SMALL),
    ]
    return Table(
        [[left, right]],
        colWidths=[CONTENT_W * 0.56, CONTENT_W * 0.44],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("BOX", (1, 0), (1, 0), 1, INK),
                ("LINEBEFORE", (1, 0), (1, 0), 4, AMBER),
                ("LEFTPADDING", (1, 0), (1, 0), 11),
                ("TOPPADDING", (1, 0), (1, 0), 8),
                ("BOTTOMPADDING", (1, 0), (1, 0), 9),
            ]
        ),
    )


def _summary_section(doc: EvidencePackDocument) -> list[Any]:
    c = doc.case
    pairs = [
        ("Purchase order", c.po_number),
        ("Vendor", c.vendor_name),
        ("Scenario", c.scenario_id or "-"),
        ("PO value", c.po_total_display),
        ("Order / expected", f"{c.order_date} / {c.expected_date}"),
        ("Policy version", c.policy_version or "-"),
        ("Lines evaluated", f"{c.lines_evaluated} of {c.lines_total}"),
        ("Sign-off required", ", ".join(r.replace("_", " ").title() for r in doc.signoff_roles) or "None"),
        ("Generated", _fmt_dt(doc.generated_at)),
    ]
    return _joined(_section("01", "Case summary"), _kv_grid(pairs))


def _variance_text(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}%"


def _four_match_section(doc: EvidencePackDocument) -> list[Any]:
    header = [
        Paragraph("LINE", S_TH),
        Paragraph("ITEM", S_TH),
        Paragraph("PO", S_TH_R),
        Paragraph("GRN", S_TH_R),
        Paragraph("INVOICE", S_TH_R),
        Paragraph("VISION", S_TH_R),
        Paragraph("SHORT VS PO", S_TH_R),
        Paragraph("HELD", S_TH_R),
    ]
    rows: list[list[Any]] = [header]
    shaded: list[tuple[Any, ...]] = []
    for i, row in enumerate(doc.four_match, start=1):
        vision = "-" if row.vision_count is None else str(row.vision_count)
        vision_sub = {"video": "SAM tracks", "document": "from GRN", "none": "no evidence"}.get(row.vision_source, "")
        if row.evidence_quality == "insufficient":
            vision_sub += " (weak)"
        rows.append(
            [
                _p(str(row.line_no), S_CELL),
                [_p(row.description, S_CELL), _p(f"{row.sku}  |  {row.unit}  |  @ {row.unit_price_display}", S_CELL_SUB)],
                _p(str(row.po_qty), S_CELL_MONO_R),
                _p("-" if row.grn_qty is None else str(row.grn_qty), S_CELL_MONO_R),
                _p(str(row.invoiced_qty), S_CELL_MONO_R),
                [_p(vision, S_CELL_MONO_R), _p(vision_sub, S_CELL_SUB_R)],
                _p(_variance_text(row.variance_pct), S_CELL_MONO_R),
                [_p(row.held_display, S_CELL_R), _p((row.verdict.value if row.verdict else "-").replace("_", " "), S_CELL_SUB_R)],
            ]
        )
        if row.contradicts_grn:
            shaded.append(("BACKGROUND", (5, i), (5, i), AMBER_TINT))
            shaded.append(("BOX", (5, i), (5, i), 0.9, AMBER))
    widths = [26, CONTENT_W - 26 - 36 - 36 - 48 - 66 - 62 - 66, 36, 36, 48, 66, 62, 66]
    table = Table(
        rows,
        colWidths=widths,
        repeatRows=1,
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEABOVE", (0, 0), (-1, 0), 0.9, INK),
                ("LINEBELOW", (0, 0), (-1, 0), 0.9, INK),
                ("LINEBELOW", (0, 1), (-1, -1), 0.25, RULE),
                ("LINEBELOW", (0, -1), (-1, -1), 0.9, INK),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                *shaded,
            ]
        ),
    )
    legend = _p(
        "Four-way match: PO = ordered, GRN = signed goods-receipt quantity, Invoice = billed, Vision = distinct "
        "tracked objects counted in Python from SAM segmentation of the dock video. An amber box marks a Vision "
        "count that contradicts the signed GRN.",
        S_SMALL,
    )
    return _joined(_section("02", "Four-way match"), table, Spacer(1, 4), legend)


def _policy_section(doc: EvidencePackDocument) -> list[Any]:
    section_head = _section("03", "Policy basis")
    if not doc.cited_clauses:
        return _joined(section_head, _p("No policy rule was triggered. Every evaluated line matched within the stated tolerances.", S_BODY))
    parts: list[Any] = []
    for index, clause in enumerate(doc.cited_clauses):
        lines = ", ".join(str(n) for n in clause.line_nos)
        head = _p(
            f"Clause {clause.clause_id}   |   rule {clause.rule_id}   |   action {clause.action.replace('_', ' ').upper()}"
            f"   |   line {lines}",
            _style("ch", fontName=SANS_B, fontSize=8, leading=10),
        )
        source = (
            "Verbatim from the policy document"
            if clause.clause_source == "policy_document"
            else "Source text of the compiled rule (clause not found in the current policy document)"
        )
        block = Table(
            [[[head, Spacer(1, 3), _p(clause.clause_text, S_QUOTE), Spacer(1, 3), _p(source, S_SMALL)]]],
            colWidths=[CONTENT_W],
            style=TableStyle(
                [
                    ("LINEBEFORE", (0, 0), (0, 0), 3, AMBER),
                    ("BACKGROUND", (0, 0), (0, 0), FAINT),
                    ("LEFTPADDING", (0, 0), (0, 0), 10),
                    ("RIGHTPADDING", (0, 0), (0, 0), 8),
                    ("TOPPADDING", (0, 0), (0, 0), 6),
                    ("BOTTOMPADDING", (0, 0), (0, 0), 7),
                ]
            ),
        )
        if index == 0:
            parts.append(KeepTogether([*section_head, block]))
        else:
            parts.append(KeepTogether(block))
        parts.append(Spacer(1, 5))
    return parts


def _frame_cell(frame: EvidenceFrame, data: bytes | None, width: float) -> list[Any]:
    cell: list[Any] = []
    if data:
        reader = ImageReader(io.BytesIO(data))
        iw, ih = reader.getSize()
        height = width * ih / iw
        cell.append(Image(io.BytesIO(data), width=width, height=height))
    else:
        cell.append(_p("(image unavailable)", S_SMALL))
    stamp = f"t = {frame.t_seconds:.1f} s" if frame.t_seconds is not None else "t = -"
    cell.append(Spacer(1, 2))
    cell.append(_p(f"F{frame.index}  |  {stamp}", _style("fc", fontName=SANS_B, fontSize=7, leading=9)))
    cell.append(_p(frame.label, S_CELL_SUB))
    cell.append(Paragraph(f"sha256 {frame.sha256[:16]}", S_MONO_SMALL))
    return cell


def _frames_section(doc: EvidencePackDocument, frames: dict[str, bytes]) -> list[Any]:
    head = _section("04", "Evidence frames")
    if not doc.frames:
        return _joined(head, _p(doc.frames_note or "No video frames are attached to this pack.", S_BODY))
    cols = 4 if len(doc.frames) == 4 else 3  # four frames fit on one row
    gap = 8
    width = (CONTENT_W - gap * (cols - 1)) / cols
    cells = [_frame_cell(f, frames.get(f.filename), width) for f in doc.frames]
    rows = [cells[i : i + cols] for i in range(0, len(cells), cols)]
    for row in rows:
        row.extend([[]] * (cols - len(row)))
    table = Table(
        rows,
        colWidths=[width + gap] * cols,
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), gap),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        ),
    )
    rest: list[Any] = []
    if doc.video_sha256:
        rest.append(_p(f"Source video SHA-256  {doc.video_sha256}", S_MONO_SMALL))
    return _joined(head, table, *rest)


def _trace_section(doc: EvidencePackDocument) -> list[Any]:
    head = _section("05", "Agent trace summary")
    trace = doc.agent_trace
    if not trace.recorded:
        return _joined(head, _p(trace.note, S_BODY))
    pairs = [
        ("Decision", f"#{trace.decision_id} - {(trace.verdict or '').replace('_', ' ')}"),
        ("Decided by", trace.decided_by or "-"),
        ("Decided at", _fmt_dt(trace.decided_at)),
    ]
    if trace.model:
        pairs.append(("Model", trace.model))
    parts: list[Any] = [Spacer(1, 4)]
    if trace.summary or trace.reason:
        parts.append(_p(trace.summary or trace.reason or "", S_BODY))
    if trace.recommended_action:
        parts.append(Spacer(1, 3))
        parts.append(_p(f"Recommended action: {trace.recommended_action}", S_SMALL))
    if trace.steps:
        shown = trace.steps[:14]
        rows: list[list[Any]] = [[Paragraph("#", S_TH), Paragraph("TOOL", S_TH), Paragraph("DETAIL", S_TH)]]
        for step in shown:
            rows.append([_p(str(step.seq), S_CELL), Paragraph(_text(step.tool), S_MONO), _p(step.detail, S_CELL_SUB)])
        parts.append(Spacer(1, 5))
        parts.append(
            Table(
                rows,
                colWidths=[22, 110, CONTENT_W - 132],
                repeatRows=1,
                style=TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LINEABOVE", (0, 0), (-1, 0), 0.9, INK),
                        ("LINEBELOW", (0, 0), (-1, 0), 0.9, INK),
                        ("LINEBELOW", (0, 1), (-1, -1), 0.25, RULE),
                        ("LEFTPADDING", (0, 0), (-1, -1), 3),
                        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                    ]
                ),
            )
        )
        if len(trace.steps) > len(shown):
            parts.append(_p(f"{len(trace.steps) - len(shown)} further steps are in the JSON pack.", S_SMALL))
    return _joined(head, _kv_grid(pairs), *parts)


def _provenance_section(doc: EvidencePackDocument, pack_sha256: str) -> list[Any]:
    m = doc.models

    def model(value: str) -> str:
        return value or "(not configured)"

    pairs = [
        ("Perception model", model(m.perception_model)),
        ("Decision model", model(m.decision_model)),
        ("Policy compiler model", model(m.compiler_model)),
        ("Segmentation model", model(m.seg_model)),
        ("Schema version", doc.schema_version),
        ("Generated", _fmt_dt(doc.generated_at)),
    ]
    sign = [Spacer(1, 4), _label("Sign-off")]
    roles = doc.signoff_roles or ["reviewer"]
    sign_rows = [
        [_p(r.replace("_", " ").title(), S_VALUE), "", _p("Date", S_SMALL), ""] for r in roles
    ]
    sign_table = Table(
        sign_rows,
        colWidths=[130, CONTENT_W - 130 - 30 - 130, 30, 130],
        style=TableStyle(
            [
                ("LINEBELOW", (1, 0), (1, -1), 0.5, INK),
                ("LINEBELOW", (3, 0), (3, -1), 0.5, INK),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ]
        ),
    )
    hash_block = Table(
        [
            [
                [
                    _label("Pack SHA-256 (of evidence_pack.json)"),
                    Spacer(1, 2),
                    Paragraph(_text(pack_sha256), _style("hx", fontName=MONO_B, fontSize=8, leading=10.5)),
                    Spacer(1, 3),
                    _p(
                        "Re-verify: GET /api/evidence/{sha256}/verify re-hashes the stored JSON, this PDF and every "
                        "frame, and reports any file that no longer matches.",
                        S_SMALL,
                    ),
                ]
            ]
        ],
        colWidths=[CONTENT_W],
        style=TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.9, INK),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        ),
    )
    return _joined(
        _section("06", "Provenance and sign-off"),
        _kv_grid(pairs),
        Spacer(1, 6),
        _p(doc.numbers_note, S_SMALL),
        Spacer(1, 8),
        KeepTogether([hash_block, Spacer(1, 4), *sign, sign_table]),
    )


# ----------------------------------------------------------------- render
class ReportLabRenderer:
    """Implements domain.evidence.PackRenderer."""

    def render_pack(self, doc: EvidencePackDocument, frames: dict[str, bytes], pack_sha256: str) -> bytes:
        story: list[Any] = [
            _title_block(doc),
            Spacer(1, 9),
            _banner(doc.synthetic_banner),
            *_summary_section(doc),
            *_four_match_section(doc),
            *_policy_section(doc),
            *_frames_section(doc, frames),
            *_trace_section(doc),
            *_provenance_section(doc, pack_sha256),
        ]
        canvas_cls = _canvas_class(
            header_left="FOURTHMATCH   |   EVIDENCE PACK",
            header_right=f"{doc.case.po_number}   delivery {doc.case.delivery_id}",
            footer_left="SYNTHETIC DATA - not a real transaction",
            footer_hash=f"SHA-256 {pack_sha256[:12]}...",
        )
        return _build(story, canvas_cls, f"Evidence pack {doc.case.po_number}")

    def render_debit_note(self, doc: EvidencePackDocument, pack_sha256: str) -> bytes:
        note = doc.debit_note
        if note is None:
            raise ValueError("pack has no debit note section")
        head = Table(
            [
                [
                    [
                        Paragraph("DEBIT NOTE", S_EYEBROW),
                        Spacer(1, 3),
                        _p(note.number, S_TITLE),
                        Spacer(1, 3),
                        _p(f"Issued {note.issue_date}", S_SMALL),
                    ],
                    [
                        _label("Debit amount"),
                        Paragraph(_text(note.total_display), S_AMOUNT),
                        Spacer(1, 1),
                        _p("ex-GST, computed in Python", S_SMALL),
                    ],
                ]
            ],
            colWidths=[CONTENT_W * 0.56, CONTENT_W * 0.44],
            style=TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("BOX", (1, 0), (1, 0), 1, INK),
                    ("LINEBEFORE", (1, 0), (1, 0), 4, AMBER),
                    ("LEFTPADDING", (1, 0), (1, 0), 11),
                    ("TOPPADDING", (1, 0), (1, 0), 8),
                    ("BOTTOMPADDING", (1, 0), (1, 0), 9),
                ]
            ),
        )
        parties = _kv_grid(
            [
                ("To (supplier)", note.vendor_name),
                ("Purchase order", note.po_number),
                ("Supplier invoice", note.invoice_number or "-"),
                ("Evidence pack", f"{pack_sha256[:16]}..."),
                ("Policy version", doc.case.policy_version or "-"),
                ("Delivery", str(doc.case.delivery_id)),
            ]
        )
        header = [
            Paragraph("LINE", S_TH),
            Paragraph("DESCRIPTION", S_TH),
            Paragraph("QTY", S_TH_R),
            Paragraph("RATE", S_TH_R),
            Paragraph("AMOUNT", S_TH_R),
        ]
        rows: list[list[Any]] = [header]
        for line in note.lines:
            rows.append(
                [
                    _p(str(line.line_no), S_CELL),
                    [
                        _p(line.description, S_CELL),
                        _p(f"{line.reason}  Clause {', '.join(line.clauses) or '-'}.", S_CELL_SUB),
                    ],
                    _p("-" if line.qty is None else f"{line.qty} {line.unit}", S_CELL_MONO_R),
                    _p(format_inr(line.unit_price_paise, decimals=True), S_CELL_MONO_R),
                    _p(line.amount_display, S_CELL_MONO_R),
                ]
            )
        rows.append(["", "", "", _p("TOTAL DEBIT", _style("tot", fontName=SANS_B, fontSize=7.5, alignment=TA_RIGHT)),
                     _p(note.total_display, _style("totv", fontName=MONO_B, fontSize=9.5, alignment=TA_RIGHT))])
        widths = [28, CONTENT_W - 28 - 70 - 70 - 82, 70, 70, 82]
        table = Table(
            rows,
            colWidths=widths,
            repeatRows=1,
            style=TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEABOVE", (0, 0), (-1, 0), 0.9, INK),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.9, INK),
                    ("LINEBELOW", (0, 1), (-1, -2), 0.25, RULE),
                    ("LINEABOVE", (0, -1), (-1, -1), 0.9, INK),
                    ("LINEBELOW", (0, -1), (-1, -1), 0.9, INK),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            ),
        )
        story: list[Any] = [
            head,
            Spacer(1, 9),
            _banner(doc.synthetic_banner),
            *_section("01", "Parties and references"),
            parties,
            *_section("02", "Basis of debit"),
            table,
            Spacer(1, 6),
            _p(
                "This debit note recovers the value of goods invoiced but not received or not acceptable, as shown "
                "by the four-way match in the linked evidence pack. The undisputed portion of the invoice is payable "
                "on its standard terms. Amounts are ex-GST.",
                S_SMALL,
            ),
            Spacer(1, 18),
            Table(
                [[_p("Authorised signatory", S_SMALL), "", _p("Date", S_SMALL), ""]],
                colWidths=[110, 190, 30, CONTENT_W - 330],
                style=TableStyle(
                    [
                        ("LINEBELOW", (1, 0), (1, 0), 0.5, INK),
                        ("LINEBELOW", (3, 0), (3, 0), 0.5, INK),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                    ]
                ),
            ),
        ]
        canvas_cls = _canvas_class(
            header_left="FOURTHMATCH   |   DEBIT NOTE",
            header_right=f"{note.number}   {note.po_number}",
            footer_left="SYNTHETIC DATA - not a real transaction",
            footer_hash=f"Evidence pack SHA-256 {pack_sha256[:12]}...",
        )
        return _build(story, canvas_cls, f"Debit note {note.number}")
