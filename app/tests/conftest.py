import os
import subprocess
import pytest
from sqlalchemy import text

from app.app import create_app
from app.app.extensions import db


@pytest.fixture(scope="session", autouse=True)
def _alembic_upgrade():
    """Run alembic upgrade head once per session (no create_all)."""
    env = os.environ.copy()
    if not env.get("DATABASE_URL"):
        env["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/hiss_test"
    # Add safety valves for lock timeout
    url = env["DATABASE_URL"]
    if "lock_timeout" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}options=-c%20lock_timeout%3D5000%20-c%20statement_timeout%3D30000"
        env["DATABASE_URL"] = url
        os.environ["DATABASE_URL"] = url
    subprocess.run(["alembic", "-c", "app/alembic.ini", "upgrade", "head"], env=env, check=True)
    yield


@pytest.fixture(scope="session")
def base_app():
    """Single shared app/engine for all tests — avoids per-test engine creation that leaks connections."""
    app = create_app()
    yield app
    # Final cleanup: ensure no idle transactions remain
    try:
        with app.app_context():
            db.session.remove()
    except Exception:
        pass
    try:
        with app.app_context():
            db.engine.dispose()
    except Exception:
        pass


@pytest.fixture
def app(base_app):
    """Function-scoped app that reuses the session-scoped engine and cleans DB via DELETE."""
    # Clean before test using the shared engine (no TRUNCATE to avoid AccessExclusiveLock)
    with base_app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text("DELETE FROM issue_labels"))
            conn.execute(text("DELETE FROM comments"))
            conn.execute(text("DELETE FROM issues"))
            conn.execute(text("DELETE FROM labels"))
            conn.execute(text("DELETE FROM projects"))
    yield base_app
    # Clean after test
    with base_app.app_context():
        try:
            db.session.remove()
        except Exception:
            pass
        with db.engine.begin() as conn:
            conn.execute(text("DELETE FROM issue_labels"))
            conn.execute(text("DELETE FROM comments"))
            conn.execute(text("DELETE FROM issues"))
            conn.execute(text("DELETE FROM labels"))
            conn.execute(text("DELETE FROM projects"))
        try:
            db.session.remove()
        except Exception:
            pass


@pytest.fixture
def client(app):
    return app.test_client()
