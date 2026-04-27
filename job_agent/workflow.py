from __future__ import annotations

from dataclasses import dataclass, field

from langgraph.graph import StateGraph, END

from job_agent.config import Settings
from job_agent.db import Database
from job_agent.matching import score_job
from job_agent.sourcing import extract_basic_fields, load_job_input


@dataclass
class IngestState:
    urls: list[str]
    ingested_job_ids: list[int] = field(default_factory=list)


def build_ingest_graph(*, settings: Settings, db: Database):
    graph = StateGraph(IngestState)

    def ingest_one(state: IngestState) -> IngestState:
        if not state.urls:
            return state
        raw = state.urls.pop(0)
        canonical_url, payload = load_job_input(raw)
        fields = extract_basic_fields(canonical_url, payload)
        job_id = db.upsert_job(
            source="url",
            url=fields["url"],
            company=fields["company"],
            title=fields["title"],
            location=fields["location"],
            description_text=fields["description_text"],
        )
        state.ingested_job_ids.append(job_id)
        return state

    def should_continue(state: IngestState):
        return "continue" if state.urls else "done"

    graph.add_node("ingest_one", ingest_one)
    graph.set_entry_point("ingest_one")
    graph.add_conditional_edges("ingest_one", should_continue, {"continue": "ingest_one", "done": END})
    return graph.compile()


def recompute_shortlist(*, settings: Settings, db: Database, limit: int = 200) -> int:
    jobs = db.list_jobs(limit=limit)
    profile_keywords = list({*settings.target_roles_list, *settings.preferred_locations_list})
    # Keep some skills and known tech as default hints
    profile_keywords += ["python", "linux", "azure", "aws", "oci", "devops", "docker", "kubernetes", "terraform"]

    count = 0
    for j in jobs:
        score, reasons = score_job(
            title=j["title"],
            location=j["location"],
            description_text=j["description_text"],
            target_roles=settings.target_roles_list,
            preferred_locations=settings.preferred_locations_list,
            profile_keywords=profile_keywords,
        )
        db.put_shortlist(int(j["id"]), score, reasons)
        count += 1
    return count

