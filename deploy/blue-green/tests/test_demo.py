"""Manual integration checks for an isolated, running blue-green demo."""

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
