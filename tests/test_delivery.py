"""Cached config, versioned bundle, loader."""
from app.assets import BUNDLE_HASH, BUNDLE_PATH


def test_config_is_small_cached_and_etagged(client):
    r = client.get("/widgets/wgt_demoSignup01/config")
    assert r.status_code == 200 and len(r.content) < 1024
    assert r.headers["cache-control"].startswith("public, max-age=60") and r.headers["access-control-allow-origin"] == "*"
    assert "notify_email" not in r.json() and "allowed_origins" not in r.json()        # no private data in public config
    r304 = client.get("/widgets/wgt_demoSignup01/config", headers={"If-None-Match": r.headers["etag"]})
    assert r304.status_code == 304 and r304.content == b""
    assert client.get("/widgets/wgt_nope000001/config").status_code == 404


def test_bundle_is_versioned_and_immutable(client):
    r = client.get(BUNDLE_PATH)
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert len(BUNDLE_HASH) == 12
    old = client.get("/assets/widget-000000000000.js", follow_redirects=False)
    assert old.status_code == 301 and old.headers["location"] == BUNDLE_PATH


def test_loader_points_to_current_bundle(client):
    r = client.get("/widget.js?id=wgt_demoSignup01")
    assert r.headers["cache-control"] == "public, max-age=300" and BUNDLE_PATH in r.text
    assert client.get("/widget.js?id=<script>").status_code == 422
