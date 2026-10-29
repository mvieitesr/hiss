"""Projects: list/create — happy paths, json vs table, error mapping."""

import json

import httpx
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


def test_projects_list_table(monkeypatch):
    def handler(request: httpx.Request):
        assert request.method == "GET"
        assert request.url.path == "/api/v1/projects"
        return httpx.Response(
            200, json=[{"id": 1, "key": "OPS", "name": "Operations"}], request=request
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["projects", "list"])
    assert result.exit_code == 0
    assert "OPS" in result.output
    assert "Operations" in result.output
    # table should not be JSON
    assert "id" in result.output.lower()


def test_projects_list_json(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            200, json=[{"id": 1, "key": "OPS", "name": "Operations"}], request=request
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["projects", "list", "--json"])
    assert result.exit_code == 0
    # output should be valid JSON
    data = json.loads(result.stdout)
    assert data[0]["key"] == "OPS"
    assert data[0]["name"] == "Operations"


def test_projects_list_empty(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(200, json=[], request=request)

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["projects", "list"])
    assert result.exit_code == 0
    assert "No Projects" in result.output


def test_projects_create_happy(monkeypatch):
    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert request.url.path == "/api/v1/projects"
        body = json.loads(request.content.decode())
        assert body == {"key": "OPS", "name": "Operations"}
        return httpx.Response(
            201, json={"id": 1, "key": "OPS", "name": "Operations"}, request=request
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["projects", "create", "--key", "OPS", "--name", "Operations"])
    assert result.exit_code == 0
    assert "OPS" in result.output


def test_projects_create_json(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            201, json={"id": 1, "key": "OPS", "name": "Operations"}, request=request
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(
        app, ["projects", "create", "--key", "OPS", "--name", "Operations", "--json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["key"] == "OPS"


def test_projects_create_409(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            409,
            json={"error": "conflict", "message": "project key 'OPS' already exists"},
            request=request,
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["projects", "create", "--key", "OPS", "--name", "Operations"])
    assert result.exit_code == 1
    assert "project key 'OPS' already exists" in result.output


def test_projects_create_400(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            400, json={"error": "bad_request", "message": "key is required"}, request=request
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["projects", "create", "--key", "", "--name", "Operations"])
    # CLI sends empty? Actually --key "" is passed as empty string, API returns 400
    # But Typer will pass "" as value, so we test error mapping via mock
    # Instead directly invoke and check 400 mapping
    # We'll simulate 400 for any create
    assert result.exit_code == 1
    assert "key is required" in result.output


def test_projects_delete_happy(monkeypatch):
    def handler(request: httpx.Request):
        assert request.method == "DELETE"
        assert request.url.path == "/api/v1/projects/OPS"
        return httpx.Response(204, request=request)

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["projects", "delete", "OPS"])
    assert result.exit_code == 0
    assert "Deleted Project OPS" in result.output


def test_projects_delete_encodes_key(monkeypatch):
    captured = {}

    def handler(request: httpx.Request):
        captured["url"] = str(request.url)
        return httpx.Response(204, request=request)

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["projects", "delete", "KEEP?other"])
    assert result.exit_code == 0
    assert captured["url"] == "http://localhost:8000/api/v1/projects/KEEP%3Fother"


def test_projects_delete_404(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            404, json={"error": "not_found", "message": "project 'OPS' not found"}, request=request
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["projects", "delete", "OPS"])
    assert result.exit_code == 1
    assert "project 'OPS' not found" in result.output
