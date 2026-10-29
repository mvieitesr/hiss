from flask import request, jsonify
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from . import api_bp
from .errors import bad_request, not_found, conflict
from ..extensions import db
from ..models import Label, Issue


def _label_to_dict(lb: Label) -> dict:
    return {"id": lb.id, "name": lb.name}


@api_bp.route("/labels", methods=["GET"])
def list_labels():
    labels = Label.query.order_by(Label.id).all()
    return jsonify([_label_to_dict(lb) for lb in labels]), 200


@api_bp.route("/labels", methods=["POST"])
def create_label():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return bad_request("invalid JSON body")
    name = data.get("name")
    if not name or not isinstance(name, str) or not name.strip():
        return bad_request("name is required")
    name = name.strip()

    if Label.query.filter_by(name=name).first() is not None:
        return conflict(f"label '{name}' already exists")

    label = Label(name=name)
    db.session.add(label)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return conflict(f"label '{name}' already exists")
    return jsonify(_label_to_dict(label)), 201


@api_bp.route("/labels/<string:name>", methods=["DELETE"])
def delete_label(name: str):
    label = Label.query.filter_by(name=name).first()
    if label is None:
        return not_found(f"label '{name}' not found")
    db.session.delete(label)
    db.session.commit()
    return "", 204


@api_bp.route("/issues/<int:issue_id>/labels/<string:name>", methods=["POST"])
def attach_label(issue_id: int, name: str):
    issue = Issue.query.options(selectinload(Issue.labels)).filter_by(id=issue_id).first()
    if issue is None:
        return not_found(f"issue {issue_id} not found")
    label = Label.query.filter_by(name=name).first()
    if label is None:
        return not_found(f"label '{name}' not found")

    # Idempotent: if already attached, return 200
    if label in issue.labels:
        return jsonify({"id": issue.id, "labels": [_label_to_dict(lb) for lb in issue.labels]}), 200

    issue.labels.append(label)
    db.session.commit()
    # Reload
    issue = Issue.query.options(selectinload(Issue.labels)).filter_by(id=issue_id).first()
    return jsonify({"id": issue.id, "labels": [_label_to_dict(lb) for lb in issue.labels]}), 200


@api_bp.route("/issues/<int:issue_id>/labels/<string:name>", methods=["DELETE"])
def detach_label(issue_id: int, name: str):
    issue = Issue.query.options(selectinload(Issue.labels)).filter_by(id=issue_id).first()
    if issue is None:
        return not_found(f"issue {issue_id} not found")
    label = Label.query.filter_by(name=name).first()
    if label is None:
        return not_found(f"label '{name}' not found")

    if label not in issue.labels:
        return not_found(f"label '{name}' not attached to issue {issue_id}")

    issue.labels.remove(label)
    db.session.commit()
    issue = Issue.query.options(selectinload(Issue.labels)).filter_by(id=issue_id).first()
    return jsonify({"id": issue.id, "labels": [_label_to_dict(lb) for lb in issue.labels]}), 200
