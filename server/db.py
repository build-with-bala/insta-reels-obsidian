import json
import sqlite3


class ReelDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reels (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    creator_username TEXT,
                    creator_display_name TEXT,
                    caption TEXT,
                    tags TEXT,
                    thumbnail_url TEXT,
                    user_note TEXT,
                    timestamp TEXT NOT NULL,
                    status TEXT DEFAULT 'processed',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def reel_exists(self, reel_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM reels WHERE id = ?", (reel_id,)
            ).fetchone()
            return row is not None

    def insert_reel(
        self,
        reel_id: str,
        url: str,
        timestamp: str,
        creator_username: str = None,
        creator_display_name: str = None,
        caption: str = None,
        tags: list = None,
        thumbnail_url: str = None,
        user_note: str = None,
        status: str = "processed",
    ):
        tags_json = json.dumps(tags) if tags else None
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO reels
                   (id, url, creator_username, creator_display_name,
                    caption, tags, thumbnail_url, user_note, timestamp, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (reel_id, url, creator_username, creator_display_name,
                 caption, tags_json, thumbnail_url, user_note, timestamp, status),
            )

    def get_reel(self, reel_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM reels WHERE id = ?", (reel_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_reels_by_status(self, status: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reels WHERE status = ? ORDER BY timestamp",
                (status,),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_reel_tags(self, reel_id: str, tags: list, status: str):
        with self._connect() as conn:
            conn.execute(
                "UPDATE reels SET tags = ?, status = ? WHERE id = ?",
                (json.dumps(tags), status, reel_id),
            )

    def get_retry_candidates(self, limit: int = 50) -> list[dict]:
        """Get reels that failed metadata fetch or tagging, for retry."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reels WHERE status IN ('fetch-failed', 'untagged') "
                "ORDER BY created_at LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        """Return counts by status for monitoring."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as count FROM reels GROUP BY status"
            ).fetchall()
            return {row["status"]: row["count"] for row in rows}
