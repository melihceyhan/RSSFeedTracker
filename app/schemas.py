from pydantic import BaseModel, HttpUrl
from datetime import datetime, date


class FeedCreate(BaseModel):
    name: str
    url: str
    category: str = "genel"


class FeedUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    category: str | None = None
    is_active: bool | None = None


class FeedOut(BaseModel):
    id: int
    name: str
    url: str
    category: str
    is_active: bool
    created_at: datetime
    article_count: int = 0
    sent_count: int = 0

    model_config = {"from_attributes": True}


class ArticleOut(BaseModel):
    id: int
    feed_id: int
    feed_name: str = ""
    title: str
    url: str
    content: str | None
    published_at: datetime | None
    fetched_at: datetime
    date: date
    summary: str | None
    model_used: str | None
    is_sent_to_telegram: bool

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    ai_provider: str | None = None
    ai_model: str | None = None
    ollama_base_url: str | None = None
    openai_api_key: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    fetch_interval_minutes: int | None = None
    daily_cleanup_hour: int | None = None


class DashboardStats(BaseModel):
    total_feeds: int
    active_feeds: int
    today_articles: int
    today_summarized: int
    today_sent: int
