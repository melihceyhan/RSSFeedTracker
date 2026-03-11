import logging
import asyncio
import re

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Article, Setting, Feed
from app.database import async_session
from app.config import get_settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def escape_markdown_v2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(special)}])", r"\\\1", text)


def format_message(feed_name: str, title: str, summary: str, url: str) -> str:
    safe_feed = escape_markdown_v2(feed_name)
    safe_title = escape_markdown_v2(title)
    safe_summary = escape_markdown_v2(summary)
    return (
        f"*{safe_feed}*\n\n"
        f"*{safe_title}*\n\n"
        f"{safe_summary}\n\n"
        f"[Habere Git]({url})"
    )


async def _get_setting(session: AsyncSession, key: str, default: str) -> str:
    result = await session.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting else default


async def send_to_telegram(token: str, chat_id: str, text: str) -> bool:
    """Send a single message to Telegram."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                TELEGRAM_API.format(token=token),
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "MarkdownV2",
                    "disable_web_page_preview": False,
                },
            )
            if resp.status_code == 200:
                return True
            logger.error(f"Telegram API error: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return False


async def send_unsent_summaries():
    """Send all summarized but unsent articles to Telegram."""
    settings = get_settings()

    async with async_session() as session:
        token = await _get_setting(session, "telegram_bot_token", settings.telegram_bot_token)
        chat_id = await _get_setting(session, "telegram_chat_id", settings.telegram_chat_id)

        if not token or not chat_id:
            logger.warning("Telegram bot token or chat ID not configured")
            return 0

        articles = (await session.execute(
            select(Article)
            .join(Feed)
            .where(Article.summary.isnot(None), Article.is_sent_to_telegram == False)
        )).scalars().all()

        sent_count = 0
        for article in articles:
            feed = await session.get(Feed, article.feed_id)
            feed_name = feed.name if feed else "RSS"

            message = format_message(feed_name, article.title, article.summary, article.url)
            success = await send_to_telegram(token, chat_id, message)

            if success:
                article.is_sent_to_telegram = True
                await session.commit()
                sent_count += 1
                logger.info(f"Sent to Telegram: {article.title[:60]}")
            else:
                logger.error(f"Failed to send: {article.title[:60]}")

            await asyncio.sleep(1)

        logger.info(f"Sent {sent_count}/{len(articles)} articles to Telegram")
        return sent_count
