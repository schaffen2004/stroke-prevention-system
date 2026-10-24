"""Initialize the offline PostgreSQL database from the SQLAlchemy models.

Run from the project root:
    python src/pipe/generate_data.py
    python src/pipe/generate_data.py --drop
    python src/pipe/generate_data.py --database-url postgresql+psycopg2://...
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.models.offline import Base  # noqa: E402

load_dotenv(ROOT / "infra" / ".env", override=False)
LOGGER = logging.getLogger("init_database")


def get_database_url() -> str | URL:
    """Return DATABASE_URL or build one from the STROKE_DB_* variables."""
    if url := os.getenv("DATABASE_URL"):
        return url

    try:
        return URL.create(
            drivername="postgresql+psycopg2",
            username=os.environ["STROKE_DB_USER"],
            password=os.environ["STROKE_DB_PASSWORD"],
            host=os.getenv("STROKE_DB_HOST", "localhost"),
            port=int(os.getenv("STROKE_DB_PORT", "5433")),
            database=os.getenv("STROKE_DB_NAME", "stroke-db"),
        )
    except KeyError as exc:
        raise SystemExit(f"Missing {exc.args[0]} or DATABASE_URL") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the offline database.")
    parser.add_argument("--database-url", help="SQLAlchemy database URL.")
    parser.add_argument("--drop", action="store_true", help="Drop tables first.")
    parser.add_argument("--echo", action="store_true", help="Echo SQL statements.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    engine = create_engine(
        args.database_url or get_database_url(),
        echo=args.echo,
        pool_pre_ping=True,
    )

    try:
        with engine.begin() as connection:
            connection.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
            if args.drop:
                LOGGER.warning("Dropping existing tables")
                Base.metadata.drop_all(connection)
            Base.metadata.create_all(connection)
    finally:
        engine.dispose()

    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    LOGGER.info("Database ready: %s", tables)


if __name__ == "__main__":
    main()
