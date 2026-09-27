import os
import sys
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update({"DATABASE_URL": f"sqlite:///{_tmp}/t.db", "ALERT_LOG": f"{_tmp}/alerts.log", "GEO_CHAIN": "mock_a,mock_b",
                   "TRUST_X_FORWARDED_FOR": "1", "RATE_LIMIT_PER_IP": "5", "RATE_LIMIT_IP_WINDOW_SECONDS": "10",
                   "EMAIL_MODE": "log", "DEV_MODE": "1", "MIN_FILL_MS": "1500"})
ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import itertools  # noqa
import time  # noqa
import pytest  # noqa
from fastapi.testclient import TestClient  # noqa
from app.main import app  # noqa
from app import geo, notify  # noqa
from app.ratelimit import limiter  # noqa
from scripts import seed  # noqa

BAKERY = {"Authorization": "Bearer wpt_demo_bakery_owner_token"}
OTHER = {"Authorization": "Bearer wpt_demo_other_company_token"}
SITE = "http://localhost:5500"
_ip = itertools.count(10)


def fresh_ip():
    return f"203.0.113.{next(_ip) % 250}"


@pytest.fixture(scope="session")
def client():
    seed.main()
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    limiter.reset()
    geo.MOCK_DOWN.clear()
    notify.FORCE_FAIL["on"] = False
    yield


def submit(client, fields=None, ip=None, origin=SITE, widget="wgt_demoSignup01", **extra):
    body = {"widget_id": widget, "fields": fields or {"name": "Jane", "email": "jane@example.com"}, "_hp": "", "_t": 4000, **extra}
    return client.post("/submissions", json=body, headers={"Origin": origin, "X-Forwarded-For": ip or fresh_ip()})


def wait_notification(sub_id, timeout=5):
    from app.db import Notification, SessionLocal
    end = time.time() + timeout
    while time.time() < end:
        db = SessionLocal()
        n = db.query(Notification).filter_by(submission_id=sub_id).one_or_none()
        db.close()
        if n and n.status in ("sent", "failed"):
            return n
        time.sleep(0.05)
    raise AssertionError("notification not finished")
