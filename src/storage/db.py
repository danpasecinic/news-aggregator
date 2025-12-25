import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import logging

from src.scrapers.base import Article

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = "data/news.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL,
                    timestamp DATETIME,
                    content TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    sent BOOLEAN DEFAULT FALSE
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_source ON articles(source)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON articles(timestamp)
            """)
            conn.commit()

    def article_exists(self, article: Article) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM articles WHERE id = ?",
                (article.id,)
            )
            return cursor.fetchone() is not None

    def save_article(self, article: Article) -> bool:
        if self.article_exists(article):
            return False

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO articles (id, title, url, source, timestamp, content)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    article.id,
                    article.title,
                    article.url,
                    article.source,
                    article.timestamp.isoformat() if article.timestamp else None,
                    article.content
                )
            )
            conn.commit()
        return True

    def mark_sent(self, article: Article):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE articles SET sent = TRUE WHERE id = ?",
                (article.id,)
            )
            conn.commit()

    def get_unsent_articles(self) -> list[Article]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM articles
                WHERE sent = FALSE
                ORDER BY timestamp DESC
                """
            )
            rows = cursor.fetchall()

        return [
            Article(
                title=row["title"],
                url=row["url"],
                source=row["source"],
                timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else None,
                content=row["content"]
            )
            for row in rows
        ]

    def cleanup_old(self, days: int = 7):
        cutoff = datetime.now() - timedelta(days=days)
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "DELETE FROM articles WHERE created_at < ?",
                (cutoff.isoformat(),)
            )
            conn.commit()
            logger.info(f"Cleaned up {result.rowcount} old articles")

    def get_stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            sent = conn.execute("SELECT COUNT(*) FROM articles WHERE sent = TRUE").fetchone()[0]
            by_source = dict(conn.execute(
                "SELECT source, COUNT(*) FROM articles GROUP BY source"
            ).fetchall())

        return {
            "total": total,
            "sent": sent,
            "pending": total - sent,
            "by_source": by_source
        }
