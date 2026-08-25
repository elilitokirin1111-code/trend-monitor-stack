"""MySQL-specific migration contracts that SQLite cannot exercise."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.repositories.hotspot.migrations import HotspotMigrationRunner


class _MysqlDatabase:
    db_type = "mysql"


class _DuplicateIndexCursor:
    def __init__(self, columns: tuple[str, ...]) -> None:
        self.columns = columns
        self.queries: list[str] = []

    def execute(self, statement: str, params=None) -> None:
        self.queries.append(statement)
        if statement.lstrip().upper().startswith("CREATE INDEX"):
            raise RuntimeError(1061, "Duplicate key name")

    def fetchall(self) -> list[dict[str, str]]:
        return [{"COLUMN_NAME": column} for column in self.columns]


def test_mysql_partial_index_step_resumes_when_definition_matches() -> None:
    runner = HotspotMigrationRunner(_MysqlDatabase())
    cursor = _DuplicateIndexCursor(("window_end", "algorithm_version", "config_hash"))

    runner._execute_statement(  # noqa: SLF001 - migration recovery contract
        cursor,
        """CREATE INDEX idx_hotspot_clustering_window
        ON hotspot_clustering_runs(window_end, algorithm_version, config_hash);""",
    )

    assert len(cursor.queries) == 2
    assert "INFORMATION_SCHEMA.STATISTICS" in cursor.queries[1]


def test_mysql_partial_index_step_rejects_a_different_definition() -> None:
    runner = HotspotMigrationRunner(_MysqlDatabase())
    cursor = _DuplicateIndexCursor(("window_end", "algorithm_version"))

    with pytest.raises(RuntimeError, match="Duplicate key name"):
        runner._execute_statement(  # noqa: SLF001 - migration recovery contract
            cursor,
            """CREATE INDEX idx_hotspot_clustering_window
            ON hotspot_clustering_runs(window_end, algorithm_version, config_hash);""",
        )


def test_mysql_foreign_key_constraint_names_are_schema_unique() -> None:
    migrations = Path(__file__).resolve().parents[2] / "migrations" / "hotspot" / "mysql"
    constraint_names: list[str] = []
    for path in sorted(migrations.glob("*.sql")):
        constraint_names.extend(
            re.findall(
                r"\bCONSTRAINT\s+([a-z0-9_]+)",
                path.read_text(encoding="utf-8"),
                re.I,
            )
        )

    duplicates = sorted(
        name for name in set(constraint_names) if constraint_names.count(name) > 1
    )
    assert duplicates == []
