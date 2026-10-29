import os
import subprocess
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text

from app.app.extensions import db


REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = REPO_ROOT / "app" / "alembic.ini"


@pytest.mark.parametrize("command", ["current", "check"])
@pytest.mark.parametrize("working_dir", [REPO_ROOT, REPO_ROOT / "app"])
@pytest.mark.parametrize("with_pythonpath", [False, True])
def test_alembic_commands_work_from_any_directory(app, command, working_dir, with_pythonpath):
    env = os.environ.copy()
    if with_pythonpath:
        env["PYTHONPATH"] = str(REPO_ROOT)
    else:
        env.pop("PYTHONPATH", None)
    result = subprocess.run(
        ["alembic", "-c", str(ALEMBIC_CONFIG), command],
        cwd=working_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    if command == "current":
        assert "(head)" in result.stdout
    else:
        assert "No new upgrade operations detected" in result.stdout


def test_pytest_from_app_directory():
    result = subprocess.run(
        ["pytest", "tests/test_probes_version_flag.py::test_healthz_returns_200"],
        cwd=REPO_ROOT / "app",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_model_metadata_matches_migrated_server_defaults(app):
    with app.app_context(), db.engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "compare_server_default": True}
        )
        differences = compare_metadata(context, db.metadata)

    assert differences == []


def test_alembic_check_detects_server_default_drift(app):
    with app.app_context():
        try:
            with db.engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE issues ALTER COLUMN description SET DEFAULT 'drift'")
                )
            result = subprocess.run(
                ["alembic", "-c", str(ALEMBIC_CONFIG), "check"],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            with db.engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE issues ALTER COLUMN description SET DEFAULT ''")
                )

    assert result.returncode != 0
    assert "modify_default" in result.stdout + result.stderr
    assert "description" in result.stdout + result.stderr
