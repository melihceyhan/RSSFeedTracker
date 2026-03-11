from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Setting
from app.schemas import SettingsUpdate
from app.config import get_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])

SETTING_KEYS = [
    "ai_provider", "ai_model", "ollama_base_url", "openai_api_key",
    "telegram_bot_token", "telegram_chat_id", "fetch_interval_minutes",
    "daily_cleanup_hour",
]


@router.get("")
async def get_all_settings(db: AsyncSession = Depends(get_db)):
    defaults = get_settings()
    result = {}
    for key in SETTING_KEYS:
        row = (await db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
        if row:
            result[key] = row.value
        else:
            result[key] = getattr(defaults, key, "")
    if "openai_api_key" in result and result["openai_api_key"]:
        result["openai_api_key"] = result["openai_api_key"][:8] + "..."
    return result


@router.put("")
async def update_settings(data: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    updated = []
    for key, value in data.model_dump(exclude_none=True).items():
        row = (await db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
        if row:
            row.value = str(value)
        else:
            db.add(Setting(key=key, value=str(value)))
        updated.append(key)
    await db.commit()
    return {"updated": updated}
