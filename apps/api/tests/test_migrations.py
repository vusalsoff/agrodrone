"""Database migration tests verifying clean Alembic 0001 -> 0002 -> 0003 -> base -> head cycles."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

API_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TABLES = {
    "users",
    "refresh_tokens",
    "audit_logs",
    "fields",
    "devices",
    "missions",
    "media_assets",
    "detection_jobs",
    "detection_items",
    "registered_datasets",
    "edge_gateways",
    "stream_sessions",
    "alerts",
}


def test_alembic_upgrade_downgrade_upgrade(tmp_path: Path) -> None:
    db_file = tmp_path / "migration_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config(str(API_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_cfg, "head")
    engine = create_engine(db_url)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert EXPECTED_TABLES.issubset(tables)
        field_cols = {col["name"] for col in inspector.get_columns("fields")}
        assert {"owner_id", "description", "location"}.issubset(field_cols)
        device_cols = {col["name"] for col in inspector.get_columns("devices")}
        assert {
            "owner_id",
            "assigned_field_id",
            "device_identifier",
            "connection_config",
            "last_authenticated_contact_at",
        }.issubset(device_cols)
        job_cols = {col["name"] for col in inspector.get_columns("detection_jobs")}
        assert {
            "owner_id",
            "detection_mode",
            "model_id",
            "model_checksum",
            "annotated_storage_key",
            "summary_json",
        }.issubset(job_cols)
        item_cols = {col["name"] for col in inspector.get_columns("detection_items")}
        assert {
            "original_label",
            "original_confidence",
            "reviewer_id",
            "reviewed_at",
            "reviewer_notes",
        }.issubset(item_cols)
    finally:
        engine.dispose()

    command.downgrade(alembic_cfg, "base")
    engine = create_engine(db_url)
    try:
        tables_after_downgrade = set(inspect(engine).get_table_names())
        assert EXPECTED_TABLES.isdisjoint(tables_after_downgrade)
    finally:
        engine.dispose()

    command.upgrade(alembic_cfg, "head")
    engine = create_engine(db_url)
    try:
        tables_reapplied = set(inspect(engine).get_table_names())
        assert EXPECTED_TABLES.issubset(tables_reapplied)
    finally:
        engine.dispose()
