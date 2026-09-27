"""Seed: two tenants (for the isolation demo), a signup widget with a fixed public id used by demo-site/index.html,
and a few submissions. Idempotent. Prints the demo bearer tokens (sandbox-only, not secrets)."""
from sqlalchemy import select
from app.auth import hash_token
from app.db import SessionLocal, Submission, Tenant, Widget
from app.migrations import migrate
from app.services import ip_hash

TENANTS = [("Mama Mboga Bakery", "owner@bakery.test", "wpt_demo_bakery_owner_token"),
           ("Other Company", "owner@other.test", "wpt_demo_other_company_token")]
FIELDS = [{"name": "name", "label": "Your name", "type": "text", "required": True, "max_length": 80},
          {"name": "email", "label": "Email", "type": "email", "required": True, "max_length": 120},
          {"name": "message", "label": "Anything to add?", "type": "textarea", "required": False, "max_length": 500}]


def main():
    migrate()
    db = SessionLocal()
    ids = []
    for name, email, token in TENANTS:
        t = db.scalar(select(Tenant).where(Tenant.token_hash == hash_token(token)))
        if not t:
            t = Tenant(name=name, email=email, token_hash=hash_token(token))
            db.add(t)
            db.commit()
        ids.append(t.id)
        print(f"tenant #{t.id} {name:20s} Authorization: Bearer {token}")
    w = db.scalar(select(Widget).where(Widget.public_id == "wgt_demoSignup01"))
    if not w:
        w = Widget(public_id="wgt_demoSignup01", tenant_id=ids[0], type="signup", title="Get our weekly specials",
                   description="Fresh deals every Friday. No spam.", fields=FIELDS, button_text="Subscribe",
                   display={"position": "inline", "theme_color": "#b45309"},
                   allowed_origins=["http://localhost:5500", "http://127.0.0.1:5500"], notify_email="owner@bakery.test")
        db.add(w)
        db.add(Widget(public_id="wgt_otherCo00001", tenant_id=ids[1], type="contact", title="Contact Other Co",
                      fields=FIELDS[:2], button_text="Send", display={"position": "inline", "theme_color": "#2563eb"},
                      allowed_origins=[]))
        db.commit()
        for n, e, c in [("Achieng", "achieng@example.com", "Kenya"), ("Brian", "brian@example.com", "Kenya"),
                        ("Chloe", "chloe@example.com", None)]:
            db.add(Submission(widget_id=w.id, tenant_id=ids[0], data={"name": n, "email": e}, origin="http://localhost:5500",
                              ip_hash=ip_hash("seed"), country=c, country_code="KE" if c else None,
                              city="Nairobi" if c else None, geo_provider="mock_a" if c else None))
        db.commit()
    print(f"widget {w.public_id}  snippet: <script src=\"http://localhost:8000/widget.js?id={w.public_id}\" async></script>")
    db.close()


if __name__ == "__main__":
    main()
