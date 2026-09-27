"""Widget management: auth, CRUD, validation, tenant isolation, embed snippet."""
from conftest import BAKERY, OTHER

NEW = {"type": "contact", "title": "Contact us", "fields": [{"name": "email", "label": "Email", "type": "email", "required": True}],
       "allowed_origins": ["http://localhost:5500"]}


def test_requests_without_valid_auth_are_rejected(client):
    assert client.get("/api/widgets").status_code == 401
    assert client.get("/api/widgets", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.post("/api/widgets", json=NEW).status_code == 401


def test_crud_and_embed_snippet(client):
    r = client.post("/api/widgets", json=NEW, headers=BAKERY)
    assert r.status_code == 201
    w = r.json()
    assert w["embed_snippet"] == f'<script src="http://localhost:8000/widget.js?id={w["id"]}" async></script>'
    assert client.get(f"/api/widgets/{w['id']}", headers=BAKERY).json()["title"] == "Contact us"
    p = client.patch(f"/api/widgets/{w['id']}", json={"title": "Talk to us"}, headers=BAKERY).json()
    assert p["title"] == "Talk to us" and p["config_version"] == 2
    assert client.get(f"/api/widgets/{w['id']}/embed", headers=BAKERY).json()["snippet"] == w["embed_snippet"]
    assert client.delete(f"/api/widgets/{w['id']}", headers=BAKERY).status_code == 204
    assert client.get(f"/api/widgets/{w['id']}", headers=BAKERY).status_code == 404


def test_widget_validation(client):
    bad = [{**NEW, "type": "spaceship"}, {**NEW, "fields": []}, {**NEW, "allowed_origins": ["not a url"]},
           {**NEW, "fields": [{"name": "_hp", "label": "x"}]}, {**NEW, "fields": [NEW["fields"][0], NEW["fields"][0]]}]
    for b in bad:
        assert client.post("/api/widgets", json=b, headers=BAKERY).status_code == 422
    assert client.patch("/api/widgets/wgt_demoSignup01", json={}, headers=BAKERY).status_code == 422


def test_tenant_isolation(client):
    # Other Company cannot read, edit, delete or list the bakery's widget or its submissions.
    assert client.get("/api/widgets/wgt_demoSignup01", headers=OTHER).status_code == 404
    assert client.patch("/api/widgets/wgt_demoSignup01", json={"title": "pwned"}, headers=OTHER).status_code == 404
    assert client.delete("/api/widgets/wgt_demoSignup01", headers=OTHER).status_code == 404
    assert all(w["id"] != "wgt_demoSignup01" for w in client.get("/api/widgets", headers=OTHER).json())
    assert client.get("/api/submissions?widget_id=wgt_demoSignup01", headers=OTHER).status_code == 404
    assert all(s["widget_id"] != 1 for s in client.get("/api/submissions", headers=OTHER).json())
    assert client.get("/api/widgets/wgt_demoSignup01", headers=BAKERY).json()["title"] != "pwned"
