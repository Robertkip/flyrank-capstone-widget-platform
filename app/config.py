"""Settings from the environment (.env). Secrets never appear in code or logs."""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    database_url = os.getenv("DATABASE_URL", "sqlite:///./data/widgets.db")
    public_base_url = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    # Abuse protection
    ip_limit = int(os.getenv("RATE_LIMIT_PER_IP", "5"))              # submissions per IP ...
    ip_window_s = int(os.getenv("RATE_LIMIT_IP_WINDOW_SECONDS", "10"))  # ... per this many seconds
    widget_limit = int(os.getenv("RATE_LIMIT_PER_WIDGET", "60"))     # submissions per widget per minute
    max_body_bytes = int(os.getenv("MAX_BODY_BYTES", "10240"))
    min_fill_ms = int(os.getenv("MIN_FILL_MS", "1500"))               # faster than this = bot (time-trap)
    trust_forwarded_for = os.getenv("TRUST_X_FORWARDED_FOR", "0") == "1"
    # Geo enrichment: comma-separated chain. mock_a,mock_b = deterministic; ip-api,ipapi-co = real free APIs
    geo_chain = [p.strip() for p in os.getenv("GEO_CHAIN", "mock_a,mock_b").split(",") if p.strip()]
    geo_timeout_s = float(os.getenv("GEO_TIMEOUT_SECONDS", "2"))
    # Side effects
    email_mode = os.getenv("EMAIL_MODE", "log")        # log | smtp | fail (fail = forced failure for probe 5)
    smtp_host = os.getenv("SMTP_HOST", "mailpit")
    smtp_port = int(os.getenv("SMTP_PORT", "1025"))
    email_from = os.getenv("EMAIL_FROM", "widgets@example.test")
    alert_log = os.getenv("ALERT_LOG", "./data/alerts.log")
    dev_mode = os.getenv("DEV_MODE", "1") == "1"         # enables /dev/* toggles for the probes
    dev_token = os.getenv("DEV_TOKEN", "")


settings = Settings()
