import asyncio
import logging
import re
from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from deep_translator import GoogleTranslator
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError
from telegram.request import HTTPXRequest

from news_aggregator.config import load_skip_patterns, settings
from news_aggregator.scrapers.base import Article

logger = logging.getLogger(__name__)

KYIV_TZ = ZoneInfo("Europe/Kyiv")
MIN_DELAY = 1.0
MAX_DELAY = 5.0
BATCH_SIZE = 10

SKIP_PATTERNS = load_skip_patterns()


def to_kyiv_time(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KYIV_TZ)


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
        self._bot: Bot | None = None

    def _get_bot(self) -> Bot:
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set")
        if self._bot is None:
            request = HTTPXRequest(
                connect_timeout=30.0,
                read_timeout=30.0,
                write_timeout=30.0,
                pool_timeout=30.0,
            )
            self._bot = Bot(token=self.token, request=request)
        return self._bot

    @staticmethod
    def _should_skip(article: Article) -> bool:
        text = f"{article.title} {article.url}".lower()
        return any(re.search(p, text, re.IGNORECASE) for p in SKIP_PATTERNS)

    def format_message(self, article: Article) -> str:
        time_str = ""
        if article.timestamp:
            kyiv_time = to_kyiv_time(article.timestamp)
            time_str = kyiv_time.strftime("%H:%M")

        title = article.title
        if article.language == "en":
            title = translate_to_ukrainian(title)

        lines = [f"{article.icon} *{self._escape_md(article.source)}*", "", self._escape_md(title), ""]

        if article.other_sources:
            sources_str = ", ".join(article.other_sources[:3])
            lines.append(f"_Також: {self._escape_md(sources_str)}_")
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

        bot = self._get_bot()
        for attempt in range(retries):
            try:
                message = self.format_message(article)
                await bot.send_message(
                    chat_id=self.channel_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    disable_web_page_preview=True,
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
            plain_message = f"{article.icon} {article.source}\n\n{article.title}\n\n🔗 {article.url}"
            await self._get_bot().send_message(
                chat_id=self.channel_id,
                text=plain_message,
                disable_web_page_preview=True,
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
            time_str = ""
            if article.timestamp:
                kyiv_time = to_kyiv_time(article.timestamp)
                time_str = kyiv_time.strftime("%H:%M")
            time_part = f" _{time_str}_" if time_str else ""

            title = article.title[:80]
            if article.language == "en":
                title = translate_to_ukrainian(title)
            title = self._escape_md(title)
            lines.append(f"{article.icon}{time_part}")
            lines.append(f"[{title}]({article.url})\n")

        message = "\n".join(lines)

        try:
            await self._get_bot().send_message(
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
