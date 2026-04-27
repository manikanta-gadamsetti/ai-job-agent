from __future__ import annotations

import math
import re


def _tokens(text: str) -> set[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9+.#/\n ]+", " ", text)
    parts = re.split(r"\s+", text)
    return {p for p in parts if 2 <= len(p) <= 32}


def score_job(
    *,
    title: str | None,
    location: str | None,
    description_text: str | None,
    target_roles: list[str],
    preferred_locations: list[str],
    profile_keywords: list[str],
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0

    title_l = (title or "").lower()
    loc_l = (location or "").lower()
    desc = description_text or ""
    desc_l = desc.lower()

    # Role match
    role_hits = 0
    for role in target_roles:
        r = role.lower()
        if r in title_l or r in desc_l:
            role_hits += 1
    if role_hits:
        score += 3.0 + 1.5 * role_hits
        reasons.append(f"Role match signals: {role_hits}")
    else:
        # still allow discovery, but penalize
        score -= 1.0
        reasons.append("No direct target-role match in title/description")

    # Location match
    loc_hits = 0
    for pl in preferred_locations:
        pl_l = pl.lower()
        if pl_l and (pl_l in loc_l or pl_l in desc_l):
            loc_hits += 1
    if loc_hits:
        score += 2.0
        reasons.append("Preferred location mentioned")
    else:
        # If location unknown, don't punish too much
        if location:
            score -= 0.5
            reasons.append("Preferred location not mentioned")
        else:
            reasons.append("Location missing/unknown")

    # Keyword overlap
    jd_tokens = _tokens(f"{title or ''}\n{location or ''}\n{desc}")
    prof_tokens = {k.lower() for k in profile_keywords if k.strip()}
    overlap = sorted(jd_tokens.intersection(prof_tokens))
    if overlap:
        score += min(4.0, 0.25 * len(overlap))
        reasons.append(f"Keyword overlap: {', '.join(overlap[:12])}" + ("..." if len(overlap) > 12 else ""))
    else:
        reasons.append("No obvious keyword overlap with profile")

    # JD richness heuristic: more text tends to be higher quality
    if len(desc) >= 1500:
        score += 0.5
    elif len(desc) < 300:
        score -= 0.5
        reasons.append("Very short description (possible low quality scrape)")

    # Clamp to a friendly range
    score = max(-5.0, min(10.0, score))
    return score, reasons

