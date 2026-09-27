"""Probe 4 (geo fallback chain) and Probe 5 (failing side effect)."""
from app import geo, notify
from app.db import SessionLocal, Submission
from conftest import BAKERY, submit, wait_notification


def stored(sid):
    db = SessionLocal()
    s = db.get(Submission, sid)
    db.close()
    return s


def test_probe4_provider_a_down_b_answers(client):
    assert stored(submit(client).json()["submission_id"]).geo_provider == "mock_a"
    client.post("/dev/geo-providers", json=["mock_a"])
    s = stored(submit(client).json()["submission_id"])
    assert s.geo_provider == "mock_b" and s.city == "Kisii"


def test_probe4_all_providers_down_still_stored(client):
    client.post("/dev/geo-providers", json=["mock_a", "mock_b"])
    r = submit(client)
    assert r.status_code == 201 and r.json()["enriched"] is False
    s = stored(r.json()["submission_id"])
    assert s is not None and s.country is None and s.geo_provider is None


def test_probe5_failing_email_does_not_block_submission(client):
    client.post("/dev/side-effects", params={"fail": True})
    r = submit(client, {"name": "Side Effect", "email": "se@example.com"})
    assert r.status_code == 201
    sid = r.json()["submission_id"]
    assert stored(sid).data["email"] == "se@example.com"
    n = wait_notification(sid)
    assert n.status == "failed" and n.attempts == notify.MAX_ATTEMPTS and "forced failure" in n.error


def test_successful_email_is_sent(client):
    n = wait_notification(submit(client).json()["submission_id"])
    assert n.status == "sent" and n.attempts == 1


def test_dashboard_stats(client):
    s = client.get("/api/stats", headers=BAKERY).json()
    assert s["total_submissions"] > 3 and s["per_day"] and s["by_country"][0]["country"] in ("Kenya", "Unknown")
    assert set(s["notifications"]) <= {"sent", "failed", "queued"}
    assert client.get("/api/stats?days=0", headers=BAKERY).status_code == 422
