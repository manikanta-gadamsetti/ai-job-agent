from __future__ import annotations

from pathlib import Path
import re


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _md_to_simple_html(md: str) -> str:
    """
    Minimal Markdown-to-HTML for our resume format:
    - # heading -> name
    - ## heading -> section header
    - ### heading -> subsection
    - - bullet -> list item
    - blank lines -> paragraph/list separation
    """
    lines = md.splitlines()
    html_parts: list[str] = []
    in_ul = False

    def close_ul():
        nonlocal in_ul
        if in_ul:
            html_parts.append("</ul>")
            in_ul = False

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            close_ul()
            continue

        if line.startswith("# "):
            close_ul()
            html_parts.append(f"<h1>{_escape_html(line[2:].strip())}</h1>")
            continue

        if line.startswith("## "):
            close_ul()
            html_parts.append(f"<h2>{_escape_html(line[3:].strip())}</h2>")
            continue

        if line.startswith("### "):
            close_ul()
            html_parts.append(f"<h3>{_escape_html(line[4:].strip())}</h3>")
            continue

        m = re.match(r"^\s*-\s+(.*)$", line)
        if m:
            if not in_ul:
                html_parts.append("<ul>")
                in_ul = True
            html_parts.append(f"<li>{_escape_html(m.group(1).strip())}</li>")
            continue

        close_ul()
        html_parts.append(f"<p>{_escape_html(line.strip())}</p>")

    close_ul()
    return "\n".join(html_parts)


def render_resume_md_to_pdf(*, md_path: str, pdf_path: str) -> str:
    md = Path(md_path).read_text(encoding="utf-8", errors="ignore")
    body = _md_to_simple_html(md)

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Resume</title>
  <style>
    @page {{
      size: A4;
      margin: 9mm 9mm;
    }}
    html, body {{
      font-family: Arial, Helvetica, sans-serif;
      font-size: 10pt;
      color: #111;
      line-height: 1.15;
    }}
    h1 {{
      font-size: 18pt;
      margin: 0 0 4px 0;
      letter-spacing: 0.2px;
    }}
    h2 {{
      font-size: 11pt;
      margin: 7px 0 4px 0;
      padding-bottom: 2px;
      border-bottom: 1px solid #ddd;
      text-transform: uppercase;
      letter-spacing: 0.6px;
    }}
    h3 {{
      font-size: 10pt;
      margin: 5px 0 2px 0;
    }}
    p {{
      margin: 0 0 2px 0;
    }}
    ul {{
      margin: 0 0 3px 16px;
      padding: 0;
    }}
    li {{
      margin: 0 0 1px 0;
    }}
    /* Try hard to keep it single-page */
    h1, h2, h3, p, li {{ break-inside: avoid; page-break-inside: avoid; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""

    tmp_html = Path(pdf_path).with_suffix(".render.html")
    tmp_html.write_text(html, encoding="utf-8")

    from playwright.sync_api import sync_playwright

    out_pdf = Path(pdf_path)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(tmp_html.resolve().as_uri(), wait_until="load")
        page.emulate_media(media="print")
        page.pdf(path=str(out_pdf), format="A4", print_background=True, scale=0.98)
        browser.close()

    return str(out_pdf)

