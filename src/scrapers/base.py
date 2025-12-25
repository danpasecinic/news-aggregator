from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import hashlib


@dataclass
class Article:
    title: str
    url: str
    source: str
    timestamp: Optional[datetime] = None
    content: Optional[str] = None

    @property
    def id(self) -> str:
        return hashlib.md5(self.url.encode()).hexdigest()

    def matches_keywords(self, keywords: list[str]) -> bool:
        if not keywords:
            return True
        text = f"{self.title} {self.content or ''}".lower()
        return any(kw.lower() in text for kw in keywords)


class BaseScraper(ABC):
    def __init__(self, config: dict):
        self.config = config
        self.name = config.get("name", "Unknown")
        self.keywords = config.get("keywords", [])
        self.enabled = config.get("enabled", True)

    @abstractmethod
    async def scrape(self) -> list[Article]:
        pass

    def filter_articles(self, articles: list[Article]) -> list[Article]:
        if not self.keywords:
            return articles
        return [a for a in articles if a.matches_keywords(self.keywords)]
