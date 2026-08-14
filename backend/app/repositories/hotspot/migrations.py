"""Small versioned migration runner for the isolated hotspot schema."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


class MigrationDatabase(Protocol):
    db_type: str

    def get_connection(self): ...


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    checksum: str
    statements: tuple[str, ...]


class MigrationDriftError(RuntimeError):
    """An applied migration was edited after deployment."""


class HotspotMigrationRunner:
    def __init__(
        self,
        database: MigrationDatabase,
        migrations_root: Path | None = None,
    ) -> None:
        self._database = database
        self._root = migrations_root or (
            Path(__file__).resolve().parents[3] / "migrations" / "hotspot"
        )

    def apply(self) -> tuple[int, ...]:
        migrations = self._load_migrations()
        applied_now: list[int] = []
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(self._version_table_sql())
            cursor.execute("SELECT version, checksum FROM hotspot_schema_migrations")
            applied = (
                {int(row[0]): row[1] for row in cursor.fetchall()}
                if self._database.db_type == "sqlite"
                else {int(row["version"]): row["checksum"] for row in cursor.fetchall()}
            )

            for migration in migrations:
                known_checksum = applied.get(migration.version)
                if known_checksum is not None:
                    if known_checksum != migration.checksum:
                        raise MigrationDriftError(
                            f"hotspot migration {migration.version} checksum changed"
                        )
                    continue
                for statement in migration.statements:
                    cursor.execute(statement)
                cursor.execute(
                    self._sql(
                        "INSERT INTO hotspot_schema_migrations "
                        "(version, name, checksum, applied_at) VALUES (?, ?, ?, ?)"
                    ),
                    (
                        migration.version,
                        migration.name,
                        migration.checksum,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                applied_now.append(migration.version)
        return tuple(applied_now)

    def _load_migrations(self) -> tuple[Migration, ...]:
        directory = self._root / self._database.db_type
        migrations: list[Migration] = []
        for path in sorted(directory.glob("*.sql")):
            match = re.match(r"^(\d+)_([a-z0-9_]+)\.sql$", path.name)
            if match is None:
                continue
            body = path.read_text(encoding="utf-8")
            statements = tuple(
                statement.strip()
                for statement in body.split("-- statement-breakpoint")
                if statement.strip()
            )
            migrations.append(
                Migration(
                    version=int(match.group(1)),
                    name=match.group(2),
                    checksum=hashlib.sha256(body.encode()).hexdigest(),
                    statements=statements,
                )
            )
        versions = [migration.version for migration in migrations]
        if not migrations or len(versions) != len(set(versions)):
            raise RuntimeError(f"invalid hotspot migrations in {directory}")
        return tuple(migrations)

    def _sql(self, statement: str) -> str:
        return (
            statement
            if self._database.db_type == "sqlite"
            else statement.replace("?", "%s")
        )

    def _version_table_sql(self) -> str:
        if self._database.db_type == "sqlite":
            return """
                CREATE TABLE IF NOT EXISTS hotspot_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
            """
        return """
            CREATE TABLE IF NOT EXISTS hotspot_schema_migrations (
                version INTEGER PRIMARY KEY,
                name VARCHAR(191) NOT NULL,
                checksum CHAR(64) NOT NULL,
                applied_at VARCHAR(40) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
