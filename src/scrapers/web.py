import httpx
from bs4 import BeautifulSoup
from datetime import datetime
import logging
from urllib.parse import urljoin

from .base import BaseScraper, Article

logger = logging.getLogger(__name__)


class WebScraper(BaseScraper):
    def __init__(self, config: dict, settings: dict):
        super().__init__(config)
        self.url = config["url"]
        self.selectors = config.get("selectors", {})
        self.link_prefix = config.get("link_prefix", "")
        self.timeout = settings.get("scraping", {}).get("request_timeout", 30)
        self.user_agent = settings.get("scraping", {}).get(
            "user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self.max_articles = settings.get("scraping", {}).get("max_articles_per_source", 20)

    async def scrape(self) -> list[Article]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    self.url,
                    headers={"User-Agent": self.user_agent},
                    follow_redirects=True
                )
                response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")
            articles = self._parse_articles(soup)
            filtered = self.filter_articles(articles)

            logger.info(f"[{self.name}] Found {len(articles)} articles, {len(filtered)} after filtering")
            return filtered[:self.max_articles]

        except Exception as e:
            logger.error(f"[{self.name}] Scraping failed: {e}")
            return []

    def _parse_articles(self, soup: BeautifulSoup) -> list[Article]:
        articles = []
        container_selector = self.selectors.get("container")

        if not container_selector:
            return articles

        containers = soup.select(container_selector)

        for container in containers:
            try:
                article = self._parse_single_article(container)
                if article:
                    articles.append(article)
            except Exception as e:
                logger.debug(f"[{self.name}] Failed to parse article: {e}")
                continue

        return articles

    def _parse_single_article(self, container) -> Article | None:
        title_sel = self.selectors.get("title")
        link_sel = self.selectors.get("link")
        time_sel = self.selectors.get("time")

        title_elem = container.select_one(title_sel) if title_sel else container
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        if not title:
            return None

        link_elem = container.select_one(link_sel) if link_sel else title_elem
        href = link_elem.get("href") if link_elem else None
        if not href:
            return None

        url = urljoin(self.link_prefix or self.url, href)

        timestamp = None
        if time_sel:
            time_elem = container.select_one(time_sel)
            if time_elem:
                time_text = time_elem.get_text(strip=True)
                timestamp = self._parse_time(time_text)

        return Article(
            title=title,
            url=url,
            source=self.name,
            timestamp=timestamp or datetime.now()
        )

    def _parse_time(self, time_str: str) -> datetime | None:
        formats = [
            "%H:%M",
            "%d.%m.%Y %H:%M",
            "%Y-%m-%d %H:%M",
            "%d %B %Y, %H:%M",
        ]
        for fmt in formats:
            try:
                parsed = datetime.strptime(time_str, fmt)
                if parsed.year == 1900:
                    parsed = parsed.replace(year=datetime.now().year)
                return parsed
            except ValueError:
                continue
        return None
