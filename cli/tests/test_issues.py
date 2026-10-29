"""Issues: list/create/update/label/unlabel — filters, error mapping, json."""

import json

import httpx
import pytest
from typer.testing import CliRunner

from hiss.main import app
import hiss.client

runner = CliRunner()


def _mock(monkeypatch, handler):
    transport = httpx.MockTransport(handler)

    def fake(ctx=None, base_url=None):
        if base_url is None:
            base_url = hiss.client.get_base_url_for_ctx(ctx)
        return httpx.Client(transport=transport, base_url=base_url, timeout=10.0)

    monkeypatch.setattr(hiss.client, "get_client", fake)


@pytest.mark.parametrize(
    ("args", "method", "expected_url", "response"),
    [
        (
            ["issues", "list", "--project", "A?B/ñ", "--label", "x?y", "--json"],
            "GET",
            "http://localhost:8000/api/v1/projects/A%3FB%2F%C3%B1/issues?label=x%3Fy",
            [],
        ),
        (
            ["issues", "create", "--project", "A?B/ñ", "--title", "T", "--json"],
            "POST",
            "http://localhost:8000/api/v1/projects/A%3FB%2F%C3%B1/issues",
            {"id": 1},
        ),
        (
            ["issues", "label", "42", "bug#other/%", "--json"],
            "POST",
            "http://localhost:8000/api/v1/issues/42/labels/bug%23other%2F%25",
            {"id": 42, "labels": []},
        ),
        (
            ["issues", "unlabel", "42", "bug#other/%", "--json"],
            "DELETE",
            "http://localhost:8000/api/v1/issues/42/labels/bug%23other%2F%25",
            {"id": 42, "labels": []},
        ),
    ],
)
def test_issues_encodes_dynamic_path_segments(monkeypatch, args, method, expected_url, response):
    captured = {}

    def handler(request: httpx.Request):
        captured["url"] = str(request.url)
        captured["method"] = request.method
        return httpx.Response(200, json=response, request=request)

    _mock(monkeypatch, handler)
    result = runner.invoke(app, args)
    assert result.exit_code == 0
    assert captured == {"url": expected_url, "method": method}


def test_issues_list_basic(monkeypatch):
    def handler(request: httpx.Request):
        assert request.method == "GET"
        assert request.url.path == "/api/v1/projects/OPS/issues"
        assert request.url.query == b""
        return httpx.Response(
            200,
            json=[{"id": 1, "title": "T", "status": "open", "priority": "medium", "labels": []}],
            request=request,
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["issues", "list", "--project", "OPS"])
    assert result.exit_code == 0
    assert "T" in result.output
    assert "open" in result.output


