"""Optional browser checks against an isolated, running Flask/Postgres instance.

Run with httpx and playwright installed outside the repository:
    python app/tests/spa_browser_checks.py [H02 ...]
Set HISS_BROWSER_BASE and CHROMIUM_PATH as needed. The script creates and
removes its own Projects and Labels; never point it at a shared database.
"""

import os
import sys
import uuid
from urllib.parse import quote

import httpx
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

BASE = os.environ.get("HISS_BROWSER_BASE", "http://localhost:18083")
CHROMIUM = os.environ.get("CHROMIUM_PATH")


def post(api, path, body):
    response = api.post(path, json=body)
    response.raise_for_status()
    return response.json()


def h02(api, page, suffix):
    key = f"x{suffix}');window.__auditXss=1;void('"
    post(api, "projects", {"key": key, "name": "XSS demo"})
    dialogs = []
    page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
    page.goto(f"{BASE}/#/projects")
    button = page.locator(".project-list-row").filter(has_text="XSS demo").locator("button")
    button.click()
    marker = page.evaluate("window.__auditXss || 0")
    assert marker == 0, f"stored project key executed JavaScript: {marker}"
    assert len(dialogs) == 1 and key in dialogs[0], f"wrong Project in confirmation: {dialogs}"


def main():
    checks = {"H02": h02}
    requested = sys.argv[1:] or list(checks)
    unknown = set(requested) - checks.keys()
    if unknown:
        raise SystemExit(f"Unknown checks: {sorted(unknown)}")
    suffix = uuid.uuid4().hex[:8]
    failures = []
    with httpx.Client(base_url=f"{BASE}/api/v1/") as api, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=CHROMIUM)
        try:
            for name in requested:
                page = browser.new_page()
                try:
                    checks[name](api, page, suffix)
                    print(f"PASS {name}", flush=True)
                except (AssertionError, httpx.HTTPError, PlaywrightError) as error:
                    failures.append(name)
                    print(f"FAIL {name}: {error}", flush=True)
                finally:
                    page.close()
        finally:
            browser.close()
            projects = api.get("projects").json()
            for project in projects:
                if suffix in project["key"]:
                    response = api.delete("projects/" + quote(project["key"], safe=""))
                    response.raise_for_status()
    print(f"SUMMARY {len(failures)} failing checks: {failures}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
