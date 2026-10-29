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


def h06(api, page, suffix):
    key = f"A{suffix}"
    post(api, "projects", {"key": key, "name": "Race project"})
    issue_a = post(api, f"projects/{key}/issues", {"title": "Race issue A"})
    issue_b = post(api, f"projects/{key}/issues", {"title": "Race issue B"})
    held = []
    page.goto(f"{BASE}/#/projects")
    page.locator(".project-list-row").filter(has_text="Race project").wait_for()
    page.route(f"**/api/v1/issues/{issue_a['id']}", lambda route: held.append(route))
    page.evaluate(f"location.hash = '#/issues/{issue_a['id']}'")
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(10)
    assert held, "Issue A request was not intercepted"
    page.evaluate(f"location.hash = '#/issues/{issue_b['id']}'")
    page.get_by_role("heading", name="Race issue B").wait_for()
    response = api.get(f"issues/{issue_a['id']}")
    response.raise_for_status()
    held[0].fulfill(status=200, content_type="application/json", body=response.text)
    page.wait_for_load_state("networkidle")
    assert page.get_by_role("heading", name="Race issue B").count() == 1, (
        f"late Issue A replaced B at {page.evaluate('location.hash')}: "
        f"{page.locator('.detail-title').all_text_contents()}"
    )

    page.unroute(f"**/api/v1/issues/{issue_a['id']}")
    page.evaluate(f"location.hash = '#/issues/{issue_a['id']}'")
    page.get_by_role("heading", name="Race issue A").wait_for()
    patch = []

    def hold_patch(route):
        if route.request.method == "PATCH":
            patch.append((route, route.fetch()))
        else:
            route.continue_()

    page.route(f"**/api/v1/issues/{issue_a['id']}", hold_patch)
    page.locator(".detail-title-actions button").click()
    page.locator("#editTitleInput").fill("Saved issue A")
    page.locator(".detail-title-edit-form button[type=submit]").click()
    for _ in range(100):
        if patch:
            break
        page.wait_for_timeout(10)
    assert patch, "Issue A PATCH was not intercepted"
    assert api.get(f"issues/{issue_a['id']}").json()["title"] == "Saved issue A"
    page.evaluate(f"location.hash = '#/issues/{issue_b['id']}'")
    page.get_by_role("heading", name="Race issue B").wait_for()
    patch[0][0].fulfill(response=patch[0][1])
    page.wait_for_load_state("networkidle")
    assert page.get_by_role("heading", name="Race issue B").count() == 1, (
        f"late Issue A edit replaced B: {page.locator('.detail-title').all_text_contents()}"
    )

    page.unroute(f"**/api/v1/issues/{issue_a['id']}")
    comments = []
    page.route(f"**/api/v1/issues/{issue_a['id']}/comments", lambda route: comments.append(route))
    page.evaluate(f"location.hash = '#/issues/{issue_a['id']}'")
    for _ in range(100):
        if comments:
            break
        page.wait_for_timeout(10)
    assert comments, "Issue A comments request was not intercepted"
    page.evaluate(f"location.hash = '#/issues/{issue_b['id']}'")
    page.get_by_role("heading", name="Race issue B").wait_for()
    comments[0].fulfill(status=503, content_type="application/json", body='{"message":"old failure"}')
    page.wait_for_load_state("networkidle")
    assert page.get_by_role("heading", name="Race issue B").count() == 1
    assert page.get_by_text("old failure").count() == 0


def main():
    checks = {"H02": h02, "H06": h06}
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
