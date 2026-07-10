"""Applies plain .sql files from migrations/sql/ in filename order.

Tracks which migrations have already run in a `schema_migrations` table, so
re-running this script is a no-op except for any new files added since the
last run. Each migration file is applied inside its own transaction.

Usage:
    python -m migrations.run_migrations
"""

import sys
from pathlib import Path

import psycopg

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

SQL_DIR = Path(__file__).parent / "sql"

configure_logging()
logger = get_logger("migrations")


def _to_psycopg_dsn(sqlalchemy_url: str) -> str:
    """Strip the SQLAlchemy '+driver' suffix so psycopg can parse the URL directly."""
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://")


def _ensure_tracking_table(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename    VARCHAR(255) PRIMARY KEY,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.commit()


def _already_applied(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute("SELECT filename FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def run() -> None:
    settings = get_settings()
    dsn = _to_psycopg_dsn(settings.database_url)

    migration_files = sorted(SQL_DIR.glob("*.sql"))
    if not migration_files:
        logger.warning("no_migration_files_found", directory=str(SQL_DIR))
        return

    with psycopg.connect(dsn) as conn:
        _ensure_tracking_table(conn)
        applied = _already_applied(conn)

        pending = [f for f in migration_files if f.name not in applied]
        if not pending:
            logger.info("no_pending_migrations")
            return

        for migration_file in pending:
            sql = migration_file.read_text()
            try:
                with conn.transaction():
                    conn.execute(sql)
                    conn.execute(
                        "INSERT INTO schema_migrations (filename) VALUES (%s)",
                        (migration_file.name,),
                    )
                logger.info("migration_applied", filename=migration_file.name)
            except Exception:
                logger.exception("migration_failed", filename=migration_file.name)
                raise

    logger.info("migrations_complete", applied_count=len(pending))


if __name__ == "__main__":
    try:
        run()
    except Exception:
        sys.exit(1)
