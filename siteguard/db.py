"""PostgreSQL connections, migrations and operational audit."""
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parent.parent


def now():
    return datetime.now(UTC)


@contextmanager
def transaction(dsn=None):
    url = dsn or os.getenv("DATABASE_URL")
    if not url:
        raise psycopg.OperationalError("Database configuration is missing")
    with psycopg.connect(url, row_factory=dict_row, connect_timeout=4, prepare_threshold=None, options="-c timezone=UTC -c statement_timeout=15000") as connection:
        yield connection


def lock_org(db, org_id):
    db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (str(org_id),))


def control(db, org_id, actor_id, action, object_id, detail=None):
    db.execute(
        """INSERT INTO control_audit (org_id, actor_id, action, object_id, detail)
        VALUES (%s, %s, %s, %s, %s)""",
        (org_id, actor_id, action, str(object_id), Jsonb(detail or {})),
    )


def migrate(dsn, runtime_role=None):
    with transaction(dsn) as db:
        db.execute("SELECT pg_advisory_xact_lock(319082061)")
        db.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
            version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )""")
        versions = {row["version"] for row in db.execute("SELECT version FROM schema_migrations")}
        for migration in sorted((ROOT / "db/migrations").glob("[0-9]*.sql")):
            if migration.name not in versions:
                db.execute(migration.read_text())
                db.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (migration.name,))
        if runtime_role:
            role = sql.Identifier(runtime_role)
            db.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
            db.execute(sql.SQL(
                "GRANT SELECT ON schema_migrations, organizations, sites, staff, sessions,"
                " attempt_limits, control_audit TO {}"
            ).format(role))
            db.execute(sql.SQL("GRANT INSERT, UPDATE ON sites, staff, attempt_limits TO {}").format(role))
            db.execute(sql.SQL("GRANT INSERT, DELETE ON sessions TO {}").format(role))
            db.execute(sql.SQL("GRANT DELETE ON attempt_limits TO {}").format(role))
            db.execute(sql.SQL("GRANT INSERT ON control_audit TO {}").format(role))
            for grant in sorted((ROOT / "db/migrations").glob("grants-*.sql")):
                db.execute(sql.SQL(grant.read_text()).format(role=role))
