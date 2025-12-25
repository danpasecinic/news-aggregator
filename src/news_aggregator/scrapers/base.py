from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
import hashlib

from news_aggregator.config import SourceConfig, settings


@dataclass
class Article:
    title: str
    url: str
    source: str
    timestamp: datetime | None = None
    content: str | None = None

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
        if not self.keywords:
            return articles
        return [a for a in articles if a.matches_keywords(self.keywords)]
