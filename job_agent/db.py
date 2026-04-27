from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime


SCHEMA = """
CREATE TABLE IF NOT EXISTS job_postings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  company TEXT,
  title TEXT,
  location TEXT,
  description_text TEXT,
  scraped_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shortlist (
  job_id INTEGER PRIMARY KEY,
  score REAL NOT NULL,
  reasons_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(job_id) REFERENCES job_postings(id)
);

CREATE TABLE IF NOT EXISTS resume_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL,
  base_resume_path TEXT NOT NULL,
  tailored_resume_path TEXT NOT NULL,
  keyword_report_path TEXT NOT NULL,
  used_llm INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(job_id) REFERENCES job_postings(id)
);

CREATE TABLE IF NOT EXISTS applications (
  job_id INTEGER PRIMARY KEY,
  status TEXT NOT NULL,
  applied_url TEXT,
  resume_version_id INTEGER,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  note TEXT,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(job_id) REFERENCES job_postings(id),
  FOREIGN KEY(resume_version_id) REFERENCES resume_versions(id)
);

CREATE TABLE IF NOT EXISTS rate_limits (
  day TEXT PRIMARY KEY,
  applies_count INTEGER NOT NULL
);
"""


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class Database:
    def __init__(self, path: str):
        self.path = path
        self._init()

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path)
        try:
            con.row_factory = sqlite3.Row
            yield con
            con.commit()
        finally:
            con.close()

    def _init(self):
        with self.connect() as con:
            con.executescript(SCHEMA)
            self._migrate(con)

    def _migrate(self, con: sqlite3.Connection) -> None:
        """
        Lightweight, idempotent migrations for existing sqlite files.
        """
        # applications table column additions
        cols = {row["name"] for row in con.execute("PRAGMA table_info(applications)").fetchall()}
        if "applied_url" not in cols:
            con.execute("ALTER TABLE applications ADD COLUMN applied_url TEXT")
        if "resume_version_id" not in cols:
            con.execute("ALTER TABLE applications ADD COLUMN resume_version_id INTEGER")
        if "attempt_count" not in cols:
            con.execute("ALTER TABLE applications ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0")
        if "last_error" not in cols:
            con.execute("ALTER TABLE applications ADD COLUMN last_error TEXT")

        # rate_limits table existence (older DBs won't have it)
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS rate_limits (
              day TEXT PRIMARY KEY,
              applies_count INTEGER NOT NULL
            )
            """
        )

    def upsert_job(
        self,
        *,
        source: str,
        url: str,
        company: str | None,
        title: str | None,
        location: str | None,
        description_text: str | None,
    ) -> int:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO job_postings (source, url, company, title, location, description_text, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                  source=excluded.source,
                  company=excluded.company,
                  title=excluded.title,
                  location=excluded.location,
                  description_text=excluded.description_text,
                  scraped_at=excluded.scraped_at
                """,
                (source, url, company, title, location, description_text, _utcnow_iso()),
            )
            row = con.execute("SELECT id FROM job_postings WHERE url = ?", (url,)).fetchone()
            return int(row["id"])

    def list_jobs(self, limit: int = 50) -> list[sqlite3.Row]:
        with self.connect() as con:
            return list(
                con.execute(
                    "SELECT * FROM job_postings ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            )

    def get_job(self, job_id: int) -> sqlite3.Row | None:
        with self.connect() as con:
            return con.execute("SELECT * FROM job_postings WHERE id = ?", (job_id,)).fetchone()

    def put_shortlist(self, job_id: int, score: float, reasons: list[str]) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO shortlist (job_id, score, reasons_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                  score=excluded.score,
                  reasons_json=excluded.reasons_json,
                  created_at=excluded.created_at
                """,
                (job_id, float(score), json.dumps(reasons), _utcnow_iso()),
            )

    def list_shortlist(self, top: int = 20) -> list[sqlite3.Row]:
        with self.connect() as con:
            return list(
                con.execute(
                    """
                    SELECT s.job_id, s.score, s.reasons_json, j.company, j.title, j.location, j.url
                    FROM shortlist s
                    JOIN job_postings j ON j.id = s.job_id
                    ORDER BY s.score DESC
                    LIMIT ?
                    """,
                    (top,),
                ).fetchall()
            )

    def add_resume_version(
        self,
        job_id: int,
        *,
        base_resume_path: str,
        tailored_resume_path: str,
        keyword_report_path: str,
        used_llm: bool,
    ) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO resume_versions (
                  job_id, base_resume_path, tailored_resume_path, keyword_report_path, used_llm, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    base_resume_path,
                    tailored_resume_path,
                    keyword_report_path,
                    1 if used_llm else 0,
                    _utcnow_iso(),
                ),
            )

    def get_latest_resume_version(self, job_id: int) -> sqlite3.Row | None:
        with self.connect() as con:
            return con.execute(
                """
                SELECT * FROM resume_versions
                WHERE job_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()

    def increment_daily_applies(self, day: str) -> int:
        """
        day: YYYY-MM-DD in UTC.
        Returns new count.
        """
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO rate_limits(day, applies_count)
                VALUES(?, 0)
                ON CONFLICT(day) DO NOTHING
                """,
                (day,),
            )
            con.execute(
                "UPDATE rate_limits SET applies_count = applies_count + 1 WHERE day = ?",
                (day,),
            )
            row = con.execute("SELECT applies_count FROM rate_limits WHERE day = ?", (day,)).fetchone()
            return int(row["applies_count"])

    def get_daily_applies(self, day: str) -> int:
        with self.connect() as con:
            row = con.execute("SELECT applies_count FROM rate_limits WHERE day = ?", (day,)).fetchone()
            return int(row["applies_count"]) if row else 0

    def set_application_status(self, job_id: int, status: str, note: str | None = None) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO applications (job_id, status, note, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                  status=excluded.status,
                  note=excluded.note,
                  updated_at=excluded.updated_at
                """,
                (job_id, status, note, _utcnow_iso()),
            )

    def record_application_attempt(
        self,
        *,
        job_id: int,
        status: str,
        applied_url: str | None = None,
        resume_version_id: int | None = None,
        last_error: str | None = None,
        note: str | None = None,
        increment_attempt: bool = True,
    ) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO applications (job_id, status, applied_url, resume_version_id, attempt_count, last_error, note, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                  status=excluded.status,
                  applied_url=COALESCE(excluded.applied_url, applications.applied_url),
                  resume_version_id=COALESCE(excluded.resume_version_id, applications.resume_version_id),
                  attempt_count=applications.attempt_count + ?,
                  last_error=excluded.last_error,
                  note=excluded.note,
                  updated_at=excluded.updated_at
                """,
                (
                    job_id,
                    status,
                    applied_url,
                    resume_version_id,
                    1 if increment_attempt else 0,
                    last_error,
                    note,
                    _utcnow_iso(),
                    1 if increment_attempt else 0,
                ),
            )

