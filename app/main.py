"""HTTP layer. Three paths: owner API (auth), public delivery (cached), public submissions (CORS + protected)."""
import hashlib
import json
import logging
import secrets
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from .assets import BUNDLE, BUNDLE_HASH, BUNDLE_PATH, loader_js, snippet
from .auth import current_tenant, hash_token, new_token
from .config import settings
from .db import SessionLocal, Submission, Tenant, Widget
from .migrations import migrate
from .schemas import TenantIn, WidgetIn, WidgetPatch
from .validation import SubmissionInvalid
from . import geo, notify, services

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = FastAPI(title="Embeddable Widget & Lead-Capture Platform", version="1.0.0")
migrate()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logging.getLogger("api").exception("unhandled error")
    return JSONResponse(status_code=500, content={"error": "internal_error"})


@app.get("/health")
def health():
    return {"ok": True, "bundle": BUNDLE_PATH, "geo_chain": settings.geo_chain}


# =============== Owner API (authenticated, tenant-isolated) ===============
def widget_out(w: Widget) -> dict:
    return {"id": w.public_id, "type": w.type, "title": w.title, "description": w.description, "fields": w.fields,
            "button_text": w.button_text, "display": w.display, "allowed_origins": w.allowed_origins,
            "notify_email": w.notify_email, "active": w.active, "config_version": w.config_version,
            "embed_snippet": snippet(w.public_id), "created_at": w.created_at.isoformat()}


def own_widget(db, tenant: Tenant, public_id: str) -> Widget:
    w = db.scalar(select(Widget).where(Widget.public_id == public_id, Widget.tenant_id == tenant.id))
    if not w:   # 404 (not 403) for other tenants' widgets: don't reveal that they exist
        raise HTTPException(404, "widget not found")
    return w


@app.post("/api/tenants", status_code=201)
def signup(body: TenantIn, db=Depends(get_db)):
    token = new_token()
    t = Tenant(name=body.name, email=body.email.lower(), token_hash=hash_token(token))
    db.add(t)
    db.commit()
    return {"tenant_id": t.id, "name": t.name, "api_token": token, "note": "Store this token now; it is shown only once."}


@app.post("/api/widgets", status_code=201)
def create_widget(body: WidgetIn, t: Tenant = Depends(current_tenant), db=Depends(get_db)):
    w = Widget(public_id="wgt_" + secrets.token_urlsafe(9).replace("-", "a").replace("_", "b"), tenant_id=t.id,
               type=body.type, title=body.title, description=body.description, fields=[f.model_dump() for f in body.fields],
               button_text=body.button_text, display=body.display.model_dump(), allowed_origins=body.allowed_origins,
               notify_email=body.notify_email)
    db.add(w)
    db.commit()
    return widget_out(w)


@app.get("/api/widgets")
def list_widgets(t: Tenant = Depends(current_tenant), db=Depends(get_db)):
    return [widget_out(w) for w in db.scalars(select(Widget).where(Widget.tenant_id == t.id).order_by(Widget.id)).all()]


@app.get("/api/widgets/{public_id}")
def get_widget(public_id: str, t: Tenant = Depends(current_tenant), db=Depends(get_db)):
    return widget_out(own_widget(db, t, public_id))


@app.patch("/api/widgets/{public_id}")
def update_widget(public_id: str, body: WidgetPatch, t: Tenant = Depends(current_tenant), db=Depends(get_db)):
    w = own_widget(db, t, public_id)
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "no fields to update")
    for k, v in changes.items():
        setattr(w, k, v)
    w.config_version += 1          # new ETag -> caches pick up the change after max-age
    db.commit()
    return widget_out(w)


@app.delete("/api/widgets/{public_id}", status_code=204)
def delete_widget(public_id: str, t: Tenant = Depends(current_tenant), db=Depends(get_db)):
    db.delete(own_widget(db, t, public_id))
    db.commit()
    return Response(status_code=204)


@app.get("/api/widgets/{public_id}/embed")
def embed(public_id: str, t: Tenant = Depends(current_tenant), db=Depends(get_db)):
    w = own_widget(db, t, public_id)
    return {"widget_id": w.public_id, "snippet": snippet(w.public_id)}


# ---- Dashboard ----
@app.get("/api/submissions")
def list_submissions(widget_id: str | None = None, limit: int = Query(default=50, ge=1, le=500),
                     t: Tenant = Depends(current_tenant), db=Depends(get_db)):
    q = select(Submission).where(Submission.tenant_id == t.id)
    if widget_id:
        q = q.where(Submission.widget_id == own_widget(db, t, widget_id).id)
    return [services.sub_out(s) for s in db.scalars(q.order_by(Submission.id.desc()).limit(limit)).all()]


@app.get("/api/stats")
def get_stats(days: int = Query(default=30, ge=1, le=365), t: Tenant = Depends(current_tenant), db=Depends(get_db)):
    return services.stats(db, t.id, days)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    """Tiny owner page: paste a token, see submissions + stats (calls the same authenticated API)."""
    return open(__file__.replace("main.py", "static/dashboard.html")).read()


# =============== Public delivery (cached) ===============
PUBLIC_CORS = {"Access-Control-Allow-Origin": "*"}


@app.get("/widget.js")
def widget_loader(id: str = Query(pattern=r"^wgt_[A-Za-z0-9]{6,30}$")):
    return Response(loader_js(id), media_type="application/javascript",
                    headers={**PUBLIC_CORS, "Cache-Control": "public, max-age=300"})


