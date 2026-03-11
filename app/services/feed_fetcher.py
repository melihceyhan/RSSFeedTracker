import logging
from datetime import datetime, date, timezone
from dateutil import parser as dateparser

import feedparser
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Feed, Article
from app.database import async_session

logger = logging.getLogger(__name__)


def clean_html(raw_html: str | None) -> str:
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def parse_date(entry) -> datetime | None:
    for field in ("published_parsed", "updated_parsed"):
        tp = getattr(entry, field, None)
        if tp:
            try:
                return datetime(*tp[:6])
            except Exception:
                pass
    for field in ("published", "updated"):
        val = getattr(entry, field, None)
        if val:
            try:
                return dateparser.parse(val)
            except Exception:
                pass
    return None


def is_today(dt: datetime | None) -> bool:
    if dt is None:
        return True
    return dt.date() == date.today()


async def fetch_feed_content(url: str) -> str | None:
    """Fetch full article content from URL for better summarization."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "RSSFeedTracker/1.0"})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
                tag.decompose()
            article = soup.find("article") or soup.find("main") or soup.find("body")
            if article:
                return article.get_text(separator=" ", strip=True)[:5000]
            return soup.get_text(separator=" ", strip=True)[:5000]
    except Exception as e:
        logger.warning(f"Could not fetch article content from {url}: {e}")
        return None


async def fetch_single_feed(feed: Feed, session: AsyncSession) -> list[Article]:
    """Fetch and store new articles from a single RSS feed."""
    new_articles = []
    try:
        parsed = feedparser.parse(feed.url)
        if parsed.bozo and not parsed.entries:
            logger.error(f"Feed parse error for {feed.name}: {parsed.bozo_exception}")
            return []

        existing_urls = set(
            (await session.execute(
                select(Article.url).where(
                    Article.feed_id == feed.id,
                    Article.date == date.today()
                )
            )).scalars().all()
        )

        for entry in parsed.entries:
            url = getattr(entry, "link", None)
            if not url or url in existing_urls:
                continue

            published_at = parse_date(entry)
            if not is_today(published_at):
                continue

            title = getattr(entry, "title", "Başlıksız")
            raw_content = ""
            if hasattr(entry, "content") and entry.content:
                raw_content = entry.content[0].get("value", "")
            elif hasattr(entry, "summary"):
                raw_content = entry.summary or ""

            content = clean_html(raw_content)
            if len(content) < 100:
                full_content = await fetch_feed_content(url)
                if full_content and len(full_content) > len(content):
                    content = full_content

            article = Article(
                feed_id=feed.id,
                title=title,
                url=url,
                content=content[:5000] if content else None,
                published_at=published_at,
                date=date.today(),
            )
            session.add(article)
            new_articles.append(article)
            existing_urls.add(url)

        await session.commit()
        logger.info(f"Feed '{feed.name}': {len(new_articles)} new articles fetched")

    except Exception as e:
        logger.error(f"Error fetching feed '{feed.name}': {e}")
        await session.rollback()

    return new_articles


async def fetch_all_feeds() -> list[Article]:
    """Fetch articles from all active feeds."""
    all_new = []
    async with async_session() as session:
        feeds = (await session.execute(
            select(Feed).where(Feed.is_active == True)
        )).scalars().all()

        for feed in feeds:
            articles = await fetch_single_feed(feed, session)
            all_new.extend(articles)

    logger.info(f"Total new articles fetched: {len(all_new)}")
    return all_new
