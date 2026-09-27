"""Side effect: owner notification email, run in a background worker with retries.
Failure is recorded + alerted but can never affect the already-stored submission."""
import logging
import os
import smtplib
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.message import EmailMessage
from .config import settings
from .db import Notification, SessionLocal, Submission, Widget

log = logging.getLogger("notify")
worker = ThreadPoolExecutor(max_workers=2)
MAX_ATTEMPTS = 3
FORCE_FAIL = {"on": settings.email_mode == "fail"}   # toggled by /dev/side-effects (probe 5)


def alert(msg: str):
    log.error("ALERT %s", msg)
    os.makedirs(os.path.dirname(settings.alert_log) or ".", exist_ok=True)
    with open(settings.alert_log, "a") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} {msg}\n")


def _send(widget: Widget, sub: Submission):
    if FORCE_FAIL["on"]:
        raise RuntimeError("email provider unavailable (forced failure)")
    body = "\n".join(f"{k}: {v}" for k, v in sub.data.items())
    if settings.email_mode in ("log", "fail"):
        log.info("EMAIL to=%s subject='New submission: %s' body=%r", widget.notify_email or "(owner)", widget.title, body)
        return
    msg = EmailMessage()
    msg["From"], msg["To"] = settings.email_from, widget.notify_email or settings.email_from
    msg["Subject"] = f"New submission: {widget.title}"
    msg.set_content(f"{body}\n\nCountry: {sub.country or 'unknown'}")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
        s.send_message(msg)


def run(notification_id: int, backoff_s: float = float(os.getenv("NOTIFY_BACKOFF_SECONDS", "0.5"))):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        db = SessionLocal()
        n = db.get(Notification, notification_id)
        sub = db.get(Submission, n.submission_id)
        try:
            _send(db.get(Widget, sub.widget_id), sub)
            n.status, n.attempts, n.error = "sent", attempt, None
            db.commit()
            return
        except Exception as e:
            n.attempts, n.error = attempt, str(e)[:300]
            if attempt == MAX_ATTEMPTS:
                n.status = "failed"
                db.commit()
                alert(f"notification {n.id} for submission {sub.id} failed after {attempt} attempts: {e}")
                return
            db.commit()
            time.sleep(backoff_s * attempt)
        finally:
            db.close()


def enqueue(db, submission_id: int):
    """Create the notification row and hand it to the worker. Never raises into the request path."""
    try:
        n = Notification(submission_id=submission_id)
        db.add(n)
        db.commit()
        return worker.submit(run, n.id)
    except Exception as e:     # even queueing failure must not break the submission
        db.rollback()
        alert(f"could not queue notification for submission {submission_id}: {e}")
        return None