def test_issues_list_with_filters(monkeypatch):
    def handler(request: httpx.Request):
        assert request.url.path == "/api/v1/projects/OPS/issues"
        q = dict(request.url.params)
        assert q.get("status") == "open"
        assert q.get("priority") == "high"
        assert q.get("label") == "bug"
        return httpx.Response(
            200,
            json=[
                {
                    "id": 2,
                    "title": "Filtered",
                    "status": "open",
                    "priority": "high",
                    "labels": [{"id": 1, "name": "bug"}],
                }
            ],
            request=request,
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(
        app,
        [
            "issues",
            "list",
            "--project",
            "OPS",
            "--status",
            "open",
            "--priority",
            "high",
            "--label",
            "bug",
        ],
    )
    assert result.exit_code == 0
    assert "Filtered" in result.output
    assert "bug" in result.output


def test_issues_list_json(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json=[{"id": 1, "title": "T", "status": "open", "priority": "medium", "labels": []}],
            request=request,
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["issues", "list", "--project", "OPS", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data[0]["title"] == "T"


def test_issues_list_label_filter_feature_disabled(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            400,
            json={
                "error": "feature_disabled",
                "message": "label filtering is disabled (FEATURE_LABEL_FILTERING=false)",
            },
            request=request,
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["issues", "list", "--project", "OPS", "--label", "bug"])
    assert result.exit_code == 1
    assert "label filtering is disabled (FEATURE_LABEL_FILTERING=false)" in result.output


def test_issues_create_happy(monkeypatch):
    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert request.url.path == "/api/v1/projects/OPS/issues"
        body = json.loads(request.content.decode())
        assert body["title"] == "T"
        assert body["priority"] == "high"
        return httpx.Response(
            201,
            json={"id": 42, "title": "T", "status": "open", "priority": "high", "labels": []},
            request=request,
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(
        app, ["issues", "create", "--project", "OPS", "--title", "T", "--priority", "high"]
    )
    assert result.exit_code == 0
    assert "T" in result.output


def test_issues_create_with_description(monkeypatch):
    def handler(request: httpx.Request):
        body = json.loads(request.content.decode())
        assert body["description"] == "desc text"
        return httpx.Response(
            201,
            json={"id": 43, "title": "T2", "status": "open", "priority": "medium", "labels": []},
            request=request,
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(
        app, ["issues", "create", "--project", "OPS", "--title", "T2", "--description", "desc text"]
    )
    assert result.exit_code == 0


def test_issues_create_404(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            404, json={"error": "not_found", "message": "project 'OPS' not found"}, request=request
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["issues", "create", "--project", "OPS", "--title", "T"])
    assert result.exit_code == 1
    assert "project 'OPS' not found" in result.output


def test_issues_update_happy(monkeypatch):
    def handler(request: httpx.Request):
        assert request.method == "PATCH"
        assert request.url.path == "/api/v1/issues/42"
        body = json.loads(request.content.decode())
        assert body["status"] == "in_progress"
        assert body["priority"] == "high"
        return httpx.Response(
            200,
            json={
                "id": 42,
                "title": "T",
                "status": "in_progress",
                "priority": "high",
                "labels": [],
            },
            request=request,
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(
        app, ["issues", "update", "42", "--status", "in_progress", "--priority", "high"]
    )
    assert result.exit_code == 0
    assert "in_progress" in result.output


def test_issues_update_400(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            400, json={"error": "bad_request", "message": "invalid status 'bad'"}, request=request
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["issues", "update", "42", "--status", "bad"])
    assert result.exit_code == 1
    assert "invalid status" in result.output


def test_issues_delete_happy(monkeypatch):
    def handler(request: httpx.Request):
        assert request.method == "DELETE"
        assert request.url.path == "/api/v1/issues/42"
        return httpx.Response(204, request=request)

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["issues", "delete", "42"])
    assert result.exit_code == 0
    assert "Deleted Issue 42" in result.output


def test_issues_delete_404(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            404, json={"error": "not_found", "message": "issue 42 not found"}, request=request
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["issues", "delete", "42"])
    assert result.exit_code == 1
    assert "issue 42 not found" in result.output


def test_issues_label_happy(monkeypatch):
    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert request.url.path == "/api/v1/issues/42/labels/bug"
        return httpx.Response(
            200, json={"id": 42, "labels": [{"id": 1, "name": "bug"}]}, request=request
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["issues", "label", "42", "bug"])
    assert result.exit_code == 0
    assert "bug" in result.output


def test_issues_unlabel_happy(monkeypatch):
    def handler(request: httpx.Request):
        assert request.method == "DELETE"
        assert request.url.path == "/api/v1/issues/42/labels/bug"
        return httpx.Response(200, json={"id": 42, "labels": []}, request=request)

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["issues", "unlabel", "42", "bug"])
    assert result.exit_code == 0


def test_issues_label_404(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            404, json={"error": "not_found", "message": "label 'bug' not found"}, request=request
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["issues", "label", "42", "bug"])
    assert result.exit_code == 1
    assert "label 'bug' not found" in result.output


def test_issues_unlabel_404(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            404,
            json={"error": "not_found", "message": "label 'bug' not attached to issue 42"},
            request=request,
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["issues", "unlabel", "42", "bug"])
    assert result.exit_code == 1
    assert "not attached" in result.output
