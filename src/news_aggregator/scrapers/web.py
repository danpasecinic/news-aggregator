import logging
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from news_aggregator.config import SourceConfig, settings
from news_aggregator.scrapers.base import Article, BaseScraper

logger = logging.getLogger(__name__)


class WebScraper(BaseScraper):
    def __init__(self, source: SourceConfig):
        super().__init__(source)
        self.url = source.url or ""
        self.selectors = source.selectors
        self.link_prefix = source.link_prefix

    async def scrape(self) -> list[Article]:
        if not self.url or not self.selectors:
            return []

        try:
            async with httpx.AsyncClient(timeout=settings.scraping.request_timeout) as client:
                response = await client.get(
                    self.url,
                    headers={"User-Agent": settings.scraping.user_agent},
                    follow_redirects=True,
                )
                response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")
            articles = self._parse_articles(soup)
            filtered = self.filter_articles(articles)

            logger.info(f"[{self.name}] Found {len(articles)} articles, {len(filtered)} after filtering")
            return filtered[: self.max_articles]

        except Exception as e:
            logger.error(f"[{self.name}] Scraping failed: {e}")
            return []

    def _parse_articles(self, soup: BeautifulSoup) -> list[Article]:
        articles = []
        if not self.selectors:
            return articles

        containers = soup.select(self.selectors.container)

        for container in containers:
            try:
                article = self._parse_single_article(container)
                if article:
                    articles.append(article)
            except Exception as e:
                logger.debug(f"[{self.name}] Failed to parse article: {e}")

        return articles

    def _parse_single_article(self, container) -> Article | None:
        if not self.selectors:
            return None

        if self.selectors.title:
            title_elem = container.select_one(self.selectors.title)
        else:
            title_elem = container

        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        if self.selectors.time:
            time_elem = container.select_one(self.selectors.time)
            if time_elem:
                time_text = time_elem.get_text(strip=True)
                title = title.replace(time_text, "").strip()

        if not title:
            return None

        if self.selectors.link:
            link_elem = container.select_one(self.selectors.link)
        else:
            link_elem = container if container.name == "a" else container.find("a")

        href = link_elem.get("href") if link_elem else None
        if not href:
            return None

        url = urljoin(self.link_prefix or self.url, href)

        timestamp = None
        if self.selectors.time:
            time_elem = container.select_one(self.selectors.time)
            if time_elem:
                time_text = time_elem.get_text(strip=True)
                timestamp = self._parse_time(time_text)

        return Article(
            title=title,
            url=url,
            source=self.name,
            timestamp=timestamp,
            icon=self.source.icon,
            language=self.source.language,
        )

    def _parse_time(self, time_str: str) -> datetime | None:
        formats = ["%H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M", "%d %B %Y, %H:%M"]
        now = datetime.now()
        for fmt in formats:
            try:
                parsed = datetime.strptime(time_str, fmt)
                if parsed.year == 1900:
                    parsed = parsed.replace(year=now.year, month=now.month, day=now.day)
                return parsed
            except ValueError:
                continue
        return None
