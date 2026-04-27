from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Template

from job_agent.config import Settings


_PROMPT = """\
You are a meticulous resume editor.

Task:
- Rewrite ONLY: Summary, Skills ordering, and rephrase bullets for relevance.
- Do NOT invent employers, dates, tools, metrics, or projects.
- Preserve truthfulness. If a requirement is missing, do NOT add it.
- Prefer concise, ATS-friendly wording.

Inputs:
1) Candidate base resume (Markdown or plain text)
2) Job description text

Output format (STRICT JSON):
{
  "tailored_resume_markdown": "string",
  "keywords": ["k1","k2", "..."],
  "keyword_placements": [{"keyword":"k","evidence":"where it appears in resume"}],
  "notes": ["short bullet notes about what changed"]
}
"""


def _extract_keywords(jd_text: str) -> list[str]:
    # Simple heuristic keyword extraction (fallback if no LLM):
    jd = jd_text.lower()
    common = [
        "python",
        "linux",
        "azure",
        "aws",
        "gcp",
        "oci",
        "kubernetes",
        "docker",
        "terraform",
        "ansible",
        "ci/cd",
        "github actions",
        "jenkins",
        "monitoring",
        "prometheus",
        "grafana",
        "sql",
        "etl",
        "data engineering",
        "ml",
        "model optimization",
        "datasets",
        "cloud",
        "devops",
        "sre",
    ]
    return [k for k in common if k in jd]


def _fallback_tailor(base_md: str, jd_text: str) -> dict:
    keywords = _extract_keywords(jd_text)
    notes = [
        "Fallback tailoring used (no LLM configured).",
        "Reordered skills by JD keyword hits only.",
    ]

    # naive skills reordering for the Skills section
    lines = base_md.splitlines()
    out_lines: list[str] = []
    in_skills = False
    skills_lines: list[str] = []
    for ln in lines:
        if re.match(r"^##\s+Skills\s*$", ln.strip()):
            in_skills = True
            out_lines.append(ln)
            continue
        if in_skills and ln.startswith("## "):
            in_skills = False
            # flush skills
            skills_text = "\n".join(skills_lines)
            # reorder bullet lines by keyword presence
            bullets = [b for b in skills_lines if b.strip().startswith("-")]
            non_bullets = [b for b in skills_lines if not b.strip().startswith("-")]
            def bullet_score(b: str) -> int:
                bl = b.lower()
                return sum(1 for k in keywords if k in bl)
            bullets.sort(key=bullet_score, reverse=True)
            out_lines.extend(non_bullets + bullets)
            skills_lines = []
            out_lines.append(ln)
            continue
        if in_skills:
            skills_lines.append(ln)
        else:
            out_lines.append(ln)

    if in_skills:
        out_lines.extend(skills_lines)

    tailored = "\n".join(out_lines).strip() + "\n"
    placements = [{"keyword": k, "evidence": "Present in job description; reorder emphasis in Skills"} for k in keywords]
    return {
        "tailored_resume_markdown": tailored,
        "keywords": keywords,
        "keyword_placements": placements,
        "notes": notes,
    }


def tailor_resume(
    *,
    settings: Settings,
    base_resume_text: str,
    job_description_text: str,
) -> tuple[dict, bool]:
    """
    Returns (result_json, used_llm).
    """
    if not settings.openai_api_key:
        return _fallback_tailor(base_resume_text, job_description_text), False

    try:
        from openai import OpenAI
    except Exception:
        return _fallback_tailor(base_resume_text, job_description_text), False

    client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)

    resp = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": _PROMPT},
            {
                "role": "user",
                "content": f"BASE_RESUME:\n\n{base_resume_text}\n\nJOB_DESCRIPTION:\n\n{job_description_text}",
            },
        ],
        temperature=0.2,
    )
    content = resp.choices[0].message.content or ""
    # Extract first JSON object
    m = re.search(r"\{[\s\S]*\}", content)
    if not m:
        return _fallback_tailor(base_resume_text, job_description_text), True
    try:
        data = json.loads(m.group(0))
        if "tailored_resume_markdown" not in data:
            raise ValueError("Missing tailored_resume_markdown")
        return data, True
    except Exception:
        return _fallback_tailor(base_resume_text, job_description_text), True


def write_tailor_artifacts(
    *,
    out_dir: str,
    job_id: int,
    tailor_json: dict,
) -> tuple[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    tailored_path = out / f"resume_tailored_job_{job_id}.md"
    report_path = out / f"keyword_report_job_{job_id}.json"

    tailored_path.write_text(str(tailor_json["tailored_resume_markdown"]).strip() + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(tailor_json, indent=2), encoding="utf-8")

    return str(tailored_path), str(report_path)

