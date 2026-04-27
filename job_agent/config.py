from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    job_agent_db_path: str = "./job_agent.sqlite"
    artifacts_dir: str = "./out"
    base_resume_path: str = "./data/base_resume.md"

    # OpenAI-compatible configuration
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str | None = None

    preferred_locations: str = "Hyderabad,Remote"
    target_roles: str = "Cloud Engineer,DevOps Engineer,AI Analyst"

    # Continuous runner knobs
    poll_interval_s: int = 1800  # 30 minutes
    shortlist_min_score: float = 6.5
    max_applies_per_day: int = 10
    auto_submit: bool = False  # when True, click final submit in supported ATS flows

    @property
    def preferred_locations_list(self) -> list[str]:
        return [x.strip() for x in self.preferred_locations.split(",") if x.strip()]

    @property
    def target_roles_list(self) -> list[str]:
        return [x.strip() for x in self.target_roles.split(",") if x.strip()]


def get_settings() -> Settings:
    return Settings()

