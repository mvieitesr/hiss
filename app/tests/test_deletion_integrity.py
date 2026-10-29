import pytest
from sqlalchemy import text

from app.app.extensions import db


def test_delete_project_removes_children_and_associations(app, client):
    client.post("/api/v1/projects", json={"key": "GONE", "name": "Gone"})
    client.post("/api/v1/projects", json={"key": "KEEP", "name": "Keep"})
    issue_id = client.post("/api/v1/projects/GONE/issues", json={"title": "Gone"}).get_json()["id"]
    keep_id = client.post("/api/v1/projects/KEEP/issues", json={"title": "Keep"}).get_json()["id"]
    comment_id = client.post(
        f"/api/v1/issues/{issue_id}/comments", json={"body": "Gone"}
    ).get_json()["id"]
    keep_comment_id = client.post(
        f"/api/v1/issues/{keep_id}/comments", json={"body": "Keep"}
    ).get_json()["id"]
    label_id = client.post("/api/v1/labels", json={"name": "shared"}).get_json()["id"]
    client.post(f"/api/v1/issues/{issue_id}/labels/shared")
    client.post(f"/api/v1/issues/{keep_id}/labels/shared")

    assert client.delete("/api/v1/projects/GONE").status_code == 204
    assert client.get(f"/api/v1/issues/{issue_id}").status_code == 404
    assert client.get(f"/api/v1/issues/{keep_id}").status_code == 200
    assert [
        comment["id"] for comment in client.get(f"/api/v1/issues/{keep_id}/comments").get_json()
    ] == [keep_comment_id]
    assert client.get("/api/v1/labels").get_json()[0]["id"] == label_id
    with app.app_context(), db.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM issues WHERE id = :id"), {"id": issue_id}
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM comments WHERE id = :id"), {"id": comment_id}
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM issue_labels WHERE issue_id = :id"), {"id": issue_id}
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM issue_labels WHERE issue_id = :id"), {"id": keep_id}
            ).scalar_one()
            == 1
        )


def test_delete_issue_removes_comments_and_associations(app, client):
    client.post("/api/v1/projects", json={"key": "P", "name": "Project"})
    issue_id = client.post("/api/v1/projects/P/issues", json={"title": "Issue"}).get_json()["id"]
    comment_id = client.post(
        f"/api/v1/issues/{issue_id}/comments", json={"body": "Comment"}
    ).get_json()["id"]
    client.post("/api/v1/labels", json={"name": "keep"})
    client.post(f"/api/v1/issues/{issue_id}/labels/keep")

    assert client.delete(f"/api/v1/issues/{issue_id}").status_code == 204
    assert client.get(f"/api/v1/issues/{issue_id}").status_code == 404
    assert client.get("/api/v1/labels").get_json()[0]["name"] == "keep"
    with app.app_context(), db.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM comments WHERE id = :id"), {"id": comment_id}
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM issue_labels WHERE issue_id = :id"), {"id": issue_id}
            ).scalar_one()
            == 0
        )


def test_delete_label_removes_associations_but_preserves_issues(app, client):
    client.post("/api/v1/projects", json={"key": "P", "name": "Project"})
    issue_id = client.post("/api/v1/projects/P/issues", json={"title": "Issue"}).get_json()["id"]
    label_id = client.post("/api/v1/labels", json={"name": "gone"}).get_json()["id"]
    client.post("/api/v1/labels", json={"name": "keep"})
    client.post(f"/api/v1/issues/{issue_id}/labels/gone")
    client.post(f"/api/v1/issues/{issue_id}/labels/keep")

    assert client.delete("/api/v1/labels/gone").status_code == 204
    issue = client.get(f"/api/v1/issues/{issue_id}")
    assert issue.status_code == 200
    assert [label["name"] for label in issue.get_json()["labels"]] == ["keep"]
    with app.app_context(), db.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM issue_labels WHERE label_id = :id"), {"id": label_id}
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM issue_labels WHERE issue_id = :id"), {"id": issue_id}
            ).scalar_one()
            == 1
        )


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/projects/missing",
        "/api/v1/issues/999999999",
        "/api/v1/comments/999999999",
        "/api/v1/labels/missing",
    ],
)
def test_delete_missing_resource_returns_json_404(client, path):
    response = client.delete(path)
    assert response.status_code == 404
    assert response.is_json
    assert response.get_json()["error"] == "not_found"
    assert isinstance(response.get_json()["message"], str)


def test_comment_edit_errors_and_persistence(client):
    client.post("/api/v1/projects", json={"key": "P", "name": "Project"})
    issue_id = client.post("/api/v1/projects/P/issues", json={"title": "Issue"}).get_json()["id"]
    comment_id = client.post(
        f"/api/v1/issues/{issue_id}/comments", json={"body": "Before"}
    ).get_json()["id"]
    missing = client.patch("/api/v1/comments/999999999", json={"body": "After"})
    assert missing.status_code == 404
    assert missing.is_json
    assert missing.get_json()["error"] == "not_found"
    assert isinstance(missing.get_json()["message"], str)

    path = f"/api/v1/comments/{comment_id}"
    assert client.patch(path, json={"body": "  After  "}).status_code == 200
    assert client.patch(path, json={"body": "   "}).status_code == 400
    assert client.patch(path, data="{", content_type="application/json").status_code == 400
    comments = client.get(f"/api/v1/issues/{issue_id}/comments").get_json()
    assert len(comments) == 1
    assert comments[0]["id"] == comment_id
    assert comments[0]["body"] == "After"


def test_detach_missing_issue_label_or_association_returns_404(client):
    client.post("/api/v1/projects", json={"key": "P", "name": "Project"})
    issue_id = client.post("/api/v1/projects/P/issues", json={"title": "Issue"}).get_json()["id"]
    client.post("/api/v1/labels", json={"name": "exists"})
    for path in [
        "/api/v1/issues/999999999/labels/exists",
        f"/api/v1/issues/{issue_id}/labels/missing",
        f"/api/v1/issues/{issue_id}/labels/exists",
    ]:
        response = client.delete(path)
        assert response.status_code == 404
        assert response.is_json
        assert response.get_json()["error"] == "not_found"
        assert isinstance(response.get_json()["message"], str)
