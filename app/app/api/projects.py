from flask import request, jsonify
from sqlalchemy import func, case
from sqlalchemy.exc import IntegrityError

from . import api_bp
from .errors import bad_request, conflict, not_found
from ..extensions import db
from ..models import Project, Issue, IssueStatus


def _project_to_dict(p: Project, open_issues: int = 0) -> dict:
    return {"id": p.id, "key": p.key, "name": p.name, "open_issues": open_issues}


@api_bp.route("/projects", methods=["GET"])
def list_projects():
    # Single query with left outer join to count open issues (status != 'done') per project
    rows = (
        db.session.query(
            Project,
            func.coalesce(
                func.sum(
                    case(
                        (Issue.status != IssueStatus.done, 1),
                        else_=0,
                    )
                ),
                0,
            ).label("open_issues"),
        )
        .outerjoin(Issue, Issue.project_id == Project.id)
        .group_by(Project.id)
        .order_by(Project.id)
        .all()
    )
    return jsonify([_project_to_dict(p, int(count)) for p, count in rows]), 200


@api_bp.route("/projects", methods=["POST"])
def create_project():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return bad_request("invalid JSON body")
    key = (data.get("key") or "").strip() if isinstance(data.get("key"), str) else data.get("key")
    name = (
        (data.get("name") or "").strip() if isinstance(data.get("name"), str) else data.get("name")
    )

    # Validate required fields
    if not key or not isinstance(key, str):
        return bad_request("key is required")
    if not name or not isinstance(name, str):
        return bad_request("name is required")

    # Check duplicate before insert for clean 409
    if Project.query.filter_by(key=key).first() is not None:
        return conflict(f"project key '{key}' already exists")

    project = Project(key=key, name=name)
    db.session.add(project)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return conflict(f"project key '{key}' already exists")

    return jsonify(_project_to_dict(project, 0)), 201


@api_bp.route("/projects/<string:key>", methods=["DELETE"])
def delete_project(key: str):
    project = Project.query.filter_by(key=key).first()
    if project is None:
        return not_found(f"project '{key}' not found")
    db.session.delete(project)
    db.session.commit()
    return "", 204
