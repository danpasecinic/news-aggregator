import asyncio
import logging
import sys

from news_aggregator.config import SourceConfig, load_sources, settings
from news_aggregator.output import TelegramBot
from news_aggregator.scrapers import RSSScraper, TwitterScraper, WebScraper, PlaywrightScraper
from news_aggregator.scrapers.base import Article
from news_aggregator.storage import Database

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class NewsAggregator:
    def __init__(self):
        self.sources = load_sources()
        self.db = Database()
        self.telegram = TelegramBot()
        self.scrapers = self._init_scrapers()

    def _init_scrapers(self) -> list:
        scrapers = []
        for source in self.sources:
            scraper = self._create_scraper(source)
            if scraper:
                scrapers.append(scraper)
                logger.info(f"Initialized scraper: {source.name}")
        return scrapers

    @staticmethod
    def _create_scraper(source: SourceConfig):
        match source.type:
            case "web":
                return WebScraper(source)
            case "twitter":
                return TwitterScraper(source)
            case "rss":
                return RSSScraper(source)
            case "playwright":
                return PlaywrightScraper(source)
            case _:
                logger.warning(f"Unknown scraper type: {source.type}")
                return None

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
        self.db.cleanup_old()


async def run_scheduler():
    aggregator = NewsAggregator()
    interval = settings.scrape_interval

    logger.info(f"Starting news aggregator, running every {interval} minutes")

    cycle_count = 0
    while True:
        try:
            await aggregator.run_cycle()
            cycle_count += 1

            if cycle_count % 60 == 0:
                aggregator.cleanup()

        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)

        await asyncio.sleep(interval * 60)


async def run_once():
    aggregator = NewsAggregator()
    await aggregator.run_cycle()


def show_stats():
    db = Database()
    stats = db.get_stats()
    print(f"Total: {stats['total']}")
    print(f"Sent: {stats['sent']}")
    print(f"Pending: {stats['pending']}")
    for source, count in stats.get("by_source", {}).items():
        print(f"  {source}: {count}")


def main():
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "once":
            asyncio.run(run_once())
            return

        if command == "stats":
            show_stats()
            return

        if command == "cleanup":
            db = Database()
            db.cleanup_old()
            return

    try:
        asyncio.run(run_scheduler())
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()
