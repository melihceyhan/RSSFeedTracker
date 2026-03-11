import logging
import asyncio
from abc import ABC, abstractmethod

import httpx
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Article, Setting
from app.database import async_session
from app.config import get_settings

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """Aşağıdaki haber makalesini Türkçe olarak 2-3 cümleyle özetle.
Özet kısa, bilgilendirici ve anlaşılır olmalı.

Başlık: {title}

İçerik:
{content}

Özet:"""


class BaseSummarizer(ABC):
    @abstractmethod
    async def summarize(self, title: str, content: str, model: str) -> str:
        pass


class OllamaSummarizer(BaseSummarizer):
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def summarize(self, title: str, content: str, model: str) -> str:
        prompt = SUMMARY_PROMPT.format(title=title, content=content[:3000])
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()


class OpenAISummarizer(BaseSummarizer):
    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(api_key=api_key)

    async def summarize(self, title: str, content: str, model: str) -> str:
        prompt = SUMMARY_PROMPT.format(title=title, content=content[:3000])
        response = await self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()


async def _get_setting(session: AsyncSession, key: str, default: str) -> str:
    result = await session.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting else default


def _get_summarizer(provider: str, **kwargs) -> BaseSummarizer:
    if provider == "openai":
        return OpenAISummarizer(api_key=kwargs.get("openai_api_key", ""))
    return OllamaSummarizer(base_url=kwargs.get("ollama_base_url", "http://localhost:11434"))


async def summarize_article(article: Article, session: AsyncSession) -> bool:
    """Summarize a single article. Returns True on success."""
    settings = get_settings()

    provider = await _get_setting(session, "ai_provider", settings.ai_provider)
    model = await _get_setting(session, "ai_model", settings.ai_model)
    ollama_url = await _get_setting(session, "ollama_base_url", settings.ollama_base_url)
    openai_key = await _get_setting(session, "openai_api_key", settings.openai_api_key)

    summarizer = _get_summarizer(
        provider, ollama_base_url=ollama_url, openai_api_key=openai_key
    )

    content = article.content or article.title
    for attempt in range(3):
        try:
            summary = await summarizer.summarize(article.title, content, model)
            if summary:
                article.summary = summary
                article.model_used = f"{provider}/{model}"
                await session.commit()
                logger.info(f"Summarized: {article.title[:60]}")
                return True
        except Exception as e:
            logger.warning(f"Summarize attempt {attempt+1} failed for '{article.title[:40]}': {e}")
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)

    logger.error(f"Failed to summarize after 3 attempts: {article.title[:60]}")
    return False


async def summarize_unsummarized():
    """Find and summarize all articles that don't have a summary yet."""
    async with async_session() as session:
        articles = (await session.execute(
            select(Article).where(Article.summary.is_(None))
        )).scalars().all()

        success_count = 0
        for article in articles:
            if await summarize_article(article, session):
                success_count += 1

        logger.info(f"Summarized {success_count}/{len(articles)} articles")
        return success_count
