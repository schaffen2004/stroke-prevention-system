"""PostgreSQL database configuration and schema initialization."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.engine import Engine, URL

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / "infra" / ".env", override=False)


class Postgres:
    """Manage a PostgreSQL engine and initialize the application schema."""

    def __init__(
        self, database_url: str | URL | None = None, echo: bool = False
    ) -> None:
        self.engine: Engine = create_engine(
            database_url or self._database_url(),
            echo=echo,
            pool_pre_ping=True,
        )

    @staticmethod
    def _database_url() -> str | URL:
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
            raise RuntimeError(f"Missing {exc.args[0]} or DATABASE_URL") from exc

    def init_db(self, metadata: MetaData, drop: bool = False) -> None:
        """Create the UUID extension and all tables in ``metadata``."""
        with self.engine.begin() as connection:
            connection.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
            if drop:
                metadata.drop_all(connection)
            metadata.create_all(connection)

    def get_data_volume(self) -> dict[str, object]:
        """Return the database size and the size of each table."""
        database_query = text(
            """
            SELECT
                current_database() AS database_name,
                pg_size_pretty(pg_database_size(current_database()))
                    AS total_size,
                ROUND(
                    pg_database_size(current_database())
                    / 1024.0 / 1024 / 1024,
                    3
                ) AS size_gb
            """
        )
        tables_query = text(
            """
            SELECT
                relname AS table_name,
                pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
                ROUND(
                    pg_total_relation_size(relid) / 1024.0 / 1024 / 1024,
                    3
                ) AS size_gb
            FROM pg_catalog.pg_statio_user_tables
            ORDER BY pg_total_relation_size(relid) DESC
            """
        )

        with self.engine.connect() as connection:
            database = connection.execute(database_query).mappings().one()
            tables = connection.execute(tables_query).mappings().all()

        return {
            "database": dict(database),
            "tables": [dict(table) for table in tables],
        }

    def close(self) -> None:
        self.engine.dispose()

    def __enter__(self) -> Postgres:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
