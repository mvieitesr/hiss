from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import event

from app.app.extensions import db


def test_create_and_list_comments(client):
    client.post("/api/v1/projects", json={"key": "CM", "name": "Com"})
    r = client.post("/api/v1/projects/CM/issues", json={"title": "T"})
    iid = r.get_json()["id"]

    r = client.post(f"/api/v1/issues/{iid}/comments", json={"body": "hello"})
    assert r.status_code == 201

    r = client.get(f"/api/v1/issues/{iid}/comments")
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    # missing body → 400
    r = client.post(f"/api/v1/issues/{iid}/comments", json={})
    assert r.status_code == 400
    assert r.is_json


def test_update_and_delete_comment(client):
    client.post("/api/v1/projects", json={"key": "CM2", "name": "Com"})
    r = client.post("/api/v1/projects/CM2/issues", json={"title": "T"})
    iid = r.get_json()["id"]
    r = client.post(f"/api/v1/issues/{iid}/comments", json={"body": "hello"})
    cid = r.get_json()["id"]

    r = client.patch(f"/api/v1/comments/{cid}", json={"body": "updated"})
    assert r.status_code == 200
    assert r.get_json()["body"] == "updated"

    r = client.patch(f"/api/v1/comments/{cid}", json={"body": "   "})
    assert r.status_code == 400

    r = client.delete(f"/api/v1/comments/{cid}")
    assert r.status_code == 204
    r = client.get(f"/api/v1/issues/{iid}/comments")
    assert r.get_json() == []

    r = client.delete("/api/v1/comments/99999")
    assert r.status_code == 404


def test_create_and_attach_detach_label(client):
    client.post("/api/v1/projects", json={"key": "LB", "name": "Lb"})
    r = client.post("/api/v1/projects/LB/issues", json={"title": "T"})
    iid = r.get_json()["id"]

    r = client.post("/api/v1/labels", json={"name": "bug"})
    assert r.status_code == 201

    r = client.post(f"/api/v1/issues/{iid}/labels/bug")
    assert r.status_code == 200
    assert any(label["name"] == "bug" for label in r.get_json()["labels"])

    r = client.delete(f"/api/v1/issues/{iid}/labels/bug")
    assert r.status_code == 200
    assert not any(label["name"] == "bug" for label in r.get_json()["labels"])


def test_concurrent_attach_same_label_is_idempotent(app, client):
    client.post("/api/v1/projects", json={"key": "RACE", "name": "Race"})
    issue_id = client.post("/api/v1/projects/RACE/issues", json={"title": "Race"}).get_json()["id"]
    client.post("/api/v1/labels", json={"name": "existing"})
    client.post("/api/v1/labels", json={"name": "race"})
    assert client.post(f"/api/v1/issues/{issue_id}/labels/existing").status_code == 200

    barrier = Barrier(2)

    def synchronize_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO issue_labels"):
            barrier.wait(timeout=10)

    with app.app_context():
        engine = db.engine
    event.listen(engine, "before_cursor_execute", synchronize_insert)
    try:

        def attach(_):
            with app.test_client() as concurrent_client:
                response = concurrent_client.post(f"/api/v1/issues/{issue_id}/labels/race")
                return response.status_code, response.get_json(silent=True)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attach, range(2)))
    finally:
        event.remove(engine, "before_cursor_execute", synchronize_insert)

    for status, body in results:
        assert status == 200
        assert body["id"] == issue_id
        assert {label["name"] for label in body["labels"]} == {"existing", "race"}
    response = client.post(f"/api/v1/issues/{issue_id}/labels/race")
    assert response.status_code == 200
    assert {label["name"] for label in response.get_json()["labels"]} == {"existing", "race"}
    issue = client.get(f"/api/v1/issues/{issue_id}").get_json()
    assert sorted(label["name"] for label in issue["labels"]) == ["existing", "race"]


def test_duplicate_label_returns_409(client):
    client.post("/api/v1/labels", json={"name": "feature"})
    r = client.post("/api/v1/labels", json={"name": "feature"})
    assert r.status_code == 409
    assert r.is_json


def test_delete_label_detaches_from_issues(client):
    client.post("/api/v1/projects", json={"key": "LB2", "name": "Lb"})
    r = client.post("/api/v1/projects/LB2/issues", json={"title": "T"})
    iid = r.get_json()["id"]
    client.post("/api/v1/labels", json={"name": "bug"})
    client.post(f"/api/v1/issues/{iid}/labels/bug")

    r = client.delete("/api/v1/labels/bug")
    assert r.status_code == 204

    r = client.get("/api/v1/labels")
    assert all(lb["name"] != "bug" for lb in r.get_json())
    r = client.get(f"/api/v1/issues/{iid}")
    assert r.get_json()["labels"] == []

    r = client.delete("/api/v1/labels/missing")
    assert r.status_code == 404
