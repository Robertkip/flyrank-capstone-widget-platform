"""Data layer: tenants, widgets, submissions, notifications."""
from datetime import datetime, timezone
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import settings


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(120))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)   # sha256 of the API token; raw token never stored
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Widget(Base):
    __tablename__ = "widgets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(40), unique=True)    # what the embed snippet exposes
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(20))                      # signup | contact | cta
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500), default="")
    fields: Mapped[list] = mapped_column(JSON)                          # [{name,label,type,required,max_length}]
    button_text: Mapped[str] = mapped_column(String(40), default="Submit")
    display: Mapped[dict] = mapped_column(JSON, default=dict)            # {position, theme_color}
    allowed_origins: Mapped[list] = mapped_column(JSON, default=list)    # [] = any origin
    notify_email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    config_version: Mapped[int] = mapped_column(Integer, default=1)      # bumps on update -> new ETag
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __table_args__ = (Index("ix_widgets_tenant", "tenant_id"),)


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    widget_id: Mapped[int] = mapped_column(ForeignKey("widgets.id", ondelete="CASCADE"))
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))   # denormalised for isolation + fast stats
    data: Mapped[dict] = mapped_column(JSON)
    origin: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ip_hash: Mapped[str] = mapped_column(String(64))                     # privacy: store a hash, not the raw IP
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    geo_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (Index("ix_sub_tenant_created", "tenant_id", "created_at"),
                      Index("ix_sub_widget_created", "widget_id", "created_at"))


class SpamEvent(Base):
    """Blocked bot attempts are counted (for the dashboard) but their payload is not stored."""
    __tablename__ = "spam_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    widget_id: Mapped[int] = mapped_column(ForeignKey("widgets.id", ondelete="CASCADE"))
    reason: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (Index("ix_spam_widget", "widget_id"),)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(20), default="email")
    status: Mapped[str] = mapped_column(String(20), default="queued")   # queued | sent | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (Index("ix_notif_status", "status"),)


engine = create_engine(settings.database_url, future=True,
                       connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
