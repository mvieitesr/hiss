"""Optional browser checks against an isolated, running Flask/Postgres instance.

Run with httpx and playwright installed outside the repository:
    python app/tests/spa_browser_checks.py [H02 ...]
Set HISS_BROWSER_BASE and CHROMIUM_PATH as needed. The script creates and
removes its own Projects and Labels; never point it at a shared database.
"""

import os
import sys
import uuid
from urllib.parse import parse_qs, quote, urlparse

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
    accept = [False]

    def handle_dialog(dialog):
        dialogs.append(dialog.message)
        if accept[0]:
            dialog.accept()
        else:
            dialog.dismiss()

    page.on("dialog", handle_dialog)
    page.goto(f"{BASE}/#/projects")
    button = page.locator(".project-list-row").filter(has_text="XSS demo").locator("button")
    button.click()
    marker = page.evaluate("window.__auditXss || 0")
    assert marker == 0, f"stored project key executed JavaScript: {marker}"
    assert len(dialogs) == 1 and key in dialogs[0], f"wrong Project in confirmation: {dialogs}"
    accept[0] = True
    button.click()
    button.wait_for(state="detached")
    assert len(dialogs) == 2 and key in dialogs[1]
    assert not any(project["key"] == key for project in api.get("projects").json())
    assert page.evaluate("location.hash") == "#/projects"


def h06(api, page, suffix):
    key = f"C{suffix}"
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


def h06_aba(api, page, suffix):
    key = f"N{suffix}"
    post(api, "projects", {"key": key, "name": "ABA project"})
    issue_a = post(api, f"projects/{key}/issues", {"title": "Old A"})
    issue_b = post(api, f"projects/{key}/issues", {"title": "ABA B"})
    held = []

    def hold_first(route):
        if not held:
            held.append((route, route.fetch()))
        else:
            route.continue_()

    page.goto(f"{BASE}/#/projects")
    page.locator(".project-list-row").filter(has_text="ABA project").wait_for()
    page.route(f"**/api/v1/issues/{issue_a['id']}", hold_first)
    page.evaluate(f"location.hash = '#/issues/{issue_a['id']}'")
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(10)
    assert held, "first A request was not intercepted"
    page.evaluate(f"location.hash = '#/issues/{issue_b['id']}'")
    page.get_by_role("heading", name="ABA B").wait_for()
    api.patch(f"issues/{issue_a['id']}", json={"title": "New A"}).raise_for_status()
    page.evaluate(f"location.hash = '#/issues/{issue_a['id']}'")
    page.get_by_role("heading", name="New A").wait_for()
    held[0][0].fulfill(response=held[0][1])
    page.wait_for_load_state("networkidle")
    assert page.get_by_role("heading", name="New A").count() == 1, (
        "old A response overwrote newer A after navigating A → B → A"
    )


def h06_project(api, page, suffix):
    key_a, key_b = f"G{suffix}", f"H{suffix}"
    post(api, "projects", {"key": key_a, "name": "Project race A"})
    post(api, "projects", {"key": key_b, "name": "Project race B"})
    issue = post(api, f"projects/{key_a}/issues", {"title": "Project race issue"})
    held = []
    page.goto(f"{BASE}/#/projects/{key_a}")
    page.get_by_text("Project race issue", exact=True).wait_for()
    page.route(f"**/api/v1/projects/{key_b}/issues", lambda route: held.append(route))
    page.evaluate(f"location.hash = '#/projects/{key_b}'")
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(10)
    assert held, "Project B issues request was not intercepted"
    page.evaluate(f"location.hash = '#/issues/{issue['id']}'")
    page.get_by_role("heading", name="Project race issue").wait_for()
    response = api.get(f"projects/{key_b}/issues")
    response.raise_for_status()
    held[0].fulfill(status=200, content_type="application/json", body=response.text)
    page.wait_for_load_state("networkidle")
    assert page.get_by_role("heading", name="Project race issue").count() == 1, (
        "late Project B issue list replaced the Issue detail"
    )


def h07_error(api, page, suffix):
    key_a, key_b = f"A{suffix}", f"B{suffix}"
    post(api, "projects", {"key": key_a, "name": "Project A"})
    post(api, "projects", {"key": key_b, "name": "Project B"})
    post(api, f"projects/{key_a}/issues", {"title": "Only in A"})
    page.goto(f"{BASE}/#/projects/{key_a}")
    page.get_by_text("Only in A", exact=True).wait_for()
    page.route(
        f"**/api/v1/projects/{key_b}/issues",
        lambda route: route.fulfill(
            status=503, content_type="application/json", body='{"message":"Issue list unavailable"}'
        ),
    )
    page.evaluate(f"location.hash = '#/projects/{key_b}'")
    page.get_by_text("Issue list unavailable", exact=True).wait_for()
    assert page.get_by_text("Only in A", exact=True).count() == 0, "Issue from Project A shown under B"
    assert page.get_by_role("heading", name="Could not load issues").count() == 1, (
        "failure was rendered as an empty or stale issue list"
    )


