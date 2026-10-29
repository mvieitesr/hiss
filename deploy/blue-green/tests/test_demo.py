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


def test_status_uses_proxy_configuration():
    run(str(DEMO / "switch.sh"), "switch", "green")
    run(
        *COMPOSE,
        "exec",
        "-T",
        "proxy",
        "sh",
        "-c",
        "ACTIVE_SLOT=blue envsubst '${ACTIVE_SLOT}' < /etc/nginx/templates/nginx.conf.template "
        "> /etc/nginx/conf.d/default.conf && nginx -s reload",
    )
    assert "Active slot: blue" in run(str(DEMO / "switch.sh"), "status").stdout
    run(str(DEMO / "switch.sh"), "switch", "green")
    assert "Active slot: green" in run(str(DEMO / "switch.sh"), "status").stdout


def test_active_slot_survives_proxy_recreation():
    run(str(DEMO / "switch.sh"), "switch", "green")
    run(*COMPOSE, "up", "-d", "--no-deps", "--force-recreate", "proxy")
    config = run(*COMPOSE, "exec", "-T", "proxy", "cat", "/etc/nginx/conf.d/default.conf").stdout
    assert "proxy_pass http://green:8000;" in config
    assert "Active slot: green" in run(str(DEMO / "switch.sh"), "status").stdout
