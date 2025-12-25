import re
import logging
from typing import Optional

from src.scrapers.base import Article

logger = logging.getLogger(__name__)


class KeywordFilter:
    def __init__(self, config: Optional[dict] = None):
        self.global_keywords: list[str] = []
        self.source_keywords: dict[str, list[str]] = {}
        self.exclude_keywords: list[str] = []

        if config:
            self.global_keywords = config.get("global_keywords", [])
            self.exclude_keywords = config.get("exclude_keywords", [])
            self.source_keywords = config.get("source_keywords", {})

    def matches(self, article: Article) -> bool:
        text = f"{article.title} {article.content or ''}".lower()

        for exclude in self.exclude_keywords:
            if exclude.lower() in text:
                logger.debug(f"Excluded article due to keyword: {exclude}")
                return False

        source_kw = self.source_keywords.get(article.source, [])
        if source_kw:
            return any(kw.lower() in text for kw in source_kw)

        if self.global_keywords:
            return any(kw.lower() in text for kw in self.global_keywords)

        return True

    def filter_articles(self, articles: list[Article]) -> list[Article]:
        filtered = [a for a in articles if self.matches(a)]
        logger.info(f"Filtered {len(articles)} -> {len(filtered)} articles")
        return filtered

    def add_source_keywords(self, source: str, keywords: list[str]):
        self.source_keywords[source] = keywords

    def add_global_keywords(self, keywords: list[str]):
        self.global_keywords.extend(keywords)

    def add_exclude_keywords(self, keywords: list[str]):
        self.exclude_keywords.extend(keywords)


def matches_pattern(text: str, pattern: str) -> bool:
    try:
        return bool(re.search(pattern, text, re.IGNORECASE))
    except re.error:
        return pattern.lower() in text.lower()
