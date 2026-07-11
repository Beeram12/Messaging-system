import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://notif_user:notif_pass@localhost:5432/notifications_test"
)
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("API_KEY", "dev-local-api-key")

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import Base

get_settings.cache_clear()
settings = get_settings()

# Create the test database if it doesn't exist yet (connects to the default
# 'postgres' maintenance DB to issue CREATE DATABASE).
_admin_url = settings.database_url.rsplit("/", 1)[0] + "/postgres"
_db_name = settings.database_url.rsplit("/", 1)[1]
_admin_engine = create_engine(_admin_url, isolation_level="AUTOCOMMIT")
with _admin_engine.connect() as conn:
    exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": _db_name}).scalar()
    if not exists:
        conn.execute(text(f'CREATE DATABASE "{_db_name}"'))
_admin_engine.dispose()

engine = create_engine(settings.database_url, future=True)
TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture()
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
