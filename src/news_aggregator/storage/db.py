import logging
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from rapidfuzz import fuzz
from news_aggregator.config import settings
from news_aggregator.scrapers.base import Article

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 75


def normalize_title(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    stopwords = {"the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "is", "are", "was", "were"}
    words = [w for w in title.split() if w not in stopwords]
    return " ".join(words)


class Database:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path or settings.storage.database_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    normalized_title TEXT,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL,
                    timestamp DATETIME,
                    content TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    sent BOOLEAN DEFAULT FALSE,
                    duplicate_of TEXT,
                    other_sources TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON articles(source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON articles(timestamp)")
            try:
                conn.execute("ALTER TABLE articles ADD COLUMN normalized_title TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE articles ADD COLUMN duplicate_of TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE articles ADD COLUMN other_sources TEXT")
            except sqlite3.OperationalError:
                pass
            conn.execute("CREATE INDEX IF NOT EXISTS idx_duplicate ON articles(duplicate_of)")
            conn.commit()

    def article_exists(self, article: Article) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT 1 FROM articles WHERE id = ?", (article.id,))
            return cursor.fetchone() is not None

    def find_similar(self, article: Article, hours: int = 24) -> tuple[str, int] | None:
        normalized = normalize_title(article.title)
        cutoff = datetime.now() - timedelta(hours=hours)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """SELECT id, title, normalized_title, source FROM articles
                   WHERE created_at > ? AND duplicate_of IS NULL""",
                (cutoff.isoformat(),)
            )
            rows = cursor.fetchall()

        for row in rows:
            existing_normalized = row["normalized_title"] or normalize_title(row["title"])
            similarity = fuzz.token_sort_ratio(normalized, existing_normalized)
            if similarity >= SIMILARITY_THRESHOLD:
                return row["id"], similarity

        return None

    def save_article(self, article: Article) -> bool:
        if self.article_exists(article):
            return False

        normalized = normalize_title(article.title)
        similar = self.find_similar(article)

        with sqlite3.connect(self.db_path) as conn:
            if similar:
                original_id, similarity = similar
                conn.execute(
                    """INSERT INTO articles (id, title, normalized_title, url, source, timestamp, content, duplicate_of, sent)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, TRUE)""",
                    (article.id, article.title, normalized, article.url, article.source,
                     article.timestamp.isoformat() if article.timestamp else None, article.content, original_id)
                )
                cursor = conn.execute("SELECT other_sources FROM articles WHERE id = ?", (original_id,))
                row = cursor.fetchone()
                existing_sources = row[0] or "" if row else ""
                new_sources = f"{existing_sources},{article.source}" if existing_sources else article.source
                conn.execute("UPDATE articles SET other_sources = ? WHERE id = ?", (new_sources, original_id))
                logger.debug(f"Duplicate ({similarity}%): '{article.title[:40]}' -> '{original_id[:20]}'")
            else:
                conn.execute(
                    """INSERT INTO articles (id, title, normalized_title, url, source, timestamp, content)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (article.id, article.title, normalized, article.url, article.source,
                     article.timestamp.isoformat() if article.timestamp else None, article.content)
                )
            conn.commit()

        return not similar

    def mark_sent(self, article: Article):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE articles SET sent = TRUE WHERE id = ?", (article.id,))
            conn.commit()

    def get_unsent_articles(self) -> list[Article]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """SELECT * FROM articles
                   WHERE sent = FALSE AND duplicate_of IS NULL
                   ORDER BY timestamp DESC"""
            )
            rows = cursor.fetchall()

        articles = []
        for row in rows:
            article = Article(
                title=row["title"],
                url=row["url"],
                source=row["source"],
                timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else None,
                content=row["content"],
            )
            other_sources = row["other_sources"]
            if other_sources:
                article.other_sources = [s.strip() for s in other_sources.split(",") if s.strip()]
            else:
                article.other_sources = []
            articles.append(article)
        return articles

    def cleanup_old(self, days: int | None = None):
        days = days or settings.storage.keep_days
        cutoff = datetime.now() - timedelta(days=days)
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute("DELETE FROM articles WHERE created_at < ?", (cutoff.isoformat(),))
            conn.commit()
            logger.info(f"Cleaned up {result.rowcount} old articles")

    def get_stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            sent = conn.execute("SELECT COUNT(*) FROM articles WHERE sent = TRUE").fetchone()[0]
            by_source = dict(
                conn.execute("SELECT source, COUNT(*) FROM articles GROUP BY source").fetchall()
            )

        return {"total": total, "sent": sent, "pending": total - sent, "by_source": by_source}
