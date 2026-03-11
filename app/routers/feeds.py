from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.models import Feed, Article
from app.schemas import FeedCreate, FeedOut

router = APIRouter(prefix="/api/feeds", tags=["feeds"])


@router.get("", response_model=list[FeedOut])
async def list_feeds(db: AsyncSession = Depends(get_db)):
    feeds = (await db.execute(select(Feed).order_by(Feed.created_at.desc()))).scalars().all()
    result = []
    for f in feeds:
        article_count = (await db.execute(
            select(func.count(Article.id)).where(Article.feed_id == f.id, Article.date == date.today())
        )).scalar() or 0
        sent_count = (await db.execute(
            select(func.count(Article.id)).where(
                Article.feed_id == f.id, Article.date == date.today(), Article.is_sent_to_telegram == True
            )
        )).scalar() or 0
        result.append(FeedOut(
            id=f.id, name=f.name, url=f.url, category=f.category,
            is_active=f.is_active, created_at=f.created_at,
            article_count=article_count, sent_count=sent_count,
        ))
    return result


@router.post("", response_model=FeedOut, status_code=201)
async def create_feed(feed: FeedCreate, db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(select(Feed).where(Feed.url == feed.url))).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "Bu URL zaten kayıtlı")
    new_feed = Feed(name=feed.name, url=feed.url, category=feed.category)
    db.add(new_feed)
    await db.commit()
    await db.refresh(new_feed)
    return FeedOut(
        id=new_feed.id, name=new_feed.name, url=new_feed.url,
        category=new_feed.category, is_active=new_feed.is_active,
        created_at=new_feed.created_at,
    )


@router.put("/{feed_id}/toggle")
async def toggle_feed(feed_id: int, db: AsyncSession = Depends(get_db)):
    feed = await db.get(Feed, feed_id)
    if not feed:
        raise HTTPException(404, "Feed bulunamadı")
    feed.is_active = not feed.is_active
    await db.commit()
    return {"id": feed.id, "is_active": feed.is_active}


@router.delete("/{feed_id}")
async def delete_feed(feed_id: int, db: AsyncSession = Depends(get_db)):
    feed = await db.get(Feed, feed_id)
    if not feed:
        raise HTTPException(404, "Feed bulunamadı")
    await db.delete(feed)
    await db.commit()
    return {"ok": True}


@router.post("/{feed_id}/fetch")
async def fetch_single_feed_now(feed_id: int, db: AsyncSession = Depends(get_db)):
    """Tek bir feed'i manuel olarak çek, özetle ve Telegram'a gönder."""
    from app.services.feed_fetcher import fetch_single_feed
    from app.services.summarizer import summarize_article
    from app.services.telegram_sender import send_unsent_summaries

    feed = await db.get(Feed, feed_id)
    if not feed:
        raise HTTPException(404, "Feed bulunamadı")

    new_articles = await fetch_single_feed(feed, db)

    summarized = 0
    for article in new_articles:
        if await summarize_article(article, db):
            summarized += 1

    sent = await send_unsent_summaries()

    return {
        "feed": feed.name,
        "fetched": len(new_articles),
        "summarized": summarized,
        "sent": sent,
    }
