import os

from flask import Flask

from . import config
from .extensions import db

# Global shared engine for test suite stability (Node 6 flakiness fix).
# Reusing one engine across per-test create_app() calls avoids lingering
# per-app engines that interleave TRUNCATE/DELETE with in-flight requests.
_shared_engine = None
_shared_uri = None


def create_app(test_config: dict | None = None) -> Flask:
    """Application factory (Flask 3).

    Config is strictly env-driven (12-factor):
      - DATABASE_URL                (required for DB, fallback to sqlite memory for early boot)
      - APP_VERSION                 (default "dev")
      - FEATURE_LABEL_FILTERING     (default "true", case-insensitive)
    """
    app = Flask(__name__)

    # 12-factor config — read env on every factory call so tests can
    # toggle FEATURE_LABEL_FILTERING by recreating the app.
    app.config["DATABASE_URL"] = os.getenv("DATABASE_URL", "")
    app.config["APP_VERSION"] = os.getenv("APP_VERSION", "dev")
    app.config["FEATURE_LABEL_FILTERING"] = config._parse_feature_flag(
        os.getenv("FEATURE_LABEL_FILTERING", "true")
    )

    # Flask-SQLAlchemy expects SQLALCHEMY_DATABASE_URI.
    # Translate bare "postgresql://" / "postgres://" to "postgresql+psycopg://"
    # so the psycopg (v3) driver is used (psycopg2 not available on Python 3.14).
    def _to_psycopg_uri(uri: str) -> str:
        if uri.startswith("postgres://"):
            return uri.replace("postgres://", "postgresql+psycopg://", 1)
        if uri.startswith("postgresql://"):
            return uri.replace("postgresql://", "postgresql+psycopg://", 1)
        return uri

    raw_uri = app.config["DATABASE_URL"] or "sqlite:///:memory:"
    app.config["SQLALCHEMY_DATABASE_URI"] = _to_psycopg_uri(raw_uri)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False

    # Allow tests / callers to override (e.g. in-memory DB)
    if test_config:
        app.config.update(test_config)
        # keep SQLALCHEMY_DATABASE_URI in sync if DATABASE_URL overridden
        if "DATABASE_URL" in test_config and "SQLALCHEMY_DATABASE_URI" not in test_config:
            raw = test_config["DATABASE_URL"] or "sqlite:///:memory:"
            app.config["SQLALCHEMY_DATABASE_URI"] = _to_psycopg_uri(raw)
        elif "SQLALCHEMY_DATABASE_URI" in test_config:
            app.config["SQLALCHEMY_DATABASE_URI"] = _to_psycopg_uri(
                app.config["SQLALCHEMY_DATABASE_URI"]
            )

    # Reuse shared engine when URI matches (test suite creates many apps with same DB)
    global _shared_engine, _shared_uri
    uri_for_share = app.config["SQLALCHEMY_DATABASE_URI"]
    use_shared = _shared_engine is not None and _shared_uri == uri_for_share

    db.init_app(app)

    if use_shared:
        # Dispose the freshly created engine for this app and replace with the shared one
        try:
            new_engines = db._app_engines.get(app, {})
            for e in list(new_engines.values()):
                try:
                    e.dispose()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            # Replace with shared engine (single entry, no bind key)
            db._app_engines[app] = {None: _shared_engine}
        except Exception:
            pass
    else:
        # First app or different URI — capture as shared for future reuse
        try:
            with app.app_context():
                eng = db.engine
                _shared_engine = eng
                _shared_uri = uri_for_share
        except Exception:
            pass

    # Ensure scoped session is cleaned after each request/app context (avoid idle-in-transaction locks)
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        try:
            db.session.remove()
        except Exception:
            pass

    # Register API blueprint (Node 3)
    from .api import api_bp

    app.register_blueprint(api_bp)

    # Ensure API 404s return JSON (fallback for unknown /api/v1/* routes)
    # The blueprint's errorhandler covers blueprint routes, but we also
    # add an app-level handler for JSON on API prefix.
    from flask import jsonify, request

    @app.errorhandler(404)
    def handle_404(e):
        # Only for API prefix return JSON, otherwise default HTML may still be useful
        if request.path.startswith("/api/"):
            return jsonify({"error": "not_found", "message": "not found"}), 404
        return jsonify({"error": "not_found", "message": "not found"}), 404

    @app.errorhandler(405)
    def handle_405(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "method_not_allowed", "message": "method not allowed"}), 405
        return jsonify({"error": "method_not_allowed", "message": "method not allowed"}), 405

    # Probes and version (Node 4)
    from .api.probes import register_probes

    register_probes(app)

    # Serve Single Page Application at root and non-API paths
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_spa(path: str):
        # Exclude probe routes and API routes from SPA fallback (they are handled elsewhere or 404'd)
        if path.startswith("api/") or path in ("healthz", "readyz", "version"):
            return jsonify({"error": "not_found", "message": "not found"}), 404
        return app.send_static_file("index.html")

    return app
