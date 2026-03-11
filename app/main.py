import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func

from app.database import init_db, async_session
from app.models import Feed, Article, Setting
from app.config import get_settings
from app.routers import feeds, articles, settings as settings_router
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.feed_fetcher import fetch_all_feeds
from app.services.summarizer import summarize_unsummarized
from app.services.telegram_sender import send_unsent_summaries

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler()
    logger.info("RSS Feed Tracker started")
    yield
    stop_scheduler()
    logger.info("RSS Feed Tracker stopped")


app = FastAPI(title="RSS Feed Tracker", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(feeds.router)
app.include_router(articles.router)
app.include_router(settings_router.router)


async def _get_settings_dict() -> dict:
    defaults = get_settings()
    result = {}
    keys = [
        "ai_provider", "ai_model", "ollama_base_url", "openai_api_key",
        "telegram_bot_token", "telegram_chat_id", "fetch_interval_minutes",
        "daily_cleanup_hour",
    ]
    async with async_session() as session:
        for key in keys:
            row = (await session.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
            result[key] = row.value if row else str(getattr(defaults, key, ""))
    return result


# --- Page Routes ---

@app.get("/")
async def dashboard_page(request: Request):
    async with async_session() as session:
        total_feeds = (await session.execute(select(func.count(Feed.id)))).scalar() or 0
        active_feeds = (await session.execute(
            select(func.count(Feed.id)).where(Feed.is_active == True)
        )).scalar() or 0
        today_articles = (await session.execute(
            select(func.count(Article.id)).where(Article.date == date.today())
        )).scalar() or 0
        today_summarized = (await session.execute(
            select(func.count(Article.id)).where(Article.date == date.today(), Article.summary.isnot(None))
        )).scalar() or 0
        today_sent = (await session.execute(
            select(func.count(Article.id)).where(Article.date == date.today(), Article.is_sent_to_telegram == True)
        )).scalar() or 0

        articles_rows = (await session.execute(
            select(Article).where(Article.date == date.today()).order_by(Article.fetched_at.desc())
        )).scalars().all()

        articles_data = []
        for a in articles_rows:
            feed = await session.get(Feed, a.feed_id)
            articles_data.append({
                "id": a.id, "title": a.title, "url": a.url, "summary": a.summary,
                "is_sent_to_telegram": a.is_sent_to_telegram,
                "feed_name": feed.name if feed else "", "fetched_at": a.fetched_at,
            })

    stats = {
        "total_feeds": total_feeds, "active_feeds": active_feeds,
        "today_articles": today_articles, "today_summarized": today_summarized,
        "today_sent": today_sent,
    }
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "active_page": "dashboard",
        "stats": stats, "articles": articles_data,
    })


@app.get("/feeds")
async def feeds_page(request: Request):
    async with async_session() as session:
        feed_rows = (await session.execute(select(Feed).order_by(Feed.created_at.desc()))).scalars().all()
        feeds_data = []
        for f in feed_rows:
            article_count = (await session.execute(
                select(func.count(Article.id)).where(Article.feed_id == f.id, Article.date == date.today())
            )).scalar() or 0
            sent_count = (await session.execute(
                select(func.count(Article.id)).where(
                    Article.feed_id == f.id, Article.date == date.today(), Article.is_sent_to_telegram == True
                )
            )).scalar() or 0
            feeds_data.append({
                "id": f.id, "name": f.name, "url": f.url,
                "category": f.category, "is_active": f.is_active,
                "article_count": article_count, "sent_count": sent_count,
            })

    return templates.TemplateResponse("feeds.html", {
        "request": request, "active_page": "feeds", "feeds": feeds_data,
    })


@app.get("/settings")
async def settings_page(request: Request):
    settings_dict = await _get_settings_dict()
    return templates.TemplateResponse("settings.html", {
        "request": request, "active_page": "settings", "settings": settings_dict,
    })


@app.post("/api/pipeline/run")
async def run_pipeline_now():
    """Manual trigger: fetch -> summarize -> send."""
    new_articles = await fetch_all_feeds()
    summarized = await summarize_unsummarized()
    sent = await send_unsent_summaries()
    return {"fetched": len(new_articles), "summarized": summarized, "sent": sent}
