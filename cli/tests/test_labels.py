"""Labels: list/create — happy paths, error mapping, json."""

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


def test_labels_list_table(monkeypatch):
    def handler(request: httpx.Request):
        assert request.method == "GET"
        assert request.url.path == "/api/v1/labels"
        return httpx.Response(
            200, json=[{"id": 1, "name": "bug"}, {"id": 2, "name": "feature"}], request=request
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["labels", "list"])
    assert result.exit_code == 0
    assert "bug" in result.output
    assert "feature" in result.output


def test_labels_list_json(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(200, json=[{"id": 1, "name": "bug"}], request=request)

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["labels", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data[0]["name"] == "bug"


def test_labels_create_happy(monkeypatch):
    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert request.url.path == "/api/v1/labels"
        body = json.loads(request.content.decode())
        assert body == {"name": "bug"}
        return httpx.Response(201, json={"id": 1, "name": "bug"}, request=request)

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["labels", "create", "bug"])
    assert result.exit_code == 0
    assert "bug" in result.output


def test_labels_create_json(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(201, json={"id": 1, "name": "bug"}, request=request)

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["labels", "create", "bug", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["name"] == "bug"


def test_labels_create_409(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            409,
            json={"error": "conflict", "message": "label 'bug' already exists"},
            request=request,
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["labels", "create", "bug"])
    assert result.exit_code == 1
    assert "label 'bug' already exists" in result.output


def test_labels_create_400(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            400, json={"error": "bad_request", "message": "name is required"}, request=request
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["labels", "create", "   "])
    # Even with whitespace, CLI sends {"name":"   "} and API returns 400
    # Our mock always returns 400, so check mapping
    assert result.exit_code == 1
    assert "name is required" in result.output


def test_labels_delete_happy(monkeypatch):
    def handler(request: httpx.Request):
        assert request.method == "DELETE"
        assert request.url.path == "/api/v1/labels/bug"
        return httpx.Response(204, request=request)

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["labels", "delete", "bug"])
    assert result.exit_code == 0
    assert "Deleted Label bug" in result.output


def test_labels_delete_encodes_name(monkeypatch):
    captured = {}

    def handler(request: httpx.Request):
        captured["url"] = str(request.url)
        return httpx.Response(204, request=request)

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["labels", "delete", "bug#other"])
    assert result.exit_code == 0
    assert captured["url"] == "http://localhost:8000/api/v1/labels/bug%23other"


def test_labels_delete_404(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            404, json={"error": "not_found", "message": "label 'bug' not found"}, request=request
        )

    _mock(monkeypatch, handler)
    result = runner.invoke(app, ["labels", "delete", "bug"])
    assert result.exit_code == 1
    assert "label 'bug' not found" in result.output
