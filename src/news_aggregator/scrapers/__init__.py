from news_aggregator.scrapers.base import BaseScraper, Article
from news_aggregator.scrapers.web import WebScraper
from news_aggregator.scrapers.twitter import TwitterScraper
from news_aggregator.scrapers.rss import RSSScraper

__all__ = ["BaseScraper", "Article", "WebScraper", "TwitterScraper", "RSSScraper"]
