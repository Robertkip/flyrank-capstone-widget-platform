"""Probes 1, 2, 3, 6 + CORS."""
from conftest import BAKERY, SITE, fresh_ip, submit


def test_preflight_and_cors(client):
    r = client.options("/submissions", headers={"Origin": SITE, "Access-Control-Request-Method": "POST",
                                                  "Access-Control-Request-Headers": "content-type"})
    assert r.status_code == 204 and r.headers["access-control-allow-origin"] == SITE
    assert "POST" in r.headers["access-control-allow-methods"] and "Content-Type" in r.headers["access-control-allow-headers"]
    ok = submit(client)
    assert ok.headers["access-control-allow-origin"] == SITE


def test_probe1_valid_submission_stored_and_visible(client):
    r = submit(client, {"name": "Probe One", "email": "probe1@example.com", "message": "hi"})
    assert r.status_code == 201 and r.json()["enriched"] is True
    subs = client.get("/api/submissions", headers=BAKERY).json()
    s = next(x for x in subs if x["id"] == r.json()["submission_id"])
    assert s["data"]["email"] == "probe1@example.com" and s["origin"] == SITE and s["geo"]["country"] == "Kenya"


def test_probe2_malformed_and_oversized_are_clean_4xx(client):
    h = {"Origin": SITE, "Content-Type": "application/json", "X-Forwarded-For": fresh_ip()}
    assert client.post("/submissions", content=b"{not json", headers=h).status_code == 400
    big = client.post("/submissions", content=b'{"x":"' + b"A" * 20000 + b'"}', headers={**h, "X-Forwarded-For": fresh_ip()})
    assert big.status_code == 413 and big.json()["error"] == "payload_too_large"
    assert client.post("/submissions", content=b"a=b", headers={**h, "Content-Type": "text/plain", "X-Forwarded-For": fresh_ip()}).status_code == 415
    assert client.post("/submissions", json=[1, 2], headers={**h, "X-Forwarded-For": fresh_ip()}).status_code == 400
    r = submit(client, {"name": "", "email": "not-an-email", "evil": "x"})
    assert r.status_code == 422
    errs = {e["field"]: e["error"] for e in r.json()["errors"]}
    assert errs == {"evil": "unknown field", "name": "required", "email": "not a valid email address"}
    assert submit(client, {"name": "x" * 81, "email": "a@b.co"}).status_code == 422
    assert submit(client, widget="wgt_nope000001").status_code == 404


def test_disallowed_origin_is_refused(client):
    r = submit(client, origin="https://evil.example")
    assert r.status_code == 403 and "access-control-allow-origin" not in r.headers


def test_probe3_burst_gets_429_and_service_keeps_serving(client):
    ip = "198.51.100.7"
    codes = [submit(client, ip=ip, fields={"name": f"Bot {i}", "email": f"b{i}@example.com"}).status_code for i in range(12)]
    assert codes[:5] == [201] * 5 and set(codes[5:]) == {429}
    r = submit(client, ip=ip)
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1 and r.json()["scope"] == "ip"
    assert submit(client, ip="198.51.100.99").status_code == 201          # a legitimate visitor right after: served
    assert client.get("/health").status_code == 200


def test_probe6_honeypot_and_time_trap_block_bots(client):
    before = len(client.get("/api/submissions?limit=500", headers=BAKERY).json())
    r1 = submit(client, _hp="http://spam.example")
    r2 = submit(client, {"name": "Speedy", "email": "s@example.com"}, _t=120)
    assert r1.status_code == 202 and r2.status_code == 202 and r1.json() == {"ok": True}
    assert len(client.get("/api/submissions?limit=500", headers=BAKERY).json()) == before
    pw = client.get("/api/stats", headers=BAKERY).json()["per_widget"]
    assert next(w for w in pw if w["widget_id"] == "wgt_demoSignup01")["spam_blocked"] >= 2
