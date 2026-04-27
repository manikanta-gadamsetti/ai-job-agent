from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class JobSource(str):
    pass


class JobPosting(BaseModel):
    id: int | None = None
    source: str = "url"
    url: str
    company: str | None = None
    title: str | None = None
    location: str | None = None
    description_text: str | None = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)


class ShortlistItem(BaseModel):
    job_id: int
    score: float
    reasons: list[str] = Field(default_factory=list)


class TailorResult(BaseModel):
    job_id: int
    base_resume_path: str
    tailored_resume_path: str
    keyword_report_path: str
    used_llm: bool


class ApplyResult(BaseModel):
    job_id: int
    status: Literal["not_started", "in_progress", "blocked", "submitted", "failed"]
    note: str | None = None

