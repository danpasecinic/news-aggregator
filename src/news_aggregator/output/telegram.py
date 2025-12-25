import asyncio
import logging
import re
from functools import lru_cache
from urllib.parse import urlparse

from deep_translator import GoogleTranslator
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError

from news_aggregator.config import settings
from news_aggregator.scrapers.base import Article

logger = logging.getLogger(__name__)

MIN_DELAY = 1.0
MAX_DELAY = 5.0
BATCH_SIZE = 10

CATEGORY_TAGS = {
    "war": "#війна",
    "ato": "#війна",
    "politics": "#політика",
    "polytics": "#політика",
    "economy": "#економіка",
    "economics": "#економіка",
    "biznes": "#бізнес",
    "business": "#бізнес",
    "sport": "#спорт",
    "culture": "#культура",
    "world": "#світ",
    "ukraine": "#україна",
    "society": "#суспільство",
    "energetika": "#енергетика",
    "infrastruktura": "#інфраструктура",
    "news": "",
    "main": "",
}

SOURCE_ICONS = {
    "RBC Ukraine": "🔴",
    "Pravda": "🟠",
    "Eurointegration": "🇪🇺",
    "ZN.UA": "📰",
    "Ekonomichna Pravda": "💰",
    "Ukrinform ATO": "⚔️",
    "Hromadske": "📺",
    "Radio Svoboda": "🔵",
    "Suspilne": "🟡",
    "Twitter": "𝕏",
    "Bloomberg": "🟧",
    "Reuters": "🔷",
    "BBC": "🇬🇧",
    "The Guardian": "🟣",
    "NYT": "🗽",
    "Washington Post": "🏛️",
    "AP News": "⚡",
    "Al Jazeera": "🌍",
    "Axios": "🔶",
    "CNN": "📺",
    "Politico": "🏛️",
    "NPR": "🎙️",
    "The Economist": "📊",
    "Forbes": "💵",
    "Sky News": "🌤️",
    "DW": "🇩🇪",
    "France24": "🇫🇷",
    "Euronews": "🇪🇺",
}

SKIP_PATTERNS = [
    r"t\.me/",
    r"telegram",
    r"підписуйся",
    r"підписатися",
    r"наш канал",
]

ENGLISH_SOURCES = {
    "Bloomberg", "Reuters", "BBC", "The Guardian", "NYT", "Washington Post",
    "AP News", "Al Jazeera", "Axios", "CNN", "Politico", "NPR", "The Economist",
    "Forbes", "Sky News", "DW", "France24", "Euronews",
}


@lru_cache(maxsize=500)
def translate_to_ukrainian(text: str) -> str:
    try:
        return GoogleTranslator(source="en", target="uk").translate(text)
    except Exception:
        return text


