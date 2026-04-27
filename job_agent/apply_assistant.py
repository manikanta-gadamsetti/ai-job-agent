from __future__ import annotations

import time

from job_agent.db import Database


def run_apply_assistant(*, db: Database, job_id: int) -> None:
    """
    Semi-automatic helper:
    - Opens the job apply URL in a real browser context.
    - Does NOT attempt to bypass CAPTCHAs.
    - Marks the attempt in DB.
    """
    job = db.get_job(job_id)
    if not job:
        raise SystemExit(f"Job id {job_id} not found")

    url = job["url"]
    db.set_application_status(job_id, "in_progress", "Launching browser for manual/assisted apply")

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        db.set_application_status(job_id, "failed", f"Playwright not available: {e}")
        raise

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")

        print("\nApply assistant opened the page.")
        print("Solve login/CAPTCHA manually if prompted.")
        print("Then continue the application manually or keep this window for reference.")
        print("When you're done, close the browser window.")

        # Keep alive until user closes browser
        while True:
            try:
                _ = page.title()
                time.sleep(1.0)
            except Exception:
                break

        try:
            context.close()
            browser.close()
        except Exception:
            pass

    db.set_application_status(job_id, "blocked", "Closed browser; mark status manually (submitted/failed) later")

