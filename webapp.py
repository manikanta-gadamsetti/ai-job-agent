from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from job_agent.config import get_settings
from job_agent.render import render_resume_md_to_pdf
from job_agent.sourcing import load_job_input, extract_basic_fields
from job_agent.tailor import tailor_resume, write_tailor_artifacts


st.set_page_config(page_title="Job AI Agent", page_icon="📄", layout="centered")


def _read_uploaded_text(upload) -> str:
    if upload is None:
        return ""
    data = upload.getvalue()
    try:
        return data.decode("utf-8")
    except Exception:
        return data.decode("utf-8", errors="ignore")


def main():
    settings = get_settings()

    st.title("Job AI Agent")
    st.caption("Paste a job URL/JD → tailor resume → download a one-page PDF.")

    with st.expander("Settings", expanded=False):
        st.write("LLM tailoring is optional. If `OPENAI_API_KEY` is set in `.env`, it will rewrite more strongly.")
        st.code(
            "\n".join(
                [
                    f"BASE_RESUME_PATH={settings.base_resume_path}",
                    f"ARTIFACTS_DIR={settings.artifacts_dir}",
                    f"OPENAI_MODEL={settings.openai_model}",
                ]
            )
        )

    st.subheader("1) Base resume")
    resume_upload = st.file_uploader("Upload your base resume (Markdown .md)", type=["md"])
    use_repo_resume = st.checkbox("Use repo default `data/base_resume.md`", value=True)

    base_resume_text = ""
    if resume_upload is not None:
        base_resume_text = _read_uploaded_text(resume_upload)
        use_repo_resume = False
    elif use_repo_resume:
        p = Path(settings.base_resume_path)
        if p.exists():
            base_resume_text = p.read_text(encoding="utf-8", errors="ignore")
        else:
            st.error(f"Base resume not found at {settings.base_resume_path}. Upload one instead.")
            return

    st.subheader("2) Job input")
    job_url = st.text_input("Job URL (company careers/ATS preferred; LinkedIn works only if you paste JD text below)")
    jd_text = st.text_area("Or paste the full Job Description text", height=220)

    st.subheader("3) Generate tailored PDF")
    job_label = st.text_input("Output filename (optional)", placeholder="Manikanta_Company_Role.pdf")

    if st.button("Generate PDF", type="primary", disabled=not base_resume_text or (not job_url and not jd_text)):
        with st.spinner("Tailoring resume..."):
            if jd_text.strip():
                canonical_url, payload = ("text://job", jd_text)
            else:
                canonical_url, payload = load_job_input(job_url)

            fields = extract_basic_fields(canonical_url, payload)
            job_description_text = fields.get("description_text") or payload

            tailor_json, used_llm = tailor_resume(
                settings=settings,
                base_resume_text=base_resume_text,
                job_description_text=job_description_text,
            )

        with st.spinner("Rendering one-page PDF..."):
            with tempfile.TemporaryDirectory() as td:
                out_dir = Path(td) / "out"
                out_dir.mkdir(parents=True, exist_ok=True)

                # Use a stable job_id-like value for filenames in temp dir
                job_id = 1
                md_path, report_path = write_tailor_artifacts(out_dir=str(out_dir), job_id=job_id, tailor_json=tailor_json)
                pdf_path = str(Path(md_path).with_suffix(".pdf"))
                render_resume_md_to_pdf(md_path=md_path, pdf_path=pdf_path)

                pdf_bytes = Path(pdf_path).read_bytes()

        st.success(f"Done. LLM used: {used_llm}")

        download_name = job_label.strip() if job_label.strip().lower().endswith(".pdf") else (job_label.strip() + ".pdf" if job_label.strip() else "tailored_resume.pdf")
        st.download_button(
            label="Download tailored PDF",
            data=pdf_bytes,
            file_name=download_name,
            mime="application/pdf",
        )

        with st.expander("Show keyword report (JSON)"):
            st.json(tailor_json)


if __name__ == "__main__":
    main()

