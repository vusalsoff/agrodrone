"""Durable SQLite + disk offline store-and-forward spool with bounded quota & retry limits."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class QueuedSnapshot:
    id: str
    file_path: Path
    filename: str
    byte_size: int
    sha256: str
    notes: str | None
    attempts: int
    created_at: str


class OfflineSnapshotSpool:
    """Persists captured ESP32-CAM snapshots when backend/internet connectivity is unavailable."""

    def __init__(self, spool_dir: Path, quota_bytes: int = 100 * 1024 * 1024) -> None:
        self.spool_dir = spool_dir
        self.quota_bytes = quota_bytes
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.spool_dir / "spool.db"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_snapshots (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    rel_path TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    notes TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def stats(self) -> tuple[int, int]:
        """Return (queue_depth, total_queued_bytes)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt, COALESCE(SUM(byte_size), 0) AS total_bytes FROM pending_snapshots"
            ).fetchone()
            return int(row["cnt"]), int(row["total_bytes"])

    def _evict_oldest_until_fits(self, needed_bytes: int) -> None:
        _, total_bytes = self.stats()
        if total_bytes + needed_bytes <= self.quota_bytes:
            return
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, rel_path, byte_size FROM pending_snapshots ORDER BY created_at ASC"
            ).fetchall()
            for row in rows:
                if total_bytes + needed_bytes <= self.quota_bytes:
                    break
                file_path = self.spool_dir / str(row["rel_path"])
                file_path.unlink(missing_ok=True)
                conn.execute("DELETE FROM pending_snapshots WHERE id = ?", (row["id"],))
                total_bytes -= int(row["byte_size"])
            conn.commit()

    def enqueue(self, jpeg_bytes: bytes, *, filename: str = "esp32_snapshot.jpg", notes: str | None = None) -> QueuedSnapshot:
        if len(jpeg_bytes) > self.quota_bytes:
            raise ValueError("Snapshot exceeds total offline spool quota.")

        self._evict_oldest_until_fits(len(jpeg_bytes))
        snap_id = uuid.uuid4().hex
        rel_path = f"{snap_id}.jpg"
        target = self.spool_dir / rel_path
        target.write_bytes(jpeg_bytes)
        digest = hashlib.sha256(jpeg_bytes).hexdigest()
        created_at = datetime.now(UTC).isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_snapshots (id, filename, rel_path, byte_size, sha256, notes, attempts, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (snap_id, filename, rel_path, len(jpeg_bytes), digest, notes, created_at),
            )
            conn.commit()

        return QueuedSnapshot(
            id=snap_id,
            file_path=target,
            filename=filename,
            byte_size=len(jpeg_bytes),
            sha256=digest,
            notes=notes,
            attempts=0,
            created_at=created_at,
        )

    def list_pending(self, *, max_attempts: int = 5, limit: int = 20) -> list[QueuedSnapshot]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, filename, rel_path, byte_size, sha256, notes, attempts, created_at
                FROM pending_snapshots
                WHERE attempts < ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (max_attempts, limit),
            ).fetchall()
            return [
                QueuedSnapshot(
                    id=str(r["id"]),
                    file_path=self.spool_dir / str(r["rel_path"]),
                    filename=str(r["filename"]),
                    byte_size=int(r["byte_size"]),
                    sha256=str(r["sha256"]),
                    notes=r["notes"],
                    attempts=int(r["attempts"]),
                    created_at=str(r["created_at"]),
                )
                for r in rows
            ]

    def mark_uploaded(self, snap_id: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT rel_path FROM pending_snapshots WHERE id = ?", (snap_id,)
            ).fetchone()
            if row is not None:
                (self.spool_dir / str(row["rel_path"])).unlink(missing_ok=True)
                conn.execute("DELETE FROM pending_snapshots WHERE id = ?", (snap_id,))
                conn.commit()

    def record_failure(self, snap_id: str, error_message: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE pending_snapshots
                SET attempts = attempts + 1, last_error = ?
                WHERE id = ?
                """,
                (error_message[:500], snap_id),
            )
            conn.commit()
