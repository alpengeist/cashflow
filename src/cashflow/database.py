from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Iterator


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

                CREATE INDEX IF NOT EXISTS idx_documents_file_name
                ON documents(file_name);
                """
            )
            connection.execute("DROP TRIGGER IF EXISTS line_items_search_after_insert")
            connection.execute("DROP TRIGGER IF EXISTS line_items_search_after_delete")
            connection.execute("DROP TRIGGER IF EXISTS line_items_search_after_update")
            connection.execute("DROP TABLE IF EXISTS line_items_search")

    def save_import(
        self,
        *,
        document_key: str,
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
                "SELECT id FROM documents WHERE file_name = ?",
                (file_name,),
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
                    (
                        document_key,
                        file_name,
                        file_path,
                        source_text,
                        model_name,
                        imported_at,
                    ),
                )
                document_id = int(cursor.lastrowid)
            else:
                document_id = int(existing["id"])
                connection.execute(
                    """
                    UPDATE documents
                    SET sha256 = ?,
                        file_name = ?,
                        file_path = ?,
                        source_text = ?,
                        model_name = ?,
                        imported_at = ?
                    WHERE id = ?
                    """,
                    (
                        document_key,
                        file_name,
                        file_path,
                        source_text,
                        model_name,
                        imported_at,
                        document_id,
                    ),
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

    def count_line_items(self, search_text: str | None = None) -> int:
        where_clauses, parameters = self._build_line_item_search(search_text)
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM line_items
                {where_sql}
                """,
                parameters,
            ).fetchone()
        return int(row["total"])

    def has_document_file_name(self, file_name: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM documents WHERE file_name = ? LIMIT 1",
                (file_name,),
            ).fetchone()
        return row is not None

    def fetch_existing_document_file_names(self, file_names: Iterable[str]) -> set[str]:
        normalized_names = tuple(dict.fromkeys(file_names))
        if not normalized_names:
            return set()

        placeholders = ", ".join("?" for _ in normalized_names)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT file_name
                FROM documents
                WHERE file_name IN ({placeholders})
                """,
                normalized_names,
            ).fetchall()
        return {str(row["file_name"]) for row in rows}

    def fetch_line_items(
        self,
        limit: int = 500,
        *,
        search_text: str | None = None,
    ) -> list[sqlite3.Row]:
        where_clauses, parameters = self._build_line_item_search(search_text)
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    line_items.id,
                    line_items.booking_date,
                    line_items.value_date,
                    line_items.description,
                    line_items.amount_cents,
                    line_items.currency,
                    line_items.category,
                    documents.file_name,
                    documents.file_path
                FROM line_items
                INNER JOIN documents ON documents.id = line_items.document_id
                {where_sql}
                ORDER BY line_items.booking_date DESC, line_items.id DESC
                LIMIT ?
                """,
                (*parameters, limit),
            ).fetchall()
        return rows

    def update_line_item_category(self, line_item_id: int, category: str | None) -> None:
        normalized_category = (
            category.strip().lower() if category and category.strip() else None
        )
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE line_items
                SET category = ?
                WHERE id = ?
                """,
                (normalized_category, line_item_id),
            )

    def fetch_available_years(self) -> list[int]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT CAST(SUBSTR(booking_date, 1, 4) AS INTEGER) AS year
                FROM line_items
                WHERE booking_date GLOB '????-??-??'
                ORDER BY year DESC
                """
            ).fetchall()
        return [int(row["year"]) for row in rows]

    def fetch_category_totals(self, year: int, *, inflow: bool) -> list[sqlite3.Row]:
        comparator = ">" if inflow else "<"
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(TRIM(category), ''), 'uncategorized') AS category,
                    ABS(SUM(amount_cents)) AS total_amount_cents
                FROM line_items
                WHERE SUBSTR(booking_date, 1, 4) = ?
                  AND amount_cents {comparator} 0
                GROUP BY COALESCE(NULLIF(TRIM(category), ''), 'uncategorized')
                ORDER BY total_amount_cents DESC, category ASC
                """,
                (str(year),),
            ).fetchall()
        return rows

    def fetch_active_month_count(self, year: int) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(DISTINCT SUBSTR(booking_date, 1, 7)) AS month_count
                FROM line_items
                WHERE SUBSTR(booking_date, 1, 4) = ?
                  AND booking_date GLOB '????-??-??'
                """,
                (str(year),),
            ).fetchone()
        return int(row["month_count"])

    def fetch_line_items_for_category(
        self,
        year: int,
        *,
        inflow: bool,
        category: str,
    ) -> list[sqlite3.Row]:
        comparator = ">" if inflow else "<"
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    line_items.booking_date,
                    line_items.description,
                    line_items.amount_cents,
                    line_items.currency,
                    COALESCE(NULLIF(TRIM(line_items.category), ''), 'uncategorized') AS category,
                    documents.file_name,
                    documents.file_path
                FROM line_items
                INNER JOIN documents ON documents.id = line_items.document_id
                WHERE SUBSTR(line_items.booking_date, 1, 4) = ?
                  AND line_items.amount_cents {comparator} 0
                  AND COALESCE(NULLIF(TRIM(line_items.category), ''), 'uncategorized') = ?
                ORDER BY line_items.booking_date DESC, line_items.id DESC
                """,
                (str(year), category),
            ).fetchall()
        return rows

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _build_line_item_search(
        self,
        search_text: str | None,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        normalized = " ".join((search_text or "").split())
        if not normalized:
            return (), ()

        tokens = normalized.split()
        where_clauses = tuple("LOWER(line_items.description) LIKE ? ESCAPE '\\'" for _ in tokens)
        parameters = tuple(
            f"%{self._escape_like_pattern(token.lower())}%"
            for token in tokens
        )
        return where_clauses, parameters

    def _escape_like_pattern(self, value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
