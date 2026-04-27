from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from job_agent.apply_assistant import run_apply_assistant
from job_agent.config import get_settings
from job_agent.db import Database
from job_agent.render import render_resume_md_to_pdf
from job_agent.runner import run_forever, run_once
from job_agent.tailor import tailor_resume, write_tailor_artifacts
from job_agent.workflow import build_ingest_graph, recompute_shortlist


app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


def _db() -> Database:
    settings = get_settings()
    return Database(settings.job_agent_db_path)


@app.command()
def ingest(seed_file: str):
    """
    Ingest job posts from a seed file.

    Seed file format:
    - one entry per line: URL OR local file path (saved HTML or .txt JD)
    - blank lines and lines starting with # are ignored
    """
    settings = get_settings()
    db = Database(settings.job_agent_db_path)

    seed_path = Path(seed_file)
    if not seed_path.exists():
        raise SystemExit(f"Seed file not found: {seed_file}")

    urls: list[str] = []
    raw_lines = seed_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for raw in raw_lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)

    # If the seed file isn't a list of entries (e.g., it's a pasted JD text file),
    # treat the seed file itself as a single ingest input.
    if not urls:
        urls = [seed_file]
    else:
        # If most "entries" contain whitespace, it's probably not a URL list;
        # treat the file itself as one input to avoid ingesting line-by-line.
        whitespace_entries = sum(1 for u in urls if (" " in u or "\t" in u))
        if whitespace_entries >= max(3, len(urls) // 2):
            urls = [seed_file]

    graph = build_ingest_graph(settings=settings, db=db)
    out = graph.invoke({"urls": urls})
    console.print(f"Ingested/updated [bold]{len(out['ingested_job_ids'])}[/bold] job(s).")

    n = recompute_shortlist(settings=settings, db=db)
    console.print(f"Recomputed shortlist scores for [bold]{n}[/bold] jobs.")


@app.command()
def shortlist(top: int = 20):
    """
    Show top-scored jobs.
    """
    settings = get_settings()
    db = Database(settings.job_agent_db_path)
    rows = db.list_shortlist(top=top)

    table = Table(title=f"Top {top} jobs")
    table.add_column("job_id", style="bold")
    table.add_column("score")
    table.add_column("company")
    table.add_column("title")
    table.add_column("location")
    table.add_column("url")
    for r in rows:
        table.add_row(
            str(r["job_id"]),
            f"{float(r['score']):.2f}",
            (r["company"] or "")[:24],
            (r["title"] or "")[:40],
            (r["location"] or "")[:18],
            (r["url"] or "")[:60],
        )
    console.print(table)


@app.command()
def tailor(job_id: int, base_resume: str = "data/base_resume.md", out_dir: str = "out"):
    """
    Generate a tailored resume markdown + keyword report for a job_id.
    """
    settings = get_settings()
    db = Database(settings.job_agent_db_path)
    job = db.get_job(job_id)
    if not job:
        raise SystemExit(f"Job id {job_id} not found")
    if not job["description_text"]:
        raise SystemExit("Job is missing description_text (ingest may have failed).")

    base_text = Path(base_resume).read_text(encoding="utf-8")
    tailor_json, used_llm = tailor_resume(
        settings=settings,
        base_resume_text=base_text,
        job_description_text=job["description_text"],
    )
    tailored_path, report_path = write_tailor_artifacts(out_dir=out_dir, job_id=job_id, tailor_json=tailor_json)

    db.add_resume_version(
        job_id,
        base_resume_path=str(Path(base_resume).resolve()),
        tailored_resume_path=str(Path(tailored_path).resolve()),
        keyword_report_path=str(Path(report_path).resolve()),
        used_llm=used_llm,
    )

    console.print(f"Tailored resume written to [bold]{tailored_path}[/bold]")
    console.print(f"Keyword report written to [bold]{report_path}[/bold]")
    console.print(f"LLM used: [bold]{used_llm}[/bold]")

    # Also render a clean PDF for convenience
    pdf_path = str(Path(tailored_path).with_suffix(".pdf"))
    try:
        out_pdf = render_resume_md_to_pdf(md_path=tailored_path, pdf_path=pdf_path)
        console.print(f"PDF resume written to [bold]{out_pdf}[/bold]")
    except Exception as e:
        console.print(f"[yellow]PDF render skipped:[/yellow] {e}")


@app.command()
def render(md_path: str, pdf_path: str | None = None):
    """
    Render a resume Markdown file into a one-page PDF.
    """
    p = Path(md_path)
    if not p.exists():
        raise SystemExit(f"File not found: {md_path}")
    out = pdf_path or str(p.with_suffix(".pdf"))
    out_pdf = render_resume_md_to_pdf(md_path=str(p), pdf_path=out)
    console.print(f"PDF resume written to [bold]{out_pdf}[/bold]")


@app.command()
def apply(job_id: int):
    """
    Semi-automatic apply helper: opens browser to the apply URL.
    """
    settings = get_settings()
    db = Database(settings.job_agent_db_path)
    run_apply_assistant(db=db, job_id=job_id)
    console.print("Apply assistant finished (status updated in DB).")


@app.command()
def run(seed_file: str = "data/job_seeds.txt", once: bool = False):
    """
    Continuous background runner:
    - (optional) ingest seed URLs/files
    - recompute shortlist
    - for high-score jobs: tailor resume and queue for application

    Note: actual browser-driven auto-apply adapters are added next (Lever/Greenhouse).
    """
    settings = get_settings()
    db = Database(settings.job_agent_db_path)

    if once:
        summary = run_once(settings=settings, db=db, seed_file=seed_file)
        console.print_json(json.dumps(summary))
        return

    run_forever(settings=settings, db=db, seed_file=seed_file)


def main():
    app()


if __name__ == "__main__":
    main()

