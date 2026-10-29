import pytest
from sqlalchemy.exc import OperationalError

from app.app import create_app
from app.app import config as app_config
from app.app.extensions import db


def test_healthz_returns_200(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_readyz_returns_200_when_db_up(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_readyz_returns_503_when_db_down(client, app, monkeypatch):
    def fail_connect():
        raise OperationalError("SELECT 1", {}, Exception("database unavailable"))

    with app.app_context():
        monkeypatch.setattr(db.engine, "connect", fail_connect)
        r = client.get("/readyz")

    assert r.status_code == 503
    assert r.get_json()["status"] == "error"
    assert "database unavailable" in r.get_json()["message"]


@pytest.mark.parametrize("version", [None, "9.9.9-test"])
def test_version_returns_app_version(app, monkeypatch, version):
    if version is None:
        monkeypatch.delenv("APP_VERSION", raising=False)
    else:
        monkeypatch.setenv("APP_VERSION", version)
    configured_app = create_app()
    expected = version if version is not None else "dev"
    assert configured_app.config["APP_VERSION"] == expected
    r = configured_app.test_client().get("/version")
    assert r.status_code == 200
    assert r.get_json()["version"] == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        ("true", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("off", False),
        (" TrUe ", True),
        (" FaLsE ", False),
        ("unknown", True),
        ("", True),
    ],
)
def test_feature_flag_is_read_on_app_creation(app, monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("FEATURE_LABEL_FILTERING", raising=False)
    else:
        monkeypatch.setenv("FEATURE_LABEL_FILTERING", value)
    configured_app = create_app()
    assert configured_app.config["FEATURE_LABEL_FILTERING"] is expected
    client = configured_app.test_client()
    client.post("/api/v1/projects", json={"key": "FLAG", "name": "Flag"})
    r = client.get("/api/v1/projects/FLAG/issues?label=bug")
    assert r.status_code == (200 if expected else 400)


def test_factory_uses_config_flag_parser(app, monkeypatch):
    monkeypatch.setenv("FEATURE_LABEL_FILTERING", "true")
    monkeypatch.setattr(app_config, "_parse_feature_flag", lambda value: False)
    assert create_app().config["FEATURE_LABEL_FILTERING"] is False


def test_label_filter_when_flag_on_returns_filtered(app, monkeypatch):
    monkeypatch.setenv("FEATURE_LABEL_FILTERING", "true")
    client = create_app().test_client()
    client.post("/api/v1/projects", json={"key": "FLT", "name": "Flt"})
    r = client.post("/api/v1/projects/FLT/issues", json={"title": "I1"})
    id1 = r.get_json()["id"]
    r = client.post("/api/v1/projects/FLT/issues", json={"title": "I2"})
    id2 = r.get_json()["id"]

    client.post("/api/v1/labels", json={"name": "bug"})
    client.post(f"/api/v1/issues/{id1}/labels/bug")

    r = client.get("/api/v1/projects/FLT/issues?label=bug")
    assert r.status_code == 200
    ids = [i["id"] for i in r.get_json()]
    assert id1 in ids and id2 not in ids


def test_label_filter_when_flag_off_returns_400(app, monkeypatch):
    monkeypatch.setenv("FEATURE_LABEL_FILTERING", "false")
    client = create_app().test_client()
    client.post("/api/v1/projects", json={"key": "FF", "name": "FF"})
    r = client.get("/api/v1/projects/FF/issues?label=bug")
    assert r.status_code == 400
    assert r.is_json
    msg = r.get_json()["message"].lower()
    assert "disabled" in msg or "flag" in msg

    # Without the label parameter, requests still succeed.
    r = client.get("/api/v1/projects/FF/issues")
    assert r.status_code == 200
