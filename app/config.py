from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./rss_tracker.db"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ai_provider: str = "ollama"
    ai_model: str = "qwen2.5:7b"
    daily_cleanup_hour: int = 6
    fetch_interval_minutes: int = 60

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
