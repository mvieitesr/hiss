import subprocess

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text

from app.app.extensions import db


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
                ["alembic", "-c", "app/alembic.ini", "check"],
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
