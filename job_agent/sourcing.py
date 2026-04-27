from __future__ import annotations

import re
from pathlib import Path

import httpx
from bs4 import BeautifulSoup


def _normalize_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    return _normalize_whitespace(text)


def extract_basic_fields(url: str, html: str) -> dict[str, str | None]:
    """
    Best-effort extraction from generic career pages/ATS pages.
    For robust automation, add site-specific adapters later.
    """
    soup = BeautifulSoup(html, "lxml")
    title = None
    if soup.title and soup.title.text:
        title = _normalize_whitespace(soup.title.text)[:160]

    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        title = _normalize_whitespace(h1.get_text(" ", strip=True))[:160]

    company = None
    # Try common meta tags
    og_site = soup.find("meta", attrs={"property": "og:site_name"})
    if og_site and og_site.get("content"):
        company = _normalize_whitespace(str(og_site.get("content")))[:120]

    # Location: extremely variable; keep best-effort
    location = None
    for needle in ["Location", "Job location", "Locations"]:
        el = soup.find(string=re.compile(rf"^{re.escape(needle)}\b", re.I))
        if el and el.parent:
            maybe = el.parent.get_text(" ", strip=True)
            if maybe and len(maybe) < 200:
                location = _normalize_whitespace(maybe)
                break

    description_text = html_to_text(html)
    return {"url": url, "title": title, "company": company, "location": location, "description_text": description_text}


def fetch_url(url: str, timeout_s: float = 30.0) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
    }
    with httpx.Client(follow_redirects=True, timeout=timeout_s, headers=headers) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.text


def load_job_input(raw: str) -> tuple[str, str]:
    """
    Returns (canonical_url, html_or_text).

    Supported inputs:
    - https://... URL (fetched)
    - file://... path to a saved HTML file
    - local path to a saved HTML file
    - local path to a .txt JD file
    """
    s = raw.strip().strip('"').strip("'")
    if not s:
        raise ValueError("Empty input")

    if s.lower().startswith("http://") or s.lower().startswith("https://"):
        return s, fetch_url(s)

    if s.lower().startswith("file://"):
        p = Path(s[7:])
        text = p.read_text(encoding="utf-8", errors="ignore")
        return s, text

    p = Path(s)
    if p.exists() and p.is_file():
        text = p.read_text(encoding="utf-8", errors="ignore")
        return p.resolve().as_uri(), text

    # Unknown format; treat as a "job description text" payload with a synthetic id
    return "text://job", s

