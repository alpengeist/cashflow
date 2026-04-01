from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StoredLineItem:
    sequence_no: int
    booking_date: str
    value_date: str | None
    description: str
    raw_text: str | None
    amount_cents: int
    currency: str
    category: str | None


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sha256 TEXT NOT NULL UNIQUE,
                    file_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    imported_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS line_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    sequence_no INTEGER NOT NULL,
                    booking_date TEXT NOT NULL,
                    value_date TEXT,
                    description TEXT NOT NULL,
                    raw_text TEXT,
                    amount_cents INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    category TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(document_id, sequence_no)
                );

                CREATE INDEX IF NOT EXISTS idx_line_items_booking_date
                ON line_items(booking_date);
                """
            )

    def save_import(
        self,
        *,
        sha256: str,
        file_name: str,
        file_path: str,
        source_text: str,
        model_name: str,
        line_items: list[StoredLineItem],
    ) -> int:
        imported_at = _utc_now()
        created_at = _utc_now()

        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id FROM documents WHERE sha256 = ?",
                (sha256,),
            ).fetchone()

            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO documents (
                        sha256,
                        file_name,
                        file_path,
                        source_text,
                        model_name,
                        imported_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (sha256, file_name, file_path, source_text, model_name, imported_at),
                )
                document_id = int(cursor.lastrowid)
            else:
                document_id = int(existing["id"])
                connection.execute(
                    """
                    UPDATE documents
                    SET file_name = ?,
                        file_path = ?,
                        source_text = ?,
                        model_name = ?,
                        imported_at = ?
                    WHERE id = ?
                    """,
                    (file_name, file_path, source_text, model_name, imported_at, document_id),
                )
                connection.execute(
                    "DELETE FROM line_items WHERE document_id = ?",
                    (document_id,),
                )

            connection.executemany(
                """
                INSERT INTO line_items (
                    document_id,
                    sequence_no,
                    booking_date,
                    value_date,
                    description,
                    raw_text,
                    amount_cents,
                    currency,
                    category,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        document_id,
                        item.sequence_no,
                        item.booking_date,
                        item.value_date,
                        item.description,
                        item.raw_text,
                        item.amount_cents,
                        item.currency,
                        item.category,
                        created_at,
                    )
                    for item in line_items
                ],
            )

        return document_id

    def count_line_items(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM line_items"
            ).fetchone()
        return int(row["total"])

    def fetch_line_items(self, limit: int = 500) -> list[sqlite3.Row]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    line_items.booking_date,
                    line_items.value_date,
                    line_items.description,
                    line_items.amount_cents,
                    line_items.currency,
                    line_items.category,
                    documents.file_name
                FROM line_items
                INNER JOIN documents ON documents.id = line_items.document_id
                ORDER BY line_items.booking_date DESC, line_items.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return rows

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
