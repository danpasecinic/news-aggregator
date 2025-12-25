import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from playwright.async_api import Page, async_playwright

from news_aggregator.config import SourceConfig, settings
from news_aggregator.scrapers.base import Article, BaseScraper

logger = logging.getLogger(__name__)

COOKIES_PATH = Path("data/twitter_cookies.json")


class TwitterScraper(BaseScraper):
    def __init__(self, source: SourceConfig):
        super().__init__(source)
        self.username = settings.twitter_username
        self.password = settings.twitter_password

    async def scrape(self) -> list[Article]:
        if not self.username or not self.password:
            logger.warning("[Twitter] Credentials not set, skipping")
            return []

        articles = []
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent=settings.scraping.user_agent,
                )

                if COOKIES_PATH.exists():
                    cookies = json.loads(COOKIES_PATH.read_text())
                    await context.add_cookies(cookies)

                page = await context.new_page()
                logged_in = await self._ensure_logged_in(page)

                if logged_in:
                    articles = await self._scrape_feed(page)
                    cookies = await context.cookies()
                    COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
                    COOKIES_PATH.write_text(json.dumps(cookies))

                await browser.close()

        except Exception as e:
            logger.error(f"[Twitter] Scraping failed: {e}")

        filtered = self.filter_articles(articles)
        logger.info(f"[Twitter] Found {len(articles)} tweets, {len(filtered)} after filtering")
        return filtered[: self.max_articles]

    async def _ensure_logged_in(self, page: Page) -> bool:
        try:
            await page.goto("https://twitter.com/home", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            if "login" in page.url.lower():
                return await self._login(page)

            return True

        except Exception as e:
            logger.error(f"[Twitter] Login check failed: {e}")
            return False

    async def _login(self, page: Page) -> bool:
        try:
            logger.info("[Twitter] Attempting login...")

            await page.goto("https://twitter.com/i/flow/login", wait_until="networkidle")
            await asyncio.sleep(2)

            username_input = page.get_by_label("Phone, email, or username")
            if await username_input.count() == 0:
                username_input = page.locator('input[autocomplete="username"]')
            await username_input.fill(self.username)
            await page.keyboard.press("Enter")
            await asyncio.sleep(2)

            password_input = page.get_by_label("Password")
            if await password_input.count() == 0:
                password_input = page.locator('input[type="password"]')
            await password_input.fill(self.password)
            await page.keyboard.press("Enter")
            await asyncio.sleep(5)

            if "home" in page.url.lower():
                logger.info("[Twitter] Login successful")
                return True

            logger.warning("[Twitter] Login may have failed, checking...")
            return "login" not in page.url.lower()

        except Exception as e:
            logger.error(f"[Twitter] Login failed: {e}")
            return False

    async def _scrape_feed(self, page: Page) -> list[Article]:
        articles = []

        try:
            await page.goto("https://twitter.com/home", wait_until="networkidle")
            await asyncio.sleep(3)

            for _ in range(3):
                await page.evaluate("window.scrollBy(0, 800)")
                await asyncio.sleep(1)

            tweets = page.get_by_test_id("tweet")
            tweet_elements = await tweets.all()

            for tweet in tweet_elements[: self.max_articles * 2]:
                try:
                    article = await self._parse_tweet(tweet)
                    if article:
                        articles.append(article)
                except Exception as e:
                    logger.debug(f"[Twitter] Failed to parse tweet: {e}")

        except Exception as e:
            logger.error(f"[Twitter] Feed scraping failed: {e}")

        return articles

    async def _parse_tweet(self, tweet) -> Article | None:
        text_locator = tweet.get_by_test_id("tweetText")
        text = ""
        if await text_locator.count() > 0:
            text = await text_locator.first.inner_text()

        link_locator = tweet.locator('a[href*="/status/"]').first
        if await link_locator.count() == 0:
            return None

        href = await link_locator.get_attribute("href")
        url = f"https://twitter.com{href}" if href and not href.startswith("http") else href

        user_locator = tweet.get_by_test_id("User-Name")
        user_text = ""
        if await user_locator.count() > 0:
            user_text = await user_locator.first.inner_text()
        username = user_text.split("\n")[0] if user_text else "Unknown"

        time_locator = tweet.locator("time")
        timestamp = None
        if await time_locator.count() > 0:
            datetime_attr = await time_locator.first.get_attribute("datetime")
            if datetime_attr:
                try:
                    timestamp = datetime.fromisoformat(datetime_attr.replace("Z", "+00:00"))
                except Exception:
                    pass

        title = text[:200] + "..." if len(text) > 200 else text

        return Article(
            title=f"@{username}: {title}",
            url=url or "",
            source="Twitter",
            timestamp=timestamp,
            content=text,
        )
