import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import delete

from app.models import Article
from app.database import async_session
from app.config import get_settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def daily_cleanup():
    """Delete all articles from previous days."""
    async with async_session() as session:
        result = await session.execute(
            delete(Article).where(Article.date < date.today())
        )
        await session.commit()
        logger.info(f"Daily cleanup: removed {result.rowcount} old articles")


async def hourly_pipeline():
    """Main pipeline: fetch -> summarize -> send to Telegram."""
    from app.services.feed_fetcher import fetch_all_feeds
    from app.services.summarizer import summarize_unsummarized
    from app.services.telegram_sender import send_unsent_summaries

    logger.info("Hourly pipeline started")

    new_articles = await fetch_all_feeds()
    logger.info(f"Fetched {len(new_articles)} new articles")

    if new_articles:
        summarized = await summarize_unsummarized()
        logger.info(f"Summarized {summarized} articles")

    sent = await send_unsent_summaries()
    logger.info(f"Sent {sent} summaries to Telegram")


async def run_pipeline_now():
    """Manual trigger for the pipeline."""
    await hourly_pipeline()


def start_scheduler():
    settings = get_settings()

    scheduler.add_job(
        daily_cleanup,
        trigger=CronTrigger(hour=settings.daily_cleanup_hour, minute=0),
        id="daily_cleanup",
        replace_existing=True,
        name="Daily old article cleanup",
    )

    scheduler.add_job(
        hourly_pipeline,
        trigger=IntervalTrigger(minutes=settings.fetch_interval_minutes),
        id="hourly_pipeline",
        replace_existing=True,
        name="Hourly fetch-summarize-send pipeline",
    )

    scheduler.start()
    logger.info(
        f"Scheduler started: cleanup at {settings.daily_cleanup_hour}:00, "
        f"pipeline every {settings.fetch_interval_minutes} min"
    )


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
