"""Logic layer for the public submission path and the dashboard."""
import hashlib
from collections import Counter
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from .config import settings
from .db import Notification, SpamEvent, Submission, Widget
from . import geo, notify
from .ratelimit import limiter
from .validation import validate


class RateLimited(Exception):
    def __init__(self, scope, retry_after):
        super().__init__(scope)
        self.scope, self.retry_after = scope, retry_after


class Spam(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def ip_hash(ip: str) -> str:
    return hashlib.sha256(("widget-platform:" + ip).encode()).hexdigest()


def check_rate(widget: Widget, ip: str):
    ok, ra = limiter.check(f"ip:{ip}", settings.ip_limit, settings.ip_window_s)
    if not ok:
        raise RateLimited("ip", ra)
    ok, ra = limiter.check(f"widget:{widget.id}", settings.widget_limit, 60)
    if not ok:
        raise RateLimited("widget", ra)


def check_spam(body: dict):
    if str(body.get("_hp") or "").strip():
        raise Spam("honeypot")
    t = body.get("_t")
    if isinstance(t, (int, float)) and t < settings.min_fill_ms:
        raise Spam("too_fast")
    text = " ".join(str(v) for v in (body.get("fields") or {}).values() if isinstance(v, str))
    if text.lower().count("http") >= 3:
        raise Spam("too_many_links")


def submit(db, widget: Widget, body: dict, ip: str, origin: str | None) -> Submission:
    """validate -> spam check -> enrich (fallback chain) -> store -> side effect (async, may fail harmlessly)."""
    try:
        check_spam(body)          # before validation: bots always get the same bland 202, learn nothing
    except Spam as s:
        db.add(SpamEvent(widget_id=widget.id, reason=s.reason))
        db.commit()
        raise
    clean = validate(widget, body.get("fields"))
    g = geo.lookup(ip) or {}
    sub = Submission(widget_id=widget.id, tenant_id=widget.tenant_id, data=clean, origin=origin, ip_hash=ip_hash(ip),
                     country=g.get("country"), country_code=g.get("country_code"), city=g.get("city"),
                     geo_provider=g.get("provider"))
    db.add(sub)
    db.commit()                       # the submission is durable BEFORE any side effect runs
    notify.enqueue(db, sub.id)
    return sub


def sub_out(s: Submission) -> dict:
    return {"id": s.id, "widget_id": s.widget_id, "data": s.data, "origin": s.origin,
            "geo": {"country": s.country, "country_code": s.country_code, "city": s.city, "provider": s.geo_provider},
            "created_at": s.created_at.isoformat()}


def stats(db, tenant_id: int, days: int = 30) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    subs = db.scalars(select(Submission).where(Submission.tenant_id == tenant_id)).all()
    subs = [s for s in subs if (s.created_at if s.created_at.tzinfo else s.created_at.replace(tzinfo=timezone.utc)) >= since]
    widgets = db.scalars(select(Widget).where(Widget.tenant_id == tenant_id)).all()
    wid = {w.id: w for w in widgets}
    spam = dict(db.execute(select(SpamEvent.widget_id, func.count()).where(SpamEvent.widget_id.in_(list(wid) or [0]))
                           .group_by(SpamEvent.widget_id)).all())
    per_day = Counter(s.created_at.date().isoformat() for s in subs)
    notif = dict(db.execute(select(Notification.status, func.count()).join(Submission)
                            .where(Submission.tenant_id == tenant_id).group_by(Notification.status)).all())
    return {
        "period_days": days, "total_submissions": len(subs),
        "per_day": [{"date": d, "count": per_day[d]} for d in sorted(per_day)],
        "per_widget": [{"widget_id": w.public_id, "title": w.title, "submissions": sum(s.widget_id == w.id for s in subs),
                        "spam_blocked": spam.get(w.id, 0)} for w in widgets],
        "by_country": [{"country": c or "Unknown", "count": n} for c, n in Counter(s.country for s in subs).most_common()],
        "enriched_pct": round(100 * sum(1 for s in subs if s.country) / len(subs), 1) if subs else 0,
        "notifications": notif,
    }
