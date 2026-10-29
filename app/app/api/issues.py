from flask import request, jsonify, current_app
from sqlalchemy.orm import selectinload

from . import api_bp
from .errors import bad_request, not_found, feature_disabled
from ..extensions import db
from ..models import Project, Issue, Label, IssueStatus, IssuePriority


VALID_STATUSES = {e.value for e in IssueStatus}
VALID_PRIORITIES = {e.value for e in IssuePriority}


def _issue_to_dict(iss: Issue) -> dict:
    # Status/priority may be enum objects or strings
    status = iss.status.value if hasattr(iss.status, "value") else str(iss.status)
    priority = iss.priority.value if hasattr(iss.priority, "value") else str(iss.priority)
    return {
        "id": iss.id,
        "project_id": iss.project_id,
        "title": iss.title,
        "description": iss.description,
        "status": status,
        "priority": priority,
        "created_at": iss.created_at.isoformat() if iss.created_at else None,
        "labels": [{"id": lb.id, "name": lb.name} for lb in (iss.labels or [])],
    }


@api_bp.route("/projects/<string:key>/issues", methods=["GET"])
def list_issues_for_project(key: str):
    project = Project.query.filter_by(key=key).first()
    if project is None:
        return not_found(f"project '{key}' not found")

    status_filter = request.args.get("status")
    priority_filter = request.args.get("priority")
    label_filter = request.args.get("label")

    # Validate enum filters
    if status_filter and status_filter not in VALID_STATUSES:
        return bad_request(f"invalid status '{status_filter}'")
    if priority_filter and priority_filter not in VALID_PRIORITIES:
        return bad_request(f"invalid priority '{priority_filter}'")

    # Feature flag gating for ?label= (Node 4 full, Node 3 stub)
    # If flag is disabled, return 400 with clear message; when enabled, filter.
    if label_filter is not None:
        # Use app config flag parsed in create_app
        flag = current_app.config.get("FEATURE_LABEL_FILTERING", True)
        if not flag:
            return feature_disabled("label filtering is disabled (FEATURE_LABEL_FILTERING=false)")

    query = Issue.query.filter_by(project_id=project.id)

    if status_filter:
        query = query.filter(Issue.status == status_filter)
    if priority_filter:
        query = query.filter(Issue.priority == priority_filter)
    if label_filter:
        # Join through association table to labels
        query = query.join(Issue.labels).filter(Label.name == label_filter)

    # Eager load labels for serialization
    query = query.options(selectinload(Issue.labels)).order_by(Issue.id)
    issues = query.all()
    return jsonify([_issue_to_dict(i) for i in issues]), 200


@api_bp.route("/projects/<string:key>/issues", methods=["POST"])
def create_issue_for_project(key: str):
    project = Project.query.filter_by(key=key).first()
    if project is None:
        return not_found(f"project '{key}' not found")

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return bad_request("invalid JSON body")

    title = data.get("title")
    if not title or not isinstance(title, str) or not title.strip():
        return bad_request("title is required")
    title = title.strip()
    if len(title) > 300:
        return bad_request("title must be at most 300 characters")

    description = data.get("description", "")
    if description is None:
        description = ""
    if not isinstance(description, str):
        return bad_request("description must be a string")

    priority = data.get("priority", "medium")
    if not isinstance(priority, str) or priority not in VALID_PRIORITIES:
        return bad_request(f"invalid priority '{priority}'")

    # Status is always default open on creation; ignore if provided? Or respect? Spec says creation with title/description/optional priority, so ignore status.
    # If status provided and invalid, maybe 400, but we simply default.
    status_val = "open"
    if "status" in data:
        s = data.get("status")
        if not isinstance(s, str) or s not in VALID_STATUSES:
            return bad_request(f"invalid status '{s}'")
        status_val = s

    issue = Issue(
        project_id=project.id,
        title=title,
        description=description,
        status=status_val,
        priority=priority,
    )
    db.session.add(issue)
    db.session.commit()
    # Reload with labels
    db.session.refresh(issue)
    return jsonify(_issue_to_dict(issue)), 201


@api_bp.route("/issues/<int:issue_id>", methods=["GET"])
def get_issue(issue_id: int):
    issue = Issue.query.options(selectinload(Issue.labels)).filter_by(id=issue_id).first()
    if issue is None:
        return not_found(f"issue {issue_id} not found")
    return jsonify(_issue_to_dict(issue)), 200


@api_bp.route("/issues/<int:issue_id>", methods=["PATCH"])
def update_issue(issue_id: int):
    issue = Issue.query.filter_by(id=issue_id).first()
    if issue is None:
        return not_found(f"issue {issue_id} not found")

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return bad_request("invalid JSON body")

    # Validate enums before update
    if "status" in data:
        status_val = data["status"]
        if not isinstance(status_val, str) or status_val not in VALID_STATUSES:
            return bad_request(f"invalid status '{status_val}'")
        issue.status = status_val

    if "priority" in data:
        priority_val = data["priority"]
        if not isinstance(priority_val, str) or priority_val not in VALID_PRIORITIES:
            return bad_request(f"invalid priority '{priority_val}'")
        issue.priority = priority_val

    if "title" in data:
        title = data["title"]
        if not title or not isinstance(title, str) or not title.strip():
            return bad_request("title must be a non-empty string")
        title = title.strip()
        if len(title) > 300:
            return bad_request("title must be at most 300 characters")
        issue.title = title

    if "description" in data:
        desc = data["description"]
        if desc is None:
            desc = ""
        if not isinstance(desc, str):
            return bad_request("description must be a string")
        issue.description = desc

    db.session.commit()
    db.session.refresh(issue)
    # Ensure labels loaded for serialization
    issue = Issue.query.options(selectinload(Issue.labels)).filter_by(id=issue_id).first()
    return jsonify(_issue_to_dict(issue)), 200


@api_bp.route("/issues/<int:issue_id>", methods=["DELETE"])
def delete_issue(issue_id: int):
    issue = Issue.query.filter_by(id=issue_id).first()
    if issue is None:
        return not_found(f"issue {issue_id} not found")
    db.session.delete(issue)
    db.session.commit()
    return "", 204
