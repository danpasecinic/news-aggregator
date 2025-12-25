import asyncio
import os
import logging
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from src.scrapers.base import Article

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, settings: dict):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.channel_id = os.getenv("TELEGRAM_CHANNEL_ID", "")
        self.message_format = settings.get("telegram", {}).get("message_format", "{title}\n{url}")

    def _get_bot(self) -> Bot:
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set")
        return Bot(token=self.token)

    def format_message(self, article: Article) -> str:
        timestamp_str = ""
        if article.timestamp:
            timestamp_str = article.timestamp.strftime("%H:%M %d.%m.%Y")

        return self.message_format.format(
            source=self._escape_md(article.source),
            title=self._escape_md(article.title),
            url=article.url,
            timestamp=timestamp_str
        )

    def _escape_md(self, text: str) -> str:
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text

    async def send_article(self, article: Article) -> bool:
        if not self.channel_id:
            logger.warning("TELEGRAM_CHANNEL_ID not set")
            return False

        try:
            message = self.format_message(article)
            async with self._get_bot() as bot:
                await bot.send_message(
                    chat_id=self.channel_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    disable_web_page_preview=False
                )
            logger.info(f"Sent: {article.title[:50]}...")
            return True

        except TelegramError as e:
            logger.error(f"Failed to send message: {e}")
            return await self._send_fallback(article)

    async def _send_fallback(self, article: Article) -> bool:
        try:
            plain_message = f"📰 {article.source}\n{article.title}\n🔗 {article.url}"
            async with self._get_bot() as bot:
                await bot.send_message(
                    chat_id=self.channel_id,
                    text=plain_message,
                    disable_web_page_preview=False
                )
            return True
        except TelegramError as e:
            logger.error(f"Fallback also failed: {e}")
            return False

    async def send_batch(self, articles: list[Article], delay: float = 1.0) -> int:
        sent_count = 0
        for article in articles:
            success = await self.send_article(article)
            if success:
                sent_count += 1
            await asyncio.sleep(delay)
        return sent_count

    async def send_status(self, stats: dict):
        message = (
            f"📊 *News Aggregator Status*\n\n"
            f"Total articles: {stats['total']}\n"
            f"Sent: {stats['sent']}\n"
            f"Pending: {stats['pending']}\n\n"
            f"By source:\n"
        )
        for source, count in stats.get('by_source', {}).items():
            message += f"  • {source}: {count}\n"

        try:
            async with self._get_bot() as bot:
                await bot.send_message(
                    chat_id=self.channel_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN
                )
        except TelegramError as e:
            logger.error(f"Failed to send status: {e}")