def h07_flag(api, page, suffix):
    key, label = f"F{suffix}", f"filter-{suffix}"
    post(api, "projects", {"key": key, "name": "Filter project"})
    post(api, f"projects/{key}/issues", {"title": "Open issue"})
    post(api, f"projects/{key}/issues", {"title": "Done issue", "status": "done"})
    post(api, "labels", {"name": label})
    requests = []

    def flag_off(route):
        params = parse_qs(urlparse(route.request.url).query)
        requests.append(params)
        if "label" in params and not os.environ.get("HISS_REAL_FLAG_OFF"):
            route.fulfill(
                status=400,
                content_type="application/json",
                body='{"error":"feature_disabled","message":"Label filtering disabled"}',
            )
        else:
            route.continue_()

    page.goto(f"{BASE}/#/projects/{key}")
    page.get_by_text("Open issue", exact=True).wait_for()
    page.route(f"**/api/v1/projects/{key}/issues?*", flag_off)
    page.locator(".filter-toggle-btn").click()
    page.locator("#filterStatus").select_option("open")
    page.get_by_text("Done issue", exact=True).wait_for(state="detached")
    page.locator(".filter-toggle-btn").click()
    page.locator("#filterLabel").select_option(label)
    page.locator(".alert-warning").wait_for()
    page.wait_for_load_state("networkidle")
    assert page.locator("#filterLabel").input_value() == "", "disabled Label still selected"
    assert page.locator("#filterStatus").input_value() == "open", "status filter was lost"
    assert page.get_by_text("Open issue", exact=True).count() == 1
    assert page.get_by_text("Done issue", exact=True).count() == 0
    assert not page.locator(".filter-pill").filter(has_text="Label:").count()
    assert any("label" in params for params in requests), requests
    assert requests[-1] == {"status": ["open"]}, f"missing unlabelled retry: {requests}"


def h10(api, page, suffix):
    post(api, "projects", {"key": f"R{suffix}", "name": "Retry project"})
    path = "**/api/v1/projects"
    page.route(
        path,
        lambda route: route.fulfill(
            status=503, content_type="application/json", body='{"message":"Projects unavailable"}'
        ),
    )
    page.goto(f"{BASE}/#/projects")
    page.get_by_role("heading", name="Could not load projects").wait_for()
    page.unroute(path)
    page.get_by_text("Try again", exact=True).click()
    page.get_by_text("Retry project", exact=True).wait_for(timeout=2000)


def h04(api, page, suffix):
    key = f"L{suffix}"
    post(api, "projects", {"key": key, "name": "Limits project"})
    issue = post(api, f"projects/{key}/issues", {"title": "Limits issue"})
    page.goto(f"{BASE}/#/issues/{issue['id']}")
    page.get_by_role("heading", name="Limits issue").wait_for()
    expected = {
        "projectKeyInput": "50",
        "projectNameInput": "200",
        "issueTitleInput": "300",
        "newLabelNameInput": "100",
    }
    for input_id, limit in expected.items():
        actual = page.locator(f"#{input_id}").get_attribute("maxlength")
        assert actual == limit, f"{input_id}: expected {limit}, got {actual}"
    page.locator(".detail-title-actions button").click()
    assert page.locator("#editTitleInput").get_attribute("maxlength") == "300"


