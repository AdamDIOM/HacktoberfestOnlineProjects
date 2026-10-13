from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requester_name TEXT NOT NULL,
    requester_email TEXT NOT NULL,
    team TEXT NOT NULL,
    title TEXT NOT NULL,
    details TEXT NOT NULL,
    impact TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    category TEXT,
    urgency TEXT,
    urgency_score INTEGER,
    summary TEXT,
    rationale TEXT,
    suggested_owner TEXT,
    classification_error TEXT,
    model TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    classified_at TEXT,
    status_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
CREATE INDEX IF NOT EXISTS idx_requests_urgency ON requests(urgency);
CREATE INDEX IF NOT EXISTS idx_requests_category ON requests(category);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
        finally:
            conn.close()

    def insert_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = utcnow()
        fields = {
            **payload,
            "status": "new",
            "created_at": now,
            "updated_at": now,
        }
        columns = ", ".join(fields)
        placeholders = ", ".join(":" + key for key in fields)
        with self.connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO requests ({columns}) VALUES ({placeholders})",
                fields,
            )
            request_id = cursor.lastrowid
            row = conn.execute(
                "SELECT * FROM requests WHERE id = ?", (request_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to persist request")
        return dict(row)

    def get_request(self, request_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM requests WHERE id = ?", (request_id,)
            ).fetchone()
        if row is None:
            raise KeyError(request_id)
        return dict(row)

    def list_requests(
        self,
        *,
        status: Optional[str] = None,
        category: Optional[str] = None,
        urgency: Optional[str] = None,
        q: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if category:
            clauses.append("category = ?")
            params.append(category)
        if urgency:
            clauses.append("urgency = ?")
            params.append(urgency)
        if q:
            clauses.append(
                "(title LIKE ? OR details LIKE ? OR requester_name LIKE ? OR requester_email LIKE ?)"
            )
            like = f"%{q}%"
            params.extend([like, like, like, like])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT * FROM requests
            {where}
            ORDER BY
                CASE urgency
                    WHEN 'critical' THEN 0
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                    ELSE 4
                END,
                created_at DESC
        """
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def update_request(self, request_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        fields = {**fields, "updated_at": utcnow()}
        assignments = ", ".join(f"{key} = :{key}" for key in fields)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE requests SET {assignments} WHERE id = :id",
                {**fields, "id": request_id},
            )
        return self.get_request(request_id)

    def stats(self) -> dict[str, Any]:
        with self.connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
            open_count = conn.execute(
                "SELECT COUNT(*) FROM requests WHERE status != 'done'"
            ).fetchone()[0]
            by_urgency = {
                row["urgency"] or "unclassified": row["n"]
                for row in conn.execute(
                    "SELECT urgency, COUNT(*) AS n FROM requests WHERE status != 'done' GROUP BY urgency"
                )
            }
            by_category = {
                row["category"] or "unclassified": row["n"]
                for row in conn.execute(
                    "SELECT category, COUNT(*) AS n FROM requests WHERE status != 'done' GROUP BY category"
                )
            }
        return {
            "total": total,
            "open": open_count,
            "by_urgency": by_urgency,
            "by_category": by_category,
        }
