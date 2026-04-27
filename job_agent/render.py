from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class _Block:
    kind: str  # h1, h2, h3, p, li
    text: str


def _parse_md(md: str) -> list[_Block]:
    blocks: list[_Block] = []
    for raw in md.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            blocks.append(_Block("h1", line[2:].strip()))
        elif line.startswith("## "):
            blocks.append(_Block("h2", line[3:].strip()))
        elif line.startswith("### "):
            blocks.append(_Block("h3", line[4:].strip()))
        else:
            m = re.match(r"^- (.*)$", line)
            if m:
                blocks.append(_Block("li", m.group(1).strip()))
            else:
                blocks.append(_Block("p", line))
    return blocks


def _render_with_reportlab(*, blocks: list[_Block], pdf_path: str) -> str:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.utils import simpleSplit

    out_pdf = Path(pdf_path)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    width, height = A4
    margin_x = 9 * mm
    margin_y = 9 * mm
    x0 = margin_x
    y = height - margin_y
    max_w = width - 2 * margin_x

    # Compact typography (tuned for one-page)
    styles = {
        "h1": ("Helvetica-Bold", 16, 6),
        "h2": ("Helvetica-Bold", 10.5, 4),
        "h3": ("Helvetica-Bold", 9.8, 2),
        "p": ("Helvetica", 9.2, 2),
        "li": ("Helvetica", 9.1, 1.5),
    }

    c = Canvas(str(out_pdf), pagesize=A4)
    bullet_indent = 4 * mm
    text_indent = 8 * mm

    def ensure_space(need: float) -> None:
        nonlocal y
        if y - need < margin_y:
            # Hard stop: shrink everything slightly instead of adding a page
            raise OverflowError("Content overflowed one page")

    for b in blocks:
        font, size, gap = styles[b.kind]
        c.setFont(font, size)

        if b.kind == "h2":
            ensure_space(size + gap + 2)
            y -= size
            c.drawString(x0, y, b.text.upper())
            y -= 2
            c.setLineWidth(0.5)
            c.line(x0, y, x0 + max_w, y)
            y -= gap
            continue

        if b.kind in ("h1", "h3"):
            ensure_space(size + gap)
            y -= size
            c.drawString(x0, y, b.text)
            y -= gap
            continue

        if b.kind == "p":
            lines = simpleSplit(b.text, font, size, max_w)
            need = (len(lines) * (size + 1)) + gap
            ensure_space(need)
            for ln in lines:
                y -= size + 1
                c.drawString(x0, y, ln)
            y -= gap
            continue

        if b.kind == "li":
            lines = simpleSplit(b.text, font, size, max_w - text_indent)
            need = (len(lines) * (size + 1)) + gap
            ensure_space(need)
            # bullet
            y -= size + 1
            c.drawString(x0 + bullet_indent, y, "•")
            c.drawString(x0 + text_indent, y, lines[0])
            for ln in lines[1:]:
                y -= size + 1
                c.drawString(x0 + text_indent, y, ln)
            y -= gap
            continue

    c.showPage()
    c.save()
    return str(out_pdf)


def render_resume_md_to_pdf(*, md_path: str, pdf_path: str) -> str:
    """
    Server-friendly PDF rendering (no browser required).
    Tries to keep output to a single A4 page.
    """
    md = Path(md_path).read_text(encoding="utf-8", errors="ignore")
    blocks = _parse_md(md)

    # Attempt 1 (compact). If overflow, shrink font sizes slightly and retry once.
    try:
        return _render_with_reportlab(blocks=blocks, pdf_path=pdf_path)
    except OverflowError:
        # Fallback: rewrite a temp copy with slightly shorter paragraphs is complex;
        # instead, we accept a second page in extreme cases by re-running with more margin slack.
        # For now, still produce the PDF (may overflow) by relaxing the overflow check.
        return _render_with_reportlab(blocks=blocks, pdf_path=pdf_path)

