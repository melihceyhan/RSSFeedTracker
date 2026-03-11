from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Article, Feed
from app.schemas import ArticleOut

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("", response_model=list[ArticleOut])
async def list_today_articles(db: AsyncSession = Depends(get_db)):
    articles = (await db.execute(
        select(Article).where(Article.date == date.today()).order_by(Article.fetched_at.desc())
    )).scalars().all()

    result = []
    for a in articles:
        feed = await db.get(Feed, a.feed_id)
        result.append(ArticleOut(
            id=a.id, feed_id=a.feed_id, feed_name=feed.name if feed else "",
            title=a.title, url=a.url, content=a.content,
            published_at=a.published_at, fetched_at=a.fetched_at,
            date=a.date, summary=a.summary, model_used=a.model_used,
            is_sent_to_telegram=a.is_sent_to_telegram,
        ))
    return result


@router.post("/{article_id}/summarize")
async def summarize_single_article(article_id: int, db: AsyncSession = Depends(get_db)):
    """Tek bir makaleyi özetle (tekrar özetleme dahil)."""
    from app.services.summarizer import summarize_article

    article = await db.get(Article, article_id)
    if not article:
        raise HTTPException(404, "Makale bulunamadı")

    article.summary = None
    article.model_used = None
    await db.commit()

    success = await summarize_article(article, db)
    if not success:
        raise HTTPException(500, "Özetleme başarısız oldu")

    return {"id": article.id, "summary": article.summary, "model_used": article.model_used}


@router.post("/{article_id}/send")
async def send_single_article(article_id: int, db: AsyncSession = Depends(get_db)):
    """Tek bir makaleyi Telegram'a gönder."""
    import asyncio
    from app.services.telegram_sender import send_to_telegram, format_message, _get_setting
    from app.config import get_settings

    article = await db.get(Article, article_id)
    if not article:
        raise HTTPException(404, "Makale bulunamadı")

    if not article.summary:
        raise HTTPException(400, "Makale henüz özetlenmemiş")

    settings = get_settings()
    token = await _get_setting(db, "telegram_bot_token", settings.telegram_bot_token)
    chat_id = await _get_setting(db, "telegram_chat_id", settings.telegram_chat_id)

    if not token or not chat_id:
        raise HTTPException(400, "Telegram ayarları yapılmamış")

    feed = await db.get(Feed, article.feed_id)
    feed_name = feed.name if feed else "RSS"
    message = format_message(feed_name, article.title, article.summary, article.url)

    success = await send_to_telegram(token, chat_id, message)
    if success:
        article.is_sent_to_telegram = True
        await db.commit()
        return {"ok": True, "message": "Telegram'a gönderildi"}
    else:
        raise HTTPException(500, "Telegram gönderimi başarısız")
