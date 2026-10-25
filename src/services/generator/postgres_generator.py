"""Generate synthetic data for the offline PostgreSQL database."""

from __future__ import annotations

import json
import logging
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, Sequence

import numpy as np
import yaml
from psycopg2.extensions import connection as Connection
from psycopg2.extras import execute_values, register_uuid
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.db.postgres import Postgres  # noqa: E402
from src.utils.volume import VOLUME_FACTORS  # noqa: E402

DEFAULT_CONFIG = (
    ROOT / "src" / "config" / "postgres_data_generator_1GB.yaml"
)
DEFAULT_SEED = 42

LOGGER = logging.getLogger("postgres_generator")


class PostgresGenerator:
    """Generate synthetic data from a table specification config."""

    def __init__(
        self,
        db: Postgres,
        config_path: Path | str = DEFAULT_CONFIG,
        scale: float = 1.0,
        seed: int | None = None,
        state_path: Path | str | None = None,
    ) -> None:
        self.db = db
        self.config_path = Path(config_path)
        self.progress_path = (
            Path(state_path)
            if state_path is not None
            else ROOT
            / "logs"
            / f"{self.config_path.stem}.progress.json"
        )
        self.scale = scale
        self.seed = seed
        self.conn: Connection | None = None

        self.config: dict[str, Any] = {}
        self.tables: dict[str, dict[str, Any]] = {}
        self.start_time = datetime(2023, 1, 1)
        self.end_time = datetime(2025, 12, 31, 23, 59, 59)
        self.n_patients = 0
        self.duplicate_rate = 0.0
        self.batch_size = 50_000
        self.rng = np.random.default_rng(DEFAULT_SEED)
        self.next_id = 1
        self.state: dict[str, Any] = {
            "processed": {},
            "next_id": 1,
        }

        self.load_config()

    @staticmethod
    def _parse_datetime(value: Any, default: datetime) -> datetime:
        if value is None:
            return default
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

    def load_config(self) -> dict[str, Any]:
        if self.scale <= 0:
            raise ValueError("scale must be greater than 0")

        with self.config_path.open(encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}

        generation = config.get("generation", {})
        self.start_time = self._parse_datetime(
            generation.get("start_time"), datetime(2023, 1, 1)
        )
        self.end_time = self._parse_datetime(
            generation.get("end_time"),
            datetime(2025, 12, 31, 23, 59, 59),
        )
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be greater than start_time")

        raw_count = int(generation["demographic_count"])
        self.n_patients = max(1, int(raw_count * self.scale))
        self.duplicate_rate = float(
            generation.get("duplicated_rate", 0.0)
        )
        if not 0 <= self.duplicate_rate < 1:
            raise ValueError("duplicated_rate must be in [0, 1)")

        self.batch_size = int(generation.get("batch_size", 50_000))
        if self.batch_size <= 0:
            raise ValueError("batch_size must be greater than 0")

        self.tables = config.get("tables", {})
        if not self.tables:
            raise ValueError("tables must be configured")
        for table, spec in self.tables.items():
            self._validate_table_spec(table, spec)

        effective_seed = int(generation.get("seed", DEFAULT_SEED))
        if self.seed is not None:
            effective_seed = self.seed

        self.config = config
        self.rng = np.random.default_rng(effective_seed)
        random.seed(effective_seed)
        self.next_id = 1
        self.state = {"processed": {}, "next_id": 1}
        return config

    def _validate_table_spec(
        self, table: str, spec: dict[str, Any]
    ) -> None:
        if "uuid_prefix" not in spec:
            raise ValueError(f"Missing uuid_prefix for {table}")
        if "count" not in spec:
            raise ValueError(f"Missing count for {table}")

        columns = spec.get("columns", {})
        if not columns:
            raise ValueError(f"Missing columns for {table}")
        primary_key = spec.get("primary_key")
        if primary_key not in columns:
            raise ValueError(f"Invalid primary_key for {table}")

        for column, column_spec in columns.items():
            column_type = column_spec.get("type")
            if column_type is None:
                raise ValueError(f"Missing type for {table}.{column}")

            if column_type == "category":
                values = column_spec.get("values", [])
                weights = column_spec.get("weights", [])
                if not values:
                    raise ValueError(
                        f"Missing values for {table}.{column}"
                    )
                if weights and len(weights) != len(values):
                    raise ValueError(
                        f"Invalid weights for {table}.{column}"
                    )
                if column_spec.get("skew") and not weights:
                    raise ValueError(
                        f"Missing weights for {table}.{column}"
                    )

            if column_type == "patient":
                parent = column_spec.get("table")
                if parent not in self.tables:
                    raise ValueError(
                        f"Invalid patient table for {table}.{column}"
                    )

            if column_type in {
                "offset_datetime",
                "computed_float",
            }:
                source = column_spec.get("source")
                if source not in columns:
                    raise ValueError(
                        f"Invalid source for {table}.{column}"
                    )

            if column_type == "float":
                for condition in column_spec.get("when", {}):
                    if condition not in columns:
                        raise ValueError(
                            f"Invalid condition for {table}.{column}"
                        )

    def connect(self) -> Connection:
        if self.conn is not None:
            return self.conn

        register_uuid()
        self.conn = self.db.engine.raw_connection()
        return self.conn

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self) -> PostgresGenerator:
        self.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _connection(self) -> Connection:
        if self.conn is None:
            raise RuntimeError("PostgresGenerator is not connected")
        return self.conn

    def _load_state(self) -> None:
        if not self.progress_path.exists():
            self.state = {"processed": {}, "next_id": 1}
            self.next_id = 1
            return

        try:
            data = json.loads(
                self.progress_path.read_text(encoding="utf-8")
            )
            processed = {
                str(table): int(count)
                for table, count in data.get("processed", {}).items()
            }
            next_id = int(data.get("next_id", 1))
        except (OSError, TypeError, ValueError) as exc:
            LOGGER.warning(
                "Invalid progress file %s (%s); starting over",
                self.progress_path,
                exc,
            )
            self.state = {"processed": {}, "next_id": 1}
            self.next_id = 1
            return

        self.state = {"processed": processed, "next_id": next_id}
        self.next_id = next_id
        LOGGER.info("Loaded progress from %s", self.progress_path)

    def _save_state(self) -> None:
        self.state["next_id"] = self.next_id
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.progress_path.with_suffix(
            self.progress_path.suffix + ".tmp"
        )
        temporary_path.write_text(
            json.dumps(self.state, indent=2), encoding="utf-8"
        )
        temporary_path.replace(self.progress_path)

    def _make_uuid(self, table: str, index: int) -> uuid.UUID:
        prefix = int(self.tables[table]["uuid_prefix"])
        return uuid.UUID(int=(prefix << 96) | index)

    def _next_uuid(self, table: str) -> uuid.UUID:
        value = self.next_id
        self.next_id += 1
        return self._make_uuid(table, value)

    def _batch_ranges(
        self,
        total: int,
        desc: str | None = None,
        start: int = 0,
    ) -> Iterator[tuple[int, int]]:
        progress = (
            tqdm(
                total=total,
                initial=start,
                desc=desc,
                unit="rows",
                unit_scale=True,
            )
            if desc
            else None
        )
        try:
            for batch_start in range(start, total, self.batch_size):
                end = min(batch_start + self.batch_size, total)
                yield batch_start, end
                if progress is not None:
                    progress.update(end - batch_start)
        finally:
            if progress is not None:
                progress.close()

    def _write_rows(
        self,
        table: str,
        columns: Sequence[str],
        rows: Sequence[tuple[Any, ...]],
    ) -> None:
        if not rows:
            return
        query = (
            f"INSERT INTO {table} ({', '.join(columns)}) "
            "VALUES %s ON CONFLICT DO NOTHING"
        )
        with self._connection().cursor() as cursor:
            execute_values(
                cursor,
                query,
                rows,
                page_size=min(len(rows), self.batch_size),
            )
        self._connection().commit()

    def _random_datetimes(self, size: int) -> list[datetime]:
        seconds = int(
            (self.end_time - self.start_time).total_seconds()
        )
        offsets = self.rng.integers(0, seconds, size=size)
        return [
            self.start_time + timedelta(seconds=int(offset))
            for offset in offsets
        ]

    def _with_duplicates(
        self,
        rows: list[tuple[Any, ...]],
        rate: float,
        duplicate_factory: Any,
    ) -> list[tuple[Any, ...]]:
        duplicate_count = int(len(rows) * rate)
        if duplicate_count <= 0:
            return rows

        indices = self.rng.choice(
            len(rows), size=duplicate_count, replace=False
        )
        duplicates = [
            duplicate_factory(rows[int(index)]) for index in indices
        ]
        combined = rows + duplicates
        random.shuffle(combined)
        return combined

    def _generate_column_data(
        self,
        table: str,
        column: str,
        spec: dict[str, Any],
        size: int,
        start: int,
        generated: dict[str, Any],
    ) -> Any:
        column_type = spec["type"]

        if column_type == "uuid":
            return [self._next_uuid(table) for _ in range(size)]

        if column_type == "patient":
            parent = spec["table"]
            if spec.get("mode") == "round_robin":
                indices = (
                    (start + np.arange(size)) % self.n_patients
                ) + 1
            else:
                indices = self.rng.integers(
                    1, self.n_patients + 1, size=size
                )
            return [
                self._make_uuid(parent, int(index))
                for index in indices
            ]

        if column_type == "sequence":
            return ((start + np.arange(size)) // self.n_patients) + 1

        if column_type == "int":
            return self.rng.integers(
                int(spec["min"]),
                int(spec["max"]) + 1,
                size=size,
            )

        if column_type == "float":
            values = self.rng.uniform(
                float(spec["min"]), float(spec["max"]), size
            )
            for condition, ranges in spec.get("when", {}).items():
                mask = np.asarray(generated[condition], dtype=bool)
                values = np.where(
                    mask,
                    self.rng.uniform(
                        float(ranges["min"]),
                        float(ranges["max"]),
                        size,
                    ),
                    values,
                )
            return self._round_values(values, spec)

        if column_type == "computed_float":
            source = np.asarray(generated[spec["source"]])
            factors = self.rng.uniform(
                float(spec["min_factor"]),
                float(spec["max_factor"]),
                size,
            )
            values = source * factors / float(
                spec.get("divisor", 1)
            )
            return self._round_values(values, spec)

        if column_type == "bool":
            return self.rng.random(size) < float(
                spec["probability"]
            )

        if column_type == "category":
            values = tuple(spec["values"])
            if spec.get("skew"):
                weights = self._normalize_weights(spec["weights"])
                return self.rng.choice(
                    values, size=size, p=weights
                )
            return self.rng.choice(values, size=size)

        if column_type == "datetime":
            return self._random_datetimes(size)

        if column_type == "offset_datetime":
            source = generated[spec["source"]]
            offsets = self.rng.integers(
                int(spec["seconds_min"]),
                int(spec["seconds_max"]) + 1,
                size=size,
            )
            return [
                source[index] + timedelta(seconds=int(offsets[index]))
                for index in range(size)
            ]

        raise ValueError(
            f"Unsupported column type for {table}.{column}: "
            f"{column_type}"
        )

    @staticmethod
    def _round_values(
        values: np.ndarray, spec: dict[str, Any]
    ) -> np.ndarray:
        precision = spec.get("precision")
        if precision is None:
            return values
        return np.round(values, int(precision))

    @staticmethod
    def _normalize_weights(weights: Sequence[float]) -> tuple[float, ...]:
        total = sum(float(weight) for weight in weights)
        if total <= 0:
            raise ValueError("Weights must have a positive sum")
        return tuple(float(weight) / total for weight in weights)

    @staticmethod
    def _scalar(value: Any) -> Any:
        if isinstance(value, np.generic):
            return value.item()
        return value

    def _generate_batch(
        self,
        table: str,
        spec: dict[str, Any],
        start: int,
        size: int,
    ) -> list[tuple[Any, ...]]:
        columns = spec["columns"]
        generated: dict[str, Any] = {}
        for column, column_spec in columns.items():
            generated[column] = self._generate_column_data(
                table,
                column,
                column_spec,
                size,
                start,
                generated,
            )

        names = tuple(columns)
        return [
            tuple(
                self._scalar(generated[name][index])
                for name in names
            )
            for index in range(size)
        ]

    def _duplicate_factory(
        self, table: str, spec: dict[str, Any]
    ) -> Any:
        columns = tuple(spec["columns"])
        primary_index = columns.index(spec["primary_key"])

        def duplicate(row: tuple[Any, ...]) -> tuple[Any, ...]:
            values = list(row)
            values[primary_index] = self._next_uuid(table)
            return tuple(values)

        return duplicate

    def _generate_table_rows(
        self,
        table: str,
        spec: dict[str, Any],
        count: int,
        start: int = 0,
    ) -> int:
        columns = tuple(spec["columns"])
        total = 0
        for batch_start, end in self._batch_ranges(
            count, table, start=start
        ):
            size = end - batch_start
            rows = self._generate_batch(
                table, spec, batch_start, size
            )
            if spec.get("duplicate", False):
                rows = self._with_duplicates(
                    rows,
                    self.duplicate_rate,
                    self._duplicate_factory(table, spec),
                )
            self._write_rows(table, columns, rows)
            total += len(rows)
            self.state["processed"][table] = end
            self._save_state()

        LOGGER.info("%s: %s rows", table, f"{total:,}")
        return total

    def generate_table(
        self,
        table: str,
        count: int | None = None,
        start: int = 0,
    ) -> int:
        try:
            spec = self.tables[table]
        except KeyError as exc:
            raise ValueError(f"Unsupported table: {table}") from exc

        if count is None:
            count = self.compute_table_counts()[table]

        if spec.get("count") == "demographic_count" and count > 0:
            self.n_patients = count

        return self._generate_table_rows(
            table, spec, count, start=start
        )

    def compute_table_counts(self) -> dict[str, int]:
        generation = self.config.get("generation", {})
        volume = generation.get("volume") or {}
        volume_value = volume.get("value")

        total_bytes = 0.0
        if volume_value is not None:
            unit = str(volume.get("unit", "GB")).upper()
            if unit not in VOLUME_FACTORS:
                raise ValueError(
                    f"Unsupported volume unit: {unit}. "
                    f"Use one of {', '.join(VOLUME_FACTORS)}"
                )
            total_bytes = float(volume_value) * VOLUME_FACTORS[unit]

        counts: dict[str, int] = {}
        for table, spec in self.tables.items():
            source = spec["count"]
            if source == "demographic_count":
                count = self.n_patients
            elif source == "volume":
                if total_bytes > 0:
                    count = int(
                        total_bytes
                        * float(spec["share"])
                        / int(spec["row_bytes"])
                    )
                else:
                    count = int(
                        self.n_patients
                        * float(spec["fallback_multiplier"])
                    )
                count = max(1, int(count * self.scale))
            elif isinstance(source, int):
                count = max(1, int(source * self.scale))
            else:
                raise ValueError(
                    f"Unsupported count source for {table}: {source}"
                )
            counts[table] = count
        return counts

    def truncate(self) -> None:
        tables = ", ".join(reversed(tuple(self.tables)))
        with self._connection().cursor() as cursor:
            cursor.execute(
                f"TRUNCATE TABLE {tables} "
                "RESTART IDENTITY CASCADE"
            )
        self._connection().commit()
        self.state = {"processed": {}, "next_id": 1}
        self.next_id = 1
        self._save_state()

    def generate_all(self) -> dict[str, int]:
        counts = self.compute_table_counts()
        self._load_state()

        for table, count in counts.items():
            LOGGER.info("%s count: %s", table, f"{count:,}")

        for table, count in counts.items():
            processed = int(
                self.state["processed"].get(table, 0)
            )
            if processed >= count:
                LOGGER.info(
                    "%s already completed (%s/%s)",
                    table,
                    f"{processed:,}",
                    f"{count:,}",
                )
                continue
            if processed > 0:
                LOGGER.info(
                    "Resuming %s at %s/%s",
                    table,
                    f"{processed:,}",
                    f"{count:,}",
                )
            self.generate_table(table, count, start=processed)

        self._save_state()
        return counts