class TelegramBot:
    def __init__(self):
        self.token = settings.telegram_bot_token
        self.channel_id = settings.telegram_channel_id

    def _get_bot(self) -> Bot:
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set")
        return Bot(token=self.token)

    @staticmethod
    def _should_skip(article: Article) -> bool:
        text = f"{article.title} {article.url}".lower()
        return any(re.search(p, text, re.IGNORECASE) for p in SKIP_PATTERNS)

    @staticmethod
    def _extract_category(url: str) -> str:
        try:
            path = urlparse(url).path.lower()
            parts = [p for p in path.split("/") if p and not p.isdigit() and len(p) > 2]

            for part in parts:
                for key, tag in CATEGORY_TAGS.items():
                    if key in part and tag:
                        return tag
        except Exception:
            pass
        return ""

    @staticmethod
    def _get_source_icon(source: str) -> str:
        return SOURCE_ICONS.get(source, "📰")

    def format_message(self, article: Article) -> str:
        icon = self._get_source_icon(article.source)
        category = self._escape_md(self._extract_category(article.url))
        time_str = article.timestamp.strftime("%H:%M") if article.timestamp else ""

        title = article.title
        if article.source in ENGLISH_SOURCES:
            title = translate_to_ukrainian(title)

        lines = [
            f"{icon} *{self._escape_md(article.source)}*",
        ]

        if category:
            lines[0] += f"  {category}"

        lines.append("")
        lines.append(self._escape_md(title))
        lines.append("")

        if time_str:
            lines.append(f"⏰ {time_str} • [Читати]({article.url})")
        else:
            lines.append(f"[Читати →]({article.url})")

        return "\n".join(lines)

    @staticmethod
    def _escape_md(text: str) -> str:
        special_chars = ["_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]
        for char in special_chars:
            text = text.replace(char, f"\\{char}")
        return text

    async def send_article(self, article: Article, retries: int = 3) -> bool:
        if not self.channel_id:
            logger.warning("TELEGRAM_CHANNEL_ID not set")
            return False

        if self._should_skip(article):
            logger.debug(f"Skipping promo article: {article.title[:50]}")
            return True

        for attempt in range(retries):
            try:
                message = self.format_message(article)
                async with self._get_bot() as bot:
                    await bot.send_message(
                        chat_id=self.channel_id,
                        text=message,
                        parse_mode=ParseMode.MARKDOWN_V2,
                        disable_web_page_preview=False,
                    )
                logger.info(f"Sent: {article.title[:50]}...")
                return True

            except RetryAfter as e:
                wait_time = e.retry_after + 1
                logger.warning(f"Flood control: waiting {wait_time}s")
                await asyncio.sleep(wait_time)

            except TelegramError as e:
                logger.error(f"Failed to send message: {e}")
                if attempt == retries - 1:
                    return await self._send_fallback(article)
                await asyncio.sleep(2 ** attempt)

        return False

    async def _send_fallback(self, article: Article) -> bool:
        try:
            icon = self._get_source_icon(article.source)
            category = self._extract_category(article.url)
            tag_str = f" {category}" if category else ""

            plain_message = f"{icon} {article.source}{tag_str}\n\n{article.title}\n\n🔗 {article.url}"
            async with self._get_bot() as bot:
                await bot.send_message(
                    chat_id=self.channel_id,
                    text=plain_message,
                    disable_web_page_preview=False,
                )
            return True
        except TelegramError as e:
            logger.error(f"Fallback also failed: {e}")
            return False

    async def send_batch(self, articles: list[Article]) -> int:
        sent_count = 0
        delay = MIN_DELAY

        for i, article in enumerate(articles):
            success = await self.send_article(article)
            if success:
                sent_count += 1
                delay = max(MIN_DELAY, delay * 0.9)
            else:
                delay = min(MAX_DELAY, delay * 1.5)

            if i < len(articles) - 1:
                if (i + 1) % BATCH_SIZE == 0:
                    logger.info(f"Batch pause after {i + 1} messages")
                    await asyncio.sleep(MAX_DELAY)
                else:
                    await asyncio.sleep(delay)

        return sent_count

    async def send_digest(self, articles: list[Article]) -> bool:
        if not articles:
            return True

        if not self.channel_id:
            return False

        lines = ["📋 *Дайджест новин*\n"]

        for article in articles[:15]:
            icon = self._get_source_icon(article.source)
            category = self._escape_md(self._extract_category(article.url))
            tag = f" {category}" if category else ""
            time_str = article.timestamp.strftime("%H:%M") if article.timestamp else ""
            time_part = f" _{time_str}_" if time_str else ""

            title = article.title[:80]
            if article.source in ENGLISH_SOURCES:
                title = translate_to_ukrainian(title)
            title = self._escape_md(title)
            lines.append(f"{icon}{tag}{time_part}")
            lines.append(f"[{title}]({article.url})\n")

        message = "\n".join(lines)

        try:
            async with self._get_bot() as bot:
                await bot.send_message(
                    chat_id=self.channel_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    disable_web_page_preview=True,
                )
            logger.info(f"Sent digest with {len(articles)} articles")
            return True
        except TelegramError as e:
            logger.error(f"Digest send failed: {e}")
            return False