def happy(api, page, suffix):
    key, label = f"P{suffix}".upper(), f"label-{suffix}'<>&\""
    page.on("dialog", lambda dialog: dialog.accept())
    page.goto(f"{BASE}/#/projects")
    page.get_by_role("heading", name="Projects", exact=True).wait_for()
    page.get_by_role("button", name="New project").click()
    page.locator("#projectKeyInput").fill(key)
    page.locator("#projectNameInput").fill("Browser project")
    page.locator("#createProjectModal button[type=submit]").click()
    page.get_by_role("heading", name="Browser project").wait_for()
    page.locator("#createProjectModal").wait_for(state="hidden")
    assert any(p["key"] == key for p in api.get("projects").json())

    page.get_by_role("button", name="New issue").click()
    page.locator("#issueTitleInput").fill("Browser issue")
    page.locator("#issueDescriptionInput").fill("First description")
    page.locator("#issuePrioritySelect").select_option("high")
    page.locator("#createIssueModal button[type=submit]").click()
    page.get_by_role("heading", name="Browser issue").wait_for()
    page.locator("#createIssueModal").wait_for(state="hidden")
    issue_id = api.get(f"projects/{key}/issues").json()[0]["id"]

    page.locator(".detail-title-actions button").click()
    page.locator("#editTitleInput").fill("Edited browser issue")
    page.locator(".detail-title-edit-form button[type=submit]").click()
    page.get_by_role("heading", name="Edited browser issue").wait_for()
    page.locator(".timeline-box").filter(has_text="Description").get_by_role("button", name="Edit").click()
    page.locator("#editDescriptionInput").fill("Edited description")
    page.locator(".timeline-edit-form button[type=submit]").click()
    page.get_by_text("Edited description", exact=True).wait_for()
    page.locator("#issueStatusSelect").select_option("done")
    page.locator(".detail-title-meta .status-badge").get_by_text("Done", exact=True).wait_for()
    page.locator("#issuePrioritySelectDetail").select_option("low")
    page.locator(".detail-title-meta .priority-badge").get_by_text("Low", exact=True).wait_for()
    issue = api.get(f"issues/{issue_id}").json()
    assert (issue["title"], issue["description"], issue["status"], issue["priority"]) == (
        "Edited browser issue", "Edited description", "done", "low"
    )

    page.locator("#commentBodyInput").fill("Browser comment")
    page.get_by_role("button", name="Comment", exact=True).click()
    page.get_by_text("Browser comment", exact=True).wait_for()
    comment = api.get(f"issues/{issue_id}/comments").json()[0]
    page.locator(".timeline-box").filter(has_text="Browser comment").get_by_role("button", name="Edit").click()
    page.locator(f"#editCommentInput_{comment['id']}").fill("Edited browser comment")
    page.locator(".timeline-edit-form button[type=submit]").click()
    page.get_by_text("Edited browser comment", exact=True).wait_for()
    assert api.get(f"issues/{issue_id}/comments").json()[0]["body"] == "Edited browser comment"
    page.locator(".timeline-box").filter(has_text="Edited browser comment").get_by_role("button", name="Delete").click()
    page.get_by_text("Edited browser comment", exact=True).wait_for(state="detached")
    assert api.get(f"issues/{issue_id}/comments").json() == []

    page.get_by_role("button", name="Manage", exact=True).click()
    page.locator("#manageLabelsModal").wait_for(state="visible")
    page.locator("#newLabelNameInput").fill(label)
    page.locator("#createLabelForm button[type=submit]").click()
    page.locator("#labelsListContainer").get_by_text(label, exact=True).wait_for()
    page.locator("#manageLabelsModal").get_by_role("button", name="Done").click()
    page.locator("#manageLabelsModal").wait_for(state="hidden")
    page.wait_for_load_state("networkidle")
    page.locator("#attachLabelSelect").select_option(label)
    page.locator(".label-attach-row button").click()
    page.locator(".sidebar-labels").get_by_text(label, exact=True).wait_for()
    assert api.get(f"issues/{issue_id}").json()["labels"][0]["name"] == label
    page.locator(".sidebar-labels button").click()
    page.get_by_text("No labels attached", exact=True).wait_for()
    assert api.get(f"issues/{issue_id}").json()["labels"] == []
    page.locator("#attachLabelSelect").select_option(label)
    page.locator(".label-attach-row button").click()
    page.locator(".sidebar-labels").get_by_text(label, exact=True).wait_for()
    page.get_by_role("button", name="Manage", exact=True).click()
    page.locator("#manageLabelsModal").wait_for(state="visible")
    page.locator("#labelsListContainer .label-pill").filter(has_text=label).locator("button").click()
    page.locator("#labelsListContainer").get_by_text(label, exact=True).wait_for(state="detached")
    assert api.get(f"issues/{issue_id}").json()["labels"] == []
    page.locator("#manageLabelsModal").get_by_role("button", name="Done").click()
    page.locator("#manageLabelsModal").wait_for(state="hidden")

    page.get_by_role("button", name="Delete issue").click()
    page.get_by_role("heading", name="Browser project").wait_for()
    assert api.get(f"issues/{issue_id}").status_code == 404
    page.get_by_role("link", name="Projects", exact=True).first.click()
    page.locator(".project-list-row").filter(has_text="Browser project").locator("button").click()
    page.get_by_text("Browser project", exact=True).wait_for(state="detached")
    assert not any(p["key"] == key for p in api.get("projects").json())


def main():
    checks = {
        "H02": h02, "H06": h06, "H06-aba": h06_aba, "H06-project": h06_project,
        "H07-error": h07_error, "H07-flag": h07_flag, "H10": h10, "H04": h04,
        "happy": happy,
    }
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
                errors = []
                page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
                try:
                    checks[name](api, page, suffix)
                    assert not errors, f"JavaScript errors: {errors}"
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
                if suffix.lower() in project["key"].lower():
                    response = api.delete("projects/" + quote(project["key"], safe=""))
                    response.raise_for_status()
            labels = api.get("labels").json()
            for label in labels:
                if suffix in label["name"]:
                    response = api.delete("labels/" + quote(label["name"], safe=""))
                    response.raise_for_status()
    print(f"SUMMARY {len(failures)} failing checks: {failures}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
