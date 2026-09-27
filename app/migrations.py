"""Versioned migrations, each applied once and recorded in schema_migrations."""
from sqlalchemy import text
from .db import Base, engine

MIGRATIONS = [("001_initial_schema", lambda conn: Base.metadata.create_all(conn))]


def migrate():
    applied = []
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(100) PRIMARY KEY)"))
        done = {r[0] for r in conn.execute(text("SELECT version FROM schema_migrations"))}
        for v, fn in MIGRATIONS:
            if v not in done:
                fn(conn)
                conn.execute(text("INSERT INTO schema_migrations (version) VALUES (:v)"), {"v": v})
                applied.append(v)
    return applied


if __name__ == "__main__":
    print("applied:", migrate() or "up to date")
