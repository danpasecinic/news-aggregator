import asyncio
import logging

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from news_aggregator.config import settings
from news_aggregator.scrapers.base import Article

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self):
        self.token = settings.telegram_bot_token
        self.channel_id = settings.telegram_channel_id
        self.message_format = settings.telegram.message_format

    def _get_bot(self) -> Bot:
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set")
        return Bot(token=self.token)

    def format_message(self, article: Article) -> str:
        timestamp_str = article.timestamp.strftime("%H:%M %d.%m.%Y") if article.timestamp else ""

        return self.message_format.format(
            source=self._escape_md(article.source),
            title=self._escape_md(article.title),
            url=article.url,
            timestamp=timestamp_str,
        )

    def _escape_md(self, text: str) -> str:
        special_chars = [
            "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"
        ]
        for char in special_chars:
            text = text.replace(char, f"\\{char}")
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
                    disable_web_page_preview=False,
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
                    disable_web_page_preview=False,
                )
            return True
        except TelegramError as e:
            logger.error(f"Fallback also failed: {e}")
            return False

    async def send_batch(self, articles: list[Article], delay: float = 1.0) -> int:
        sent_count = 0
        for article in articles:
            if await self.send_article(article):
                sent_count += 1
            await asyncio.sleep(delay)
        return sent_count
