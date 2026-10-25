"""Initialize the offline PostgreSQL database and generate synthetic data.

Run from the project root:
    python src/pipe/generate_data.py
    python src/pipe/generate_data.py --config path/to/config.yaml
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.db.postgres import Postgres  # noqa: E402
from src.models.offline import Base  # noqa: E402
from src.services.generator.postgres_generator import (  # noqa: E402
    PostgresGenerator,
)

LOGGER = logging.getLogger("generate_data")


def format_volume_report(volume: dict[str, Any]) -> str:
    database = volume["database"]
    tables = volume["tables"]
    lines = [
        f"Database  : {database['database_name']}",
        (
            f"Total size: {database['total_size']} "
            f"({database['size_gb']} GB)"
        ),
        "",
        f"{'Table':<32}{'Total size':>16}{'Size (GB)':>12}",
        "-" * 60,
    ]
    for table in tables:
        lines.append(
            f"{table['table_name']:<32}"
            f"{table['total_size']:>16}"
            f"{table['size_gb']:>12}"
        )
    return "\n".join(lines)


def write_volume_log(db: Postgres) -> Path:
    report = format_volume_report(db.get_data_volume())
    logs_dir = ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"data_volume_{timestamp}.log"
    log_path.write_text(f"{report}\n", encoding="utf-8")
    return log_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Initialize the offline database and generate data."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "src" / "config" / "postgres_data_generator_1GB.yaml",
        help="Path to the generation config file.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s: %(message)s"
    )

    try:
        db = Postgres()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    generator = PostgresGenerator(db=db, config_path=args.config)
    LOGGER.info("Progress file: %s", generator.progress_path)

    with db:
        db.init_db(Base.metadata)

        tables = ", ".join(
            table.name for table in Base.metadata.sorted_tables
        )
        LOGGER.info("Database ready: %s", tables)

        started = time.perf_counter()
        with generator:
            counts = generator.generate_all()

        LOGGER.info("Generated rows: %s", counts)
        LOGGER.info(
            "Finished in %.2f seconds",
            time.perf_counter() - started,
        )

        volume_log = write_volume_log(db)
        LOGGER.info("Data volume log: %s", volume_log)


if __name__ == "__main__":
    main()
