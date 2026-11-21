import os
from pathlib import Path

import pytest

# Tests drop and rebuild the schema, so they use their own database (TEST_DATABASE_URL), never DATABASE_URL.
# Must be set before the app (and its settings) is imported by any test module.
TEST_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://chess:chess@localhost:5432/chess_intelligence_test")
if not TEST_URL.rsplit("/", 1)[-1].split("?")[0].endswith("_test"):
    raise RuntimeError(f"refusing to run tests against a database whose name does not end in _test: {TEST_URL}")
os.environ["DATABASE_URL"] = TEST_URL
os.environ["ANALYSIS_WORKERS"] = "0"  # run analysis inline so API tests are deterministic


@pytest.fixture(scope="session", autouse=True)
def database():
    """Fresh schema built by the real Alembic migrations (so the migrations are tested too)."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    from app.db import engine

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    yield
