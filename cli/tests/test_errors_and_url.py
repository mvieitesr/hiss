"""Error mapping, URL precedence, connection errors, table vs json."""

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


def test_error_400_mapping(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            400, json={"error": "bad_request", "message": "invalid priority 'bad'"}, request=request
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["issues", "update", "42", "--priority", "bad"])
    assert result.exit_code == 1
    assert "invalid priority" in result.output
    # should contain Error: prefix via handle_response
    assert "Error:" in result.output


def test_error_404_mapping(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            404, json={"error": "not_found", "message": "project 'OPS' not found"}, request=request
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["issues", "create", "--project", "OPS", "--title", "T"])
    assert result.exit_code == 1
    assert "project 'OPS' not found" in result.output


def test_error_409_mapping(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            409,
            json={"error": "conflict", "message": "project key 'OPS' already exists"},
            request=request,
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["projects", "create", "--key", "OPS", "--name", "Operations"])
    assert result.exit_code == 1
    assert "already exists" in result.output


@pytest.mark.parametrize("json_option", [[], ["--json"]])
def test_successful_html_response_is_protocol_error(monkeypatch, json_option):
    def handler(request: httpx.Request):
        return httpx.Response(
            200, text="<html>SPA</html>", headers={"Content-Type": "text/html"}, request=request
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(
        app, ["--url", "http://localhost:8000/wrong-prefix", "projects", "list", *json_option]
    )
    assert result.exit_code == 1
    assert "non-JSON" in result.stderr
    assert "base URL" in result.stderr
    assert "No Projects found" not in result.stdout


@pytest.mark.parametrize("status", [200, 204])
def test_empty_success_response_is_allowed(monkeypatch, status):
    def handler(request: httpx.Request):
        return httpx.Response(status, content=b"", request=request)

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["projects", "list"])
    assert result.exit_code == 0
    assert "No Projects found" in result.stdout
    assert result.stderr == ""


def test_connection_error(monkeypatch):
    def handler(request: httpx.Request):
        raise httpx.ConnectError("connection refused", request=request)

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["projects", "list"])
    assert result.exit_code == 1
    assert "could not connect" in result.output.lower()
    # base_url should appear in message
    assert "http://localhost:8000" in result.output


def test_url_precedence_default(monkeypatch):
    captured = {}

    def handler(request: httpx.Request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[], request=request)

    monkeypatch.delenv("HISS_URL", raising=False)

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["projects", "list"])
    assert result.exit_code == 0
    assert captured["url"] == "http://localhost:8000/api/v1/projects"


def test_url_precedence_env(monkeypatch):
    captured = {}

    def handler(request: httpx.Request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[], request=request)

    monkeypatch.setenv("HISS_URL", "http://env:9000")

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["projects", "list"])
    assert result.exit_code == 0
    assert captured["url"] == "http://env:9000/api/v1/projects"


def test_url_precedence_flag_over_env(monkeypatch):
    captured = {}

    def handler(request: httpx.Request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[], request=request)

    monkeypatch.setenv("HISS_URL", "http://env:9000")

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["--url", "http://flag:8000", "projects", "list"])
    assert result.exit_code == 0
    assert captured["url"] == "http://flag:8000/api/v1/projects"


def test_url_trailing_slash(monkeypatch):
    captured = {}

    def handler(request: httpx.Request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[], request=request)

    monkeypatch.setenv("HISS_URL", "http://env:9000/")

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["projects", "list"])
    assert result.exit_code == 0
    # should not double slash
    assert captured["url"] == "http://env:9000/api/v1/projects"
    assert "//api" not in captured["url"]


def test_flag_trailing_slash(monkeypatch):
    captured = {}

    def handler(request: httpx.Request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[], request=request)

    monkeypatch.delenv("HISS_URL", raising=False)

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["--url", "http://flag:8000/", "projects", "list"])
    assert result.exit_code == 0
    assert captured["url"] == "http://flag:8000/api/v1/projects"


def test_table_vs_json_projects(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            200, json=[{"id": 1, "key": "OPS", "name": "Operations"}], request=request
        )

    _mock(monkeypatch, handler)
    # table
    result = runner.invoke(app, ["projects", "list"])
    assert result.exit_code == 0
    # table contains box drawing or header, not raw JSON
    assert "OPS" in result.output
    assert "Operations" in result.output
    # should not be valid JSON array alone (contains table borders)
    try:
        json.loads(result.stdout)
        # if stdout is JSON, then table failed — but our table goes to stdout, not JSON
        # For table, stdout should not be pure JSON
        assert False, "table output should not be pure JSON"
    except json.JSONDecodeError:
        pass

    # json
    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["projects", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data[0]["key"] == "OPS"


def test_table_vs_json_issues(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json=[{"id": 1, "title": "T", "status": "open", "priority": "medium", "labels": []}],
            request=request,
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["issues", "list", "--project", "OPS"])
    assert result.exit_code == 0
    assert "T" in result.output

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["issues", "list", "--project", "OPS", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data[0]["title"] == "T"


def test_json_output_is_valid_json_labels(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(200, json=[{"id": 1, "name": "bug"}], request=request)

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["labels", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data[0]["name"] == "bug"
