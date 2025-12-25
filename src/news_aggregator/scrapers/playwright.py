import asyncio
import logging
from datetime import datetime
from urllib.parse import urljoin

from playwright.async_api import async_playwright

from news_aggregator.config import SourceConfig, settings
from news_aggregator.scrapers.base import Article, BaseScraper

logger = logging.getLogger(__name__)


class PlaywrightScraper(BaseScraper):
    def __init__(self, source: SourceConfig):
        super().__init__(source)
        self.url = source.url or ""
        self.selectors = source.selectors
        self.link_prefix = source.link_prefix

    async def scrape(self) -> list[Article]:
        if not self.url or not self.selectors:
            return []

        articles = []
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent=settings.scraping.user_agent,
                )

                page = await context.new_page()
                await page.goto(self.url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)

                containers = await page.query_selector_all(self.selectors.container)


                for container in containers[:self.max_articles * 2]:
                    try:
                        article = await self._parse_article(container)
                        if article:
                            articles.append(article)
                    except Exception as e:
                        logger.debug(f"[{self.name}] Failed to parse article: {e}")

                await browser.close()

        except Exception as e:
            logger.error(f"[{self.name}] Playwright scraping failed: {e}")

        filtered = self.filter_articles(articles)
        logger.info(f"[{self.name}] Found {len(articles)} articles, {len(filtered)} after filtering")
        return filtered[:self.max_articles]

    async def _parse_article(self, container) -> Article | None:
        if not self.selectors:
            return None

        if self.selectors.title:
            title_elem = await container.query_selector(self.selectors.title)
        else:
            title_elem = container

        if not title_elem:
            return None

        title = await title_elem.inner_text()
        title = title.strip()

        if not title:
            return None

        if self.selectors.link:
            link_elem = await container.query_selector(self.selectors.link)
        else:
            tag = await container.evaluate("el => el.tagName.toLowerCase()")
            if tag == "a":
                link_elem = container
            else:
                link_elem = await container.query_selector("a")

        href = await link_elem.get_attribute("href") if link_elem else None
        if not href:
            return None

        url = urljoin(self.link_prefix or self.url, href)

        timestamp = None
        if self.selectors.time:
            time_elem = await container.query_selector(self.selectors.time)
            if time_elem:
                time_text = await time_elem.inner_text()
                timestamp = self._parse_time(time_text.strip())

        return Article(
            title=title,
            url=url,
            source=self.name,
            timestamp=timestamp or datetime.now(),
        )

    @staticmethod
    def _parse_time(time_str: str) -> datetime | None:
        formats = ["%H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M", "%d %B %Y, %H:%M", "%d.%m.%Y"]
        for fmt in formats:
            try:
                parsed = datetime.strptime(time_str, fmt)
                if parsed.year == 1900:
                    parsed = parsed.replace(year=datetime.now().year)
                return parsed
            except ValueError:
                continue
        return None
