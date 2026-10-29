from flask import request, jsonify

from . import api_bp
from .errors import bad_request, not_found
from ..extensions import db
from ..models import Issue, Comment


def _comment_to_dict(c: Comment) -> dict:
    return {
        "id": c.id,
        "issue_id": c.issue_id,
        "body": c.body,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@api_bp.route("/issues/<int:issue_id>/comments", methods=["GET"])
def list_comments(issue_id: int):
    issue = Issue.query.filter_by(id=issue_id).first()
    if issue is None:
        return not_found(f"issue {issue_id} not found")
    comments = Comment.query.filter_by(issue_id=issue_id).order_by(Comment.id).all()
    return jsonify([_comment_to_dict(c) for c in comments]), 200


@api_bp.route("/issues/<int:issue_id>/comments", methods=["POST"])
def create_comment(issue_id: int):
    issue = Issue.query.filter_by(id=issue_id).first()
    if issue is None:
        return not_found(f"issue {issue_id} not found")

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return bad_request("invalid JSON body")

    body = data.get("body")
    if not body or not isinstance(body, str) or not body.strip():
        return bad_request("body is required")

    comment = Comment(issue_id=issue_id, body=body.strip())
    db.session.add(comment)
    db.session.commit()
    return jsonify(_comment_to_dict(comment)), 201


@api_bp.route("/comments/<int:comment_id>", methods=["PATCH"])
def update_comment(comment_id: int):
    comment = Comment.query.filter_by(id=comment_id).first()
    if comment is None:
        return not_found(f"comment {comment_id} not found")

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return bad_request("invalid JSON body")

    body = data.get("body")
    if not body or not isinstance(body, str) or not body.strip():
        return bad_request("body is required")

    comment.body = body.strip()
    db.session.commit()
    return jsonify(_comment_to_dict(comment)), 200


@api_bp.route("/comments/<int:comment_id>", methods=["DELETE"])
def delete_comment(comment_id: int):
    comment = Comment.query.filter_by(id=comment_id).first()
    if comment is None:
        return not_found(f"comment {comment_id} not found")
    db.session.delete(comment)
    db.session.commit()
    return "", 204
