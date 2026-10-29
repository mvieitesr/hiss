def test_root_serves_spa_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.content_type
    assert "Hiss — Issue Tracker" in r.text
    assert "/static/vendor/bootstrap.min.css" in r.text
    assert "/static/vendor/bootstrap.bundle.min.js" in r.text
    assert "/static/app.js" in r.text


def test_spa_route_fallback(client):
    r = client.get("/projects/PRJ")
    assert r.status_code == 200
    assert "text/html" in r.content_type
    assert "Hiss — Issue Tracker" in r.text


def test_vendored_static_assets(client):
    r_css = client.get("/static/vendor/bootstrap.min.css")
    assert r_css.status_code == 200
    assert "text/css" in r_css.content_type

    r_js = client.get("/static/vendor/bootstrap.bundle.min.js")
    assert r_js.status_code == 200
    assert "javascript" in r_js.content_type

    r_app_js = client.get("/static/app.js")
    assert r_app_js.status_code == 200
    assert "javascript" in r_app_js.content_type

    r_app_css = client.get("/static/app.css")
    assert r_app_css.status_code == 200
    assert "text/css" in r_app_css.content_type


def test_project_delete_does_not_embed_key_in_javascript(client):
    script = client.get("/static/app.js").text
    assert 'onclick="app.handleDeleteProject(\'' not in script


def test_unknown_api_returns_404_json(client):
    r = client.get("/api/v1/nonexistent")
    assert r.status_code == 404
    assert r.is_json
    assert r.get_json()["error"] == "not_found"
