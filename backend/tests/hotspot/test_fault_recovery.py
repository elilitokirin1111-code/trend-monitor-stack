"""Phase 11 fault injection, recovery and backup-restore tests.

Collector-level provider failure/fallback is already covered by
``test_collector.py``; these tests exercise the service + storage layer:
inject a full pipeline failure, verify the system records it truthfully,
recovers on the next window, and survives a SQLite file-level backup/restore
and a migration drift.
"""

from __future__ import annotations

import asyncio
import shutil
from datetime import timedelta
from pathlib import Path

from app.domain.hotspot import Freshness
from app.repositories.hotspot import HotspotMigrationRunner, HotspotRepository
from app.repositories.hotspot.dashboard import HotspotDashboardRepository
from app.services.database import Database

from .test_dashboard_repository import _classified_database
from .test_hotspot_repository import AT, _result
from .test_trend_repository import _failed_result


def _database(tmp_path: Path, name: str = "fault.db") -> Database:
    return Database(f"sqlite:///{tmp_path / name}")


def test_failed_window_is_recorded_and_dashboard_marks_failure(
    tmp_path: Path,
) -> None:
    database = _classified_database(tmp_path)
    failed_at = AT + timedelta(hours=2)
    asyncio.run(
        HotspotRepository(database).save_collection(_failed_result(failed_at))
    )

    overview = HotspotDashboardRepository(database).get_overview(
        as_of=failed_at + timedelta(minutes=1)
    )
    weibo = next(
        item for item in overview["platforms"] if item["platform"] == "weibo"
    )
    assert weibo["status"] == "failed"
    assert weibo["freshness"] == "stale"
    assert weibo["stale_reason"] == "latest_collection_failed"
    assert weibo["error"]["code"] == "upstream_offline"
    # 失败不会伪造实时数据：事件列表仍然只有旧的真实快照证据
    events = HotspotDashboardRepository(database).list_events(limit=20, offset=0)
    assert events["total"] == 1


def test_recovery_on_next_window_creates_fresh_snapshot(tmp_path: Path) -> None:
    database = _classified_database(tmp_path)
    repository = HotspotRepository(database)
    # 注入一次失败（AT+2h 窗口）
    asyncio.run(repository.save_collection(_failed_result(AT + timedelta(hours=2))))
    # 下一窗口（AT+2h30m）恢复成功：fresh 采集
    asyncio.run(
        repository.save_collection(
            _result(
                "run-recovered",
                freshness=Freshness.FRESH,
                at=AT + timedelta(hours=2, minutes=30),
            )
        )
    )

    with database.get_connection() as connection:
        latest = connection.execute(
            """SELECT status, freshness FROM hotspot_collection_runs
               WHERE run_id = 'run-recovered'"""
        ).fetchone()
    assert latest["status"] == "success"
    assert latest["freshness"] == "fresh"

    overview = HotspotDashboardRepository(database).get_overview(
        as_of=AT + timedelta(hours=3)
    )
    weibo = next(
        item for item in overview["platforms"] if item["platform"] == "weibo"
    )
    assert weibo["status"] == "fresh"


def test_backup_and_restore_keeps_data_and_migrations(tmp_path: Path) -> None:
    database = _classified_database(tmp_path)
    source_path = Path(database.db_path)

    # 文件级备份（复制 SQLite 文件）
    backup_path = tmp_path / "backup.db"
    shutil.copy2(source_path, backup_path)

    # "故障"：删除原库文件
    source_path.unlink()

    # 从备份恢复：打开备份文件作为新库
    restored = Database(f"sqlite:///{backup_path}")
    with restored.get_connection() as connection:
        reports_ok = connection.execute(
            "SELECT COUNT(*) FROM hotspot_report_runs"
        ).fetchone()[0]
        migrations_ok = connection.execute(
            "SELECT COUNT(*) FROM hotspot_schema_migrations"
        ).fetchone()[0]
    assert reports_ok == 0  # 分类库没有报告
    assert migrations_ok == 7  # 全部迁移都在备份中
    assert HotspotMigrationRunner(restored).apply() == ()  # 无新迁移

    events = HotspotDashboardRepository(restored).list_events(limit=20, offset=0)
    assert events["total"] == 1


def test_migration_drift_is_detected_on_existing_database(tmp_path: Path) -> None:
    database = _database(tmp_path)
    HotspotMigrationRunner(database).apply()

    # 模拟迁移文件被篡改：改写已应用迁移的校验和
    migration_root = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "hotspot"
        / "sqlite"
    )
    target = migration_root / "001_initial.sql"
    original = target.read_text(encoding="utf-8")
    try:
        target.write_text(original + "\n-- tampered\n", encoding="utf-8")
        try:
            HotspotMigrationRunner(database).apply()
        except Exception as exc:  # noqa: BLE001
            from app.repositories.hotspot import MigrationDriftError

            assert isinstance(exc, MigrationDriftError)
        else:
            raise AssertionError("expected MigrationDriftError for tampered file")
    finally:
        target.write_text(original, encoding="utf-8")


def test_migration_rollback_rebuilds_from_scratch(tmp_path: Path) -> None:
    """回滚等价于重建：新库可完整应用全部迁移并保持幂等。"""
    database = _database(tmp_path, "rebuild.db")

    applied = HotspotMigrationRunner(database).apply()

    assert applied == (1, 2, 3, 4, 5, 6, 7)
    assert HotspotMigrationRunner(database).apply() == ()
    with database.get_connection() as connection:
        tables = [
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            if row["name"].startswith("hotspot_")
        ]
    assert "hotspot_report_runs" in tables
    assert "hotspot_report_deliveries" in tables
