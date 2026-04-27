# Job AI Agent (MVP)

An **AI-assisted job application agent** that:

- **Ingests jobs** from URLs or saved job pages/JDs
- **Scores + shortlists** roles for your target titles/locations
- **Tailors your resume** to the job description (LLM optional, with a safe fallback)
- **Exports a clean one-page PDF** resume per job
- Provides a **background runner** to keep processing continuously

## Capabilities

- **Job sourcing (safe MVP)**: `https://...` links, local saved HTML (`.html`) or job descriptions (`.txt`)
- **Shortlisting**: keyword/role/location-based scoring
- **Resume tailoring**:
  - With LLM: rewrites summary/skills/bullets (no fabrication rules)
  - Without LLM: deterministic keyword-based emphasis
- **Resume export**: render tailored Markdown to an **A4 PDF**
- **Background runner**: periodic ingest → shortlist → tailor → queue

## Quick start (Windows PowerShell)

From `c:\Users\Manik\Downloads\ai-job-agent`:

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install
```

## Configure

Copy `.env.example` to `.env` and fill it.

At minimum, set:
- `JOB_AGENT_DB_PATH` (defaults to `./job_agent.sqlite`)

Optional (resume tailoring via LLM):
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default: `gpt-4.1-mini`)
- `OPENAI_BASE_URL` (optional if using a compatible provider)

Optional (runner tuning):
- `SHORTLIST_MIN_SCORE`
- `MAX_APPLIES_PER_DAY`
- `POLL_INTERVAL_S`
- `AUTO_SUBMIT` (keep `false` unless you fully trust your apply adapters)

## Run the MVP

1) Put job sources into `data/job_seeds.txt` (one per line):

- `https://...` (company/ATS links recommended)
- local file path to saved `.html` or `.txt` JD

2) Run ingestion + ranking:

```bash
python -m job_agent ingest data/job_seeds.txt
python -m job_agent shortlist --top 20
```

3) Tailor your resume for a job (job id from shortlist) and generate PDF:

```bash
python -m job_agent tailor 1 --base-resume data/base_resume.md --out-dir out
```

4) Render an existing tailored resume Markdown to PDF:

```bash
python -m job_agent render out/resume_tailored_job_1.md
```

5) (Optional) Apply assistant (semi-automatic open-in-browser helper):

```bash
python -m job_agent apply 1
```

## Continuous background mode

The runner can periodically ingest new jobs, rescore, tailor a resume, and queue applications.

Run one cycle:

```bash
python -m job_agent run --once --seed-file data/job_seeds.txt
```

Run continuously:

```bash
python -m job_agent run --seed-file data/job_seeds.txt
```

It will queue jobs above `SHORTLIST_MIN_SCORE` and respect `MAX_APPLIES_PER_DAY`.

## Safety and platform limitations

- This MVP avoids direct automation on platforms like LinkedIn/Naukri; use it to ingest JDs and generate tailored PDFs, then apply manually or via company ATS links.
- CAPTCHAs are treated as a **hard stop** requiring manual solve.
- Final submission is always **explicitly confirmed** in the flow.

