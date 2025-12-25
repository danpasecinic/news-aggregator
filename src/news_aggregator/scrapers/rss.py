import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from news_aggregator.config import SourceConfig, settings
from news_aggregator.scrapers.base import Article, BaseScraper

logger = logging.getLogger(__name__)


class RSSScraper(BaseScraper):
    def __init__(self, source: SourceConfig):
        super().__init__(source)
        self.url = source.url or ""

    async def scrape(self) -> list[Article]:
        if not self.url:
            return []

        try:
            async with httpx.AsyncClient(timeout=settings.scraping.request_timeout) as client:
                response = await client.get(
                    self.url,
                    headers={"User-Agent": settings.scraping.user_agent},
                    follow_redirects=True,
                )
                response.raise_for_status()

            articles = self._parse_feed(response.text)
            filtered = self.filter_articles(articles)

            logger.info(f"[{self.name}] Found {len(articles)} articles, {len(filtered)} after filtering")
            return filtered[: self.max_articles]

        except Exception as e:
            logger.error(f"[{self.name}] RSS fetch failed: {e}")
            return []

    def _parse_feed(self, xml_content: str) -> list[Article]:
        articles = []
        try:
            root = ElementTree.fromstring(xml_content)
        except ElementTree.ParseError as e:
            logger.error(f"[{self.name}] Failed to parse RSS: {e}")
            return articles

        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for item in root.findall(".//item"):
            article = self._parse_rss_item(item)
            if article:
                articles.append(article)

        for entry in root.findall(".//atom:entry", ns):
            article = self._parse_atom_entry(entry, ns)
            if article:
                articles.append(article)

        return articles

    def _parse_rss_item(self, item) -> Article | None:
        title_elem = item.find("title")
        link_elem = item.find("link")
        pub_date_elem = item.find("pubDate")
        desc_elem = item.find("description")

        if title_elem is None or link_elem is None:
            return None

        timestamp = None
        if pub_date_elem is not None and pub_date_elem.text:
            try:
                timestamp = parsedate_to_datetime(pub_date_elem.text)
            except Exception:
                pass

        return Article(
            title=title_elem.text or "",
            url=link_elem.text or "",
            source=self.name,
            timestamp=timestamp,
            content=desc_elem.text if desc_elem is not None else None,
        )

    def _parse_atom_entry(self, entry, ns: dict) -> Article | None:
        title_elem = entry.find("atom:title", ns)
        link_elem = entry.find("atom:link", ns)
        updated_elem = entry.find("atom:updated", ns)
        summary_elem = entry.find("atom:summary", ns)

        if title_elem is None or link_elem is None:
            return None

        href = link_elem.get("href", "")

        timestamp = None
        if updated_elem is not None and updated_elem.text:
            try:
                timestamp = datetime.fromisoformat(updated_elem.text.replace("Z", "+00:00"))
            except Exception:
                pass

        return Article(
            title=title_elem.text or "",
            url=href,
            source=self.name,
            timestamp=timestamp,
            content=summary_elem.text if summary_elem is not None else None,
        )
