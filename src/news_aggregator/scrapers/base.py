from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib

from news_aggregator.config import SourceConfig, settings


@dataclass
class Article:
    title: str
    url: str
    source: str
    timestamp: datetime | None = None
    content: str | None = None
    other_sources: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return hashlib.md5(self.url.encode()).hexdigest()

    def matches_keywords(self, keywords: list[str]) -> bool:
        if not keywords:
            return True
        text = f"{self.title} {self.content or ''}".lower()
        return any(kw.lower() in text for kw in keywords)


class BaseScraper(ABC):
    def __init__(self, source: SourceConfig):
        self.source = source
        self.name = source.name
        self.keywords = source.keywords
        self.max_articles = settings.scraping.max_articles_per_source

    @abstractmethod
    async def scrape(self) -> list[Article]:
        pass

    def filter_articles(self, articles: list[Article]) -> list[Article]:
        max_age = timedelta(hours=settings.scraping.max_article_age_hours)
        cutoff_utc = datetime.now(timezone.utc) - max_age
        cutoff_naive = datetime.now() - max_age

        filtered = []
        for a in articles:
            if a.timestamp:
                if a.timestamp.tzinfo is not None:
                    if a.timestamp < cutoff_utc:
                        continue
                elif a.timestamp < cutoff_naive:
                    continue
            if self.keywords and not a.matches_keywords(self.keywords):
                continue
            filtered.append(a)

        return filtered
