"""Owner authentication: opaque bearer tokens, stored only as SHA-256 hashes."""
import hashlib
import secrets
from fastapi import Depends, Header, HTTPException
from .db import SessionLocal, Tenant


def new_token() -> str:
    return "wpt_" + secrets.token_urlsafe(32)


def hash_token(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def current_tenant(authorization: str | None = Header(default=None)) -> Tenant:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    db = SessionLocal()
    try:
        t = db.query(Tenant).filter(Tenant.token_hash == hash_token(authorization[7:].strip())).one_or_none()
    finally:
        db.close()
    if not t:
        raise HTTPException(401, "invalid token", headers={"WWW-Authenticate": "Bearer"})
    return t