@app.get("/assets/widget-{h}.js")
def widget_bundle(h: str):
    if h != BUNDLE_HASH:          # old version requested: point it at the current one
        return Response(status_code=301, headers={"Location": BUNDLE_PATH, "Cache-Control": "public, max-age=300"})
    return Response(BUNDLE, media_type="application/javascript",
                    headers={**PUBLIC_CORS, "Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/widgets/{public_id}/config")
def widget_config(public_id: str, request: Request, db=Depends(get_db)):
    w = db.scalar(select(Widget).where(Widget.public_id == public_id, Widget.active.is_(True)))
    if not w:
        return JSONResponse(status_code=404, content={"error": "widget_not_found"}, headers=PUBLIC_CORS)
    cfg = {"id": w.public_id, "v": w.config_version, "type": w.type, "title": w.title, "description": w.description,
           "fields": [{k: f[k] for k in ("name", "label", "type", "required", "max_length")} for f in w.fields],
           "button_text": w.button_text, "display": w.display}
    body = json.dumps(cfg, separators=(",", ":"))
    etag = '"' + hashlib.sha256(body.encode()).hexdigest()[:16] + '"'
    headers = {**PUBLIC_CORS, "Cache-Control": "public, max-age=60, stale-while-revalidate=300", "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="application/json", headers=headers)


# =============== Public submissions (CORS + validation + protection) ===============
def cors_headers(origin: str | None, widget: Widget | None = None) -> dict:
    if not origin:
        return {}
    if widget and widget.allowed_origins and origin not in widget.allowed_origins:
        return {}
    return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}


def client_ip(request: Request) -> str:
    if settings.trust_forwarded_for and request.headers.get("x-forwarded-for"):
        return request.headers["x-forwarded-for"].split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


@app.options("/submissions")
def submissions_preflight(origin: str | None = Header(default=None),
                          access_control_request_method: str | None = Header(default=None)):
    if access_control_request_method and access_control_request_method.upper() != "POST":
        return Response(status_code=405, headers={"Allow": "POST, OPTIONS"})
    return Response(status_code=204, headers={
        "Access-Control-Allow-Origin": origin or "*", "Vary": "Origin",
        "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "600"})


def err(status: int, body: dict, origin=None, widget=None, extra=None):
    return JSONResponse(status_code=status, content=body, headers={**cors_headers(origin, widget), **(extra or {})})


@app.post("/submissions")
async def create_submission(request: Request, origin: str | None = Header(default=None), db=Depends(get_db)):
    raw = await request.body()
    if len(raw) > settings.max_body_bytes:
        return err(413, {"error": "payload_too_large", "message": f"body exceeds {settings.max_body_bytes} bytes"}, origin)
    if "application/json" not in request.headers.get("content-type", ""):
        return err(415, {"error": "unsupported_media_type", "message": "send application/json"}, origin)
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return err(400, {"error": "malformed_json", "message": "request body is not valid JSON"}, origin)
    if not isinstance(body, dict) or not isinstance(body.get("widget_id"), str) or not isinstance(body.get("fields"), dict):
        return err(400, {"error": "bad_request", "message": "expected {widget_id: string, fields: object}"}, origin)
    w = db.scalar(select(Widget).where(Widget.public_id == body["widget_id"], Widget.active.is_(True)))
    if not w:
        return err(404, {"error": "widget_not_found"}, origin)
    if origin and w.allowed_origins and origin not in w.allowed_origins:
        return err(403, {"error": "origin_not_allowed", "message": f"{origin} is not allowed to submit to this widget"})
    ip = client_ip(request)
    try:
        services.check_rate(w, ip)
        sub = services.submit(db, w, body, ip, origin)
    except services.RateLimited as e:
        return err(429, {"error": "rate_limited", "scope": e.scope,
                         "message": f"too many submissions from this {e.scope}; retry in {e.retry_after}s"},
                   origin, w, {"Retry-After": str(e.retry_after)})
    except SubmissionInvalid as e:
        return err(422, {"error": "validation_failed", "errors": e.errors}, origin, w)
    except services.Spam as e:
        # Silently "accept" so bots learn nothing; nothing is stored except a spam counter.
        return JSONResponse(status_code=202, content={"ok": True}, headers=cors_headers(origin, w))
    return JSONResponse(status_code=201, content={"ok": True, "submission_id": sub.id, "enriched": bool(sub.country)},
                        headers=cors_headers(origin, w))


# =============== Dev toggles for the probes (DEV_MODE only) ===============
def dev_guard(x_dev_token: str | None = Header(default=None)):
    if not settings.dev_mode:
        raise HTTPException(404, "not found")
    if settings.dev_token and x_dev_token != settings.dev_token:
        raise HTTPException(403, "bad dev token")


@app.post("/dev/geo-providers", dependencies=[Depends(dev_guard)])
def toggle_geo(down: list[str]):
    unknown = [p for p in down if p not in ("mock_a", "mock_b")]
    if unknown:
        raise HTTPException(422, f"unknown mock providers: {unknown}")
    geo.MOCK_DOWN.clear()
    geo.MOCK_DOWN.update(down)
    return {"down": sorted(geo.MOCK_DOWN), "chain": settings.geo_chain}


@app.post("/dev/side-effects", dependencies=[Depends(dev_guard)])
def toggle_side_effects(fail: bool):
    notify.FORCE_FAIL["on"] = fail
    return {"email_forced_failure": fail}
