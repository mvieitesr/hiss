import json
from urllib.parse import quote

import pytest


@pytest.fixture
def api_resources(client):
    client.post("/api/v1/projects", json={"key": "VALID", "name": "Valid"})
    issue = client.post("/api/v1/projects/VALID/issues", json={"title": "Issue"}).get_json()
    comment = client.post(
        f"/api/v1/issues/{issue['id']}/comments", json={"body": "Comment"}
    ).get_json()
    return {"issue_id": issue["id"], "comment_id": comment["id"]}


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/v1/projects"),
        ("POST", "/api/v1/labels"),
        ("POST", "/api/v1/projects/VALID/issues"),
        ("PATCH", "/api/v1/issues/{issue_id}"),
        ("POST", "/api/v1/issues/{issue_id}/comments"),
        ("PATCH", "/api/v1/comments/{comment_id}"),
    ],
)
@pytest.mark.parametrize("body", [7, [], "x", None, True])
def test_json_endpoints_reject_non_object_bodies(client, api_resources, method, path, body):
    response = client.open(
        path.format(**api_resources),
        method=method,
        data=json.dumps(body),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.is_json
    assert response.get_json() == {"error": "bad_request", "message": "invalid JSON body"}


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/v1/projects/VALID/issues"),
        ("PATCH", "/api/v1/issues/{issue_id}"),
    ],
)
@pytest.mark.parametrize("field", ["status", "priority"])
@pytest.mark.parametrize("value", [[], {}, 7, True, None])
def test_issue_rejects_non_string_enums(client, api_resources, method, path, field, value):
    response = client.open(
        path.format(**api_resources), method=method, json={"title": "Issue", field: value}
    )

    assert response.status_code == 400
    assert response.is_json
    assert response.get_json()["error"] == "bad_request"
    assert isinstance(response.get_json()["message"], str)


@pytest.mark.parametrize(
    "method,path,payload,field",
    [
        ("POST", "/api/v1/projects", {"key": "OTHER", "name": "Name"}, "key"),
        ("POST", "/api/v1/projects", {"key": "OTHER", "name": "Name"}, "name"),
        ("POST", "/api/v1/labels", {"name": "Label"}, "name"),
        ("POST", "/api/v1/projects/VALID/issues", {"title": "Issue"}, "title"),
        ("POST", "/api/v1/projects/VALID/issues", {"title": "Issue"}, "description"),
        ("PATCH", "/api/v1/issues/{issue_id}", {}, "title"),
        ("PATCH", "/api/v1/issues/{issue_id}", {}, "description"),
        ("POST", "/api/v1/issues/{issue_id}/comments", {}, "body"),
        ("PATCH", "/api/v1/comments/{comment_id}", {}, "body"),
    ],
)
@pytest.mark.parametrize("value", [[], {}, 7, True, None])
def test_json_fields_validate_types(client, api_resources, method, path, payload, field, value):
    response = client.open(
        path.format(**api_resources), method=method, json={**payload, field: value}
    )

    if field == "description" and value is None:
        assert response.status_code == (201 if method == "POST" else 200)
        assert response.get_json()["description"] == ""
        return
    assert response.status_code == 400
    assert response.is_json
    assert response.get_json()["error"] == "bad_request"
    assert isinstance(response.get_json()["message"], str)


@pytest.mark.parametrize(
    "method,path,payload,field,limit",
    [
        ("POST", "/api/v1/projects", {"name": "Project"}, "key", 50),
        ("POST", "/api/v1/projects", {"key": "OTHER"}, "name", 200),
        ("POST", "/api/v1/labels", {}, "name", 100),
        ("POST", "/api/v1/projects/VALID/issues", {}, "title", 300),
        ("PATCH", "/api/v1/issues/{issue_id}", {}, "title", 300),
    ],
)
def test_text_limits_apply_after_trim(client, api_resources, method, path, payload, field, limit):
    path = path.format(**api_resources)
    accepted = client.open(path, method=method, json={**payload, field: "  " + "x" * limit + "  "})
    assert accepted.status_code == (200 if method == "PATCH" else 201)
    assert accepted.get_json()[field] == "x" * limit

    rejected = client.open(path, method=method, json={**payload, field: "  " + "x" * (limit + 1)})
    assert rejected.status_code == 400
    assert rejected.is_json
    assert rejected.get_json()["error"] == "bad_request"
    assert isinstance(rejected.get_json()["message"], str)
    if method == "PATCH":
        assert client.get(path).get_json()[field] == "x" * limit


@pytest.mark.parametrize("identifier", ["a/b", "/", ".", "..", "  ..  "])
@pytest.mark.parametrize("resource", ["project", "label"])
def test_create_rejects_unroutable_identifiers(client, resource, identifier):
    if resource == "project":
        response = client.post("/api/v1/projects", json={"key": identifier, "name": "Project"})
    else:
        response = client.post("/api/v1/labels", json={"name": identifier})

    assert response.status_code == 400
    assert response.is_json
    assert response.get_json()["error"] == "bad_request"
    assert isinstance(response.get_json()["message"], str)


@pytest.mark.parametrize("identifier", ["what?now", "hash#name", "with space", "café", ".hidden"])
def test_encoded_identifiers_support_create_list_use_and_delete(client, identifier):
    segment = quote(identifier, safe="")
    assert (
        client.post("/api/v1/projects", json={"key": identifier, "name": "Project"}).status_code
        == 201
    )
    assert client.post("/api/v1/labels", json={"name": identifier}).status_code == 201
    assert identifier in [p["key"] for p in client.get("/api/v1/projects").get_json()]
    assert identifier in [label["name"] for label in client.get("/api/v1/labels").get_json()]

    issue = client.post(f"/api/v1/projects/{segment}/issues", json={"title": "Issue"})
    assert issue.status_code == 201
    issue_id = issue.get_json()["id"]
    assert [i["id"] for i in client.get(f"/api/v1/projects/{segment}/issues").get_json()] == [
        issue_id
    ]
    attached = client.post(f"/api/v1/issues/{issue_id}/labels/{segment}")
    assert attached.status_code == 200
    assert [label["name"] for label in attached.get_json()["labels"]] == [identifier]
    detached = client.delete(f"/api/v1/issues/{issue_id}/labels/{segment}")
    assert detached.status_code == 200
    assert detached.get_json()["labels"] == []
    assert client.delete(f"/api/v1/labels/{segment}").status_code == 204
    assert client.delete(f"/api/v1/projects/{segment}").status_code == 204
    assert client.get(f"/api/v1/issues/{issue_id}").status_code == 404


def test_issue_patch_allows_empty_object_and_null_description(client, api_resources):
    path = f"/api/v1/issues/{api_resources['issue_id']}"
    assert client.patch(path, json={}).status_code == 200
    response = client.patch(path, json={"description": None})
    assert response.status_code == 200
    assert response.get_json()["description"] == ""
