"""Manual integration checks for an isolated, running blue-green demo."""

import json
import os
import subprocess
from pathlib import Path


DEMO = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", str(DEMO / "compose.yml")]


def run(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True, env=os.environ)


def health(service):
    container = run(*COMPOSE, "ps", "-q", service).stdout.strip()
    return run("docker", "inspect", "--format", "{{.State.Health.Status}}", container).stdout.strip()


def test_proxy_is_healthy():
    assert health("proxy") == "healthy"


def test_slots_wait_for_a_single_migration_job():
    config = json.loads(run(*COMPOSE, "config", "--format", "json").stdout)
    services = config["services"]
    assert "migrate" in services
    for slot in ("blue", "green"):
        assert services[slot]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
        assert services[slot]["entrypoint"][0] == "gunicorn"
    assert services["migrate"]["entrypoint"][0] == "alembic"
