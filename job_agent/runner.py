from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from job_agent.config import Settings
from job_agent.db import Database
from job_agent.tailor import tailor_resume, write_tailor_artifacts
from job_agent.workflow import build_ingest_graph, recompute_shortlist


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_seed_entries(seed_file: str) -> list[str]:
    p = Path(seed_file)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    entries = []
    for raw in lines:
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        entries.append(s)
    return entries


def run_once(
    *,
    settings: Settings,
    db: Database,
    seed_file: str,
) -> dict:
    # 1) ingest (URLs or local files)
    entries = _read_seed_entries(seed_file)
    ingested = 0
    if entries:
        graph = build_ingest_graph(settings=settings, db=db)
        out = graph.invoke({"urls": entries})
        ingested = len(out["ingested_job_ids"])

    # 2) shortlist recompute
    rescored = recompute_shortlist(settings=settings, db=db)

    # 3) apply loop (top scored only)
    shortlisted = db.list_shortlist(top=200)
    applied_candidates = [r for r in shortlisted if float(r["score"]) >= float(settings.shortlist_min_score)]

    applies_today = db.get_daily_applies(_utc_day())
    allowed = max(0, int(settings.max_applies_per_day) - int(applies_today))

    applied = 0
    attempted: list[int] = []
    skipped: list[int] = []

    for r in applied_candidates:
        if allowed <= 0:
            break

        job_id = int(r["job_id"])
        job = db.get_job(job_id)
        if not job:
            continue

        # Skip if already submitted
        # (We keep it simple: check applications table row)
        # If missing, it's not applied yet.
        with db.connect() as con:
            row = con.execute("SELECT status FROM applications WHERE job_id = ?", (job_id,)).fetchone()
        if row and row["status"] in ("submitted",):
            skipped.append(job_id)
            continue

        # 3a) tailor resume (store artifacts)
        base_path = Path(settings.base_resume_path)
        if not base_path.exists():
            raise RuntimeError(f"Base resume not found: {settings.base_resume_path}")
        base_text = base_path.read_text(encoding="utf-8", errors="ignore")
        jd_text = job["description_text"] or ""
        tailor_json, used_llm = tailor_resume(settings=settings, base_resume_text=base_text, job_description_text=jd_text)
        tailored_path, report_path = write_tailor_artifacts(out_dir=settings.artifacts_dir, job_id=job_id, tailor_json=tailor_json)

        db.add_resume_version(
            job_id,
            base_resume_path=str(base_path.resolve()),
            tailored_resume_path=str(Path(tailored_path).resolve()),
            keyword_report_path=str(Path(report_path).resolve()),
            used_llm=used_llm,
        )
        latest_rv = db.get_latest_resume_version(job_id)
        resume_version_id = int(latest_rv["id"]) if latest_rv else None

        # 3b) attempt apply (adapter-based)
        # For now, we only queue/record the attempt and open browser via apply_assistant.
        # Adapter implementations come next (Lever/Greenhouse).
        db.record_application_attempt(
            job_id=job_id,
            status="queued",
            applied_url=job["url"],
            resume_version_id=resume_version_id,
            note="Queued by continuous runner",
            increment_attempt=False,
        )
        attempted.append(job_id)
        allowed -= 1

        # Count as an "apply attempt budget" once queued
        db.increment_daily_applies(_utc_day())
        applied += 1

    return {
        "ingested": ingested,
        "rescored": rescored,
        "candidates": len(applied_candidates),
        "queued": applied,
        "attempted_job_ids": attempted,
        "skipped_job_ids": skipped,
    }


def run_forever(
    *,
    settings: Settings,
    db: Database,
    seed_file: str,
) -> None:
    while True:
        summary = run_once(settings=settings, db=db, seed_file=seed_file)
        print(json.dumps({"ts": datetime.utcnow().isoformat() + "Z", **summary}, indent=2))
        time.sleep(max(10, int(settings.poll_interval_s)))

