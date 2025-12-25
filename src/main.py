import asyncio
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from apscheduler import AsyncScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from src.scrapers import WebScraper, TwitterScraper, RSSScraper, Article
from src.storage import Database
from src.output import TelegramBot

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class NewsAggregator:
    def __init__(self):
        self.settings = self._load_yaml("config/settings.yaml")
        self.sources = self._load_yaml("config/sources.yaml")
        self.db = Database(self.settings.get("storage", {}).get("database_path", "data/news.db"))
        self.telegram = TelegramBot(self.settings)
        self.scrapers = self._init_scrapers()

    @staticmethod
    def _load_yaml(path: str) -> dict:
        config_path = Path(path)
        if not config_path.exists():
            logger.warning(f"Config file not found: {path}")
            return {}
        with open(config_path) as f:
            return yaml.safe_load(f) or {}

    def _init_scrapers(self) -> list:
        scrapers = []
        for source in self.sources.get("sources", []):
            if not source.get("enabled", True):
                continue

            source_type = source.get("type", "web")

            if source_type == "web":
                scrapers.append(WebScraper(source, self.settings))
            elif source_type == "twitter":
                scrapers.append(TwitterScraper(source, self.settings))
            elif source_type == "rss":
                scrapers.append(RSSScraper(source, self.settings))

            logger.info(f"Initialized scraper: {source.get('name')}")

        return scrapers

    async def scrape_all(self) -> list[Article]:
        all_articles = []
        tasks = [scraper.scrape() for scraper in self.scrapers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for scraper, result in zip(self.scrapers, results):
            if isinstance(result, Exception):
                logger.error(f"Scraper {scraper.name} failed: {result}")
                continue
            all_articles.extend(result)

        return all_articles

    async def process_articles(self, articles: list[Article]) -> int:
        new_count = 0
        for article in articles:
            if self.db.save_article(article):
                new_count += 1
        logger.info(f"Saved {new_count} new articles")
        return new_count

    async def send_pending(self) -> int:
        unsent = self.db.get_unsent_articles()
        if not unsent:
            return 0

        logger.info(f"Sending {len(unsent)} pending articles")
        sent = 0
        for article in unsent:
            if await self.telegram.send_article(article):
                self.db.mark_sent(article)
                sent += 1
            await asyncio.sleep(1)

        return sent

    async def run_cycle(self):
        logger.info("Starting scrape cycle...")
        try:
            articles = await self.scrape_all()
            new_count = await self.process_articles(articles)
            sent_count = await self.send_pending()
            logger.info(f"Cycle complete: {len(articles)} scraped, {new_count} new, {sent_count} sent")
        except Exception as e:
            logger.error(f"Cycle failed: {e}", exc_info=True)

    def cleanup(self):
        keep_days = self.settings.get("storage", {}).get("keep_days", 7)
        self.db.cleanup_old(keep_days)


async def main():
    aggregator = NewsAggregator()

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "once":
            await aggregator.run_cycle()
            return

        if command == "stats":
            stats = aggregator.db.get_stats()
            print(f"Total: {stats['total']}")
            print(f"Sent: {stats['sent']}")
            print(f"Pending: {stats['pending']}")
            for source, count in stats.get('by_source', {}).items():
                print(f"  {source}: {count}")
            return

        if command == "cleanup":
            aggregator.cleanup()
            return

    interval = int(os.getenv("SCRAPE_INTERVAL", "10"))

    async with AsyncScheduler() as scheduler:
        await scheduler.add_schedule(
            aggregator.run_cycle,
            IntervalTrigger(minutes=interval),
            id="scrape_cycle"
        )

        await scheduler.add_schedule(
            aggregator.cleanup,
            CronTrigger(hour=3),
            id="cleanup"
        )

        logger.info(f"Scheduler started, running every {interval} minutes")

        await aggregator.run_cycle()

        await scheduler.run_until_stopped()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
