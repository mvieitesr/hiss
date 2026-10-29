"""Smoke commands in the course documentation retain their exit-status contract."""

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_documented_minimal_smoke_command_fails_for_wrong_version():
    docs = (ROOT / "docs/pipeline.md").read_text()
    prefix = "# forma mínima equivalente: "
    command = next(line[len(prefix) :] for line in docs.splitlines() if line.startswith(prefix))
    assert "forma corta: `jq -e --arg expected`" in docs
    result = subprocess.run(
        ["bash", "-c", command],
        input='{"version":"wrong"}',
        text=True,
        capture_output=True,
        env={**os.environ, "DEPLOY_TAG": "expected"},
    )
    assert result.returncode != 0
    result = subprocess.run(
        ["bash", "-c", command],
        input='{"version":"expected"}',
        text=True,
        capture_output=True,
        env={**os.environ, "DEPLOY_TAG": "expected"},
    )
    assert result.returncode == 0
