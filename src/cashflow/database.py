from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Iterable, Iterator


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

                CREATE INDEX IF NOT EXISTS idx_line_items_category
                ON line_items(category);

                CREATE INDEX IF NOT EXISTS idx_line_items_amount_cents
                ON line_items(amount_cents);

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
        on_progress: Callable[[str], None] | None = None,
    ) -> int:
        imported_at = _utc_now()
        created_at = _utc_now()

        with self._connect() as connection:
            if on_progress:
                on_progress(f"Checking existing data for {file_name}...")
            existing = connection.execute(
                "SELECT id FROM documents WHERE file_name = ?",
                (file_name,),
            ).fetchone()

            if existing is None:
                if on_progress:
                    on_progress(f"Creating document entry for {file_name}...")
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
                if on_progress:
                    on_progress(f"Updating document entry for {file_name}...")
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
                if on_progress:
                    on_progress(f"Clearing old transactions for {file_name}...")
                connection.execute(
                    "DELETE FROM line_items WHERE document_id = ?",
                    (document_id,),
                )

            if on_progress:
                on_progress(f"Saving {len(line_items)} transactions for {file_name}...")
            
            # Pre-calculate tuples for executemany to avoid overhead during the insert
            insert_data = [
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
            ]
            
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
                insert_data,
            )

        return document_id

    def count_line_items(
        self,
        search_text: str | None = None,
        *,
        year: int | None = None,
    ) -> int:
        where_clauses, parameters = self._build_line_item_filters(
            search_text=search_text,
            year=year,
        )
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

    def count_documents(self, *, year: int | None = None) -> int:
        where_sql = ""
        parameters = []
        if year is not None:
            where_sql = (
                "WHERE id IN (SELECT DISTINCT document_id FROM line_items "
                "WHERE SUBSTR(booking_date, 1, 4) = ?)"
            )
            parameters.append(str(year))
        
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) AS total FROM documents {where_sql}",
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
        limit: int | None = None,
        *,
        search_text: str | None = None,
        year: int | None = None,
    ) -> list[sqlite3.Row]:
        where_clauses, parameters = self._build_line_item_filters(
            search_text=search_text,
            year=year,
        )
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        limit_sql = ""
        query_parameters: tuple[str | int, ...] = parameters
        if limit is not None:
            limit_sql = "LIMIT ?"
            query_parameters = (*parameters, limit)
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
                    COALESCE(NULLIF(TRIM(line_items.category), ''), '') AS category,
                    documents.file_name,
                    documents.file_path
                FROM line_items
                INNER JOIN documents ON documents.id = line_items.document_id
                {where_sql}
                ORDER BY line_items.booking_date DESC, line_items.id DESC
                {limit_sql}
                """,
                query_parameters,
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

    def fetch_available_outflow_categories(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT COALESCE(NULLIF(TRIM(category), ''), 'uncategorized') AS category
                FROM line_items
                WHERE amount_cents < 0
                ORDER BY category ASC
                """
            ).fetchall()
        return [str(row["category"]) for row in rows]

    def fetch_category_totals(self, year: int | None, *, inflow: bool) -> list[sqlite3.Row]:
        comparator = ">" if inflow else "<"
        where_clauses = [f"amount_cents {comparator} 0"]
        parameters = []
        if year is not None:
            where_clauses.append("SUBSTR(booking_date, 1, 4) = ?")
            parameters.append(str(year))
        
        where_sql = " AND ".join(where_clauses)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(TRIM(category), ''), 'uncategorized') AS category,
                    ABS(SUM(amount_cents)) AS total_amount_cents
                FROM line_items
                WHERE {where_sql}
                GROUP BY COALESCE(NULLIF(TRIM(category), ''), 'uncategorized')
                ORDER BY total_amount_cents DESC, category ASC
                """,
                parameters,
            ).fetchall()
        return rows

    def fetch_active_month_count(self, year: int | None) -> int:
        where_clauses = ["booking_date GLOB '????-??-??'"]
        parameters = []
        if year is not None:
            where_clauses.append("SUBSTR(booking_date, 1, 4) = ?")
            parameters.append(str(year))
        
        where_sql = " AND ".join(where_clauses)
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(DISTINCT SUBSTR(booking_date, 1, 7)) AS month_count
                FROM line_items
                WHERE {where_sql}
                """,
                parameters,
            ).fetchone()
        return int(row["month_count"])

    def fetch_line_items_for_category(
        self,
        year: int | None,
        *,
        inflow: bool,
        category: str,
    ) -> list[sqlite3.Row]:
        comparator = ">" if inflow else "<"
        where_clauses = [
            f"line_items.amount_cents {comparator} 0",
            "COALESCE(NULLIF(TRIM(line_items.category), ''), 'uncategorized') = ?"
        ]
        parameters = [category]
        if year is not None:
            where_clauses.append("SUBSTR(line_items.booking_date, 1, 4) = ?")
            parameters.append(str(year))
            
        where_sql = " AND ".join(where_clauses)
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
                WHERE {where_sql}
                ORDER BY line_items.booking_date DESC, line_items.id DESC
                """,
                parameters,
            ).fetchall()
        return rows

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _build_line_item_filters(
        self,
        *,
        search_text: str | None,
        year: int | None,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        where_clauses: list[str] = []
        parameters: list[str] = []

        if year is not None:
            where_clauses.append("SUBSTR(line_items.booking_date, 1, 4) = ?")
            parameters.append(str(year))

        normalized = " ".join((search_text or "").split())
        if not normalized:
            return tuple(where_clauses), tuple(parameters)

        tokens = normalized.split()
        where_clauses.extend(
            "LOWER(line_items.description) LIKE ? ESCAPE '\\'" for _ in tokens
        )
        parameters.extend(
            f"%{self._escape_like_pattern(token.lower())}%"
            for token in tokens
        )
        return tuple(where_clauses), tuple(parameters)

    def _escape_like_pattern(self, value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
