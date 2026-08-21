"""
KODA-7 Configuration Manager
إدارة الإعدادات والمتغيرات البيئية
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class Config:
    """جميع الإعدادات المطلوبة للوكيل"""

    # Telegram Bot
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    CHAT_ID: str = os.getenv("CHAT_ID", "")

    # Groq AI
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama3-70b-8192")
    GROQ_MAX_TOKENS: int = int(os.getenv("GROQ_MAX_TOKENS", "4096"))

    # Telegram API (لـ Telethon)
    TG_API_ID: int = int(os.getenv("TG_API_ID", "0"))
    TG_API_HASH: str = os.getenv("TG_API_HASH", "")

    # Database
    DB_PATH: str = os.getenv("DB_PATH", "koda7.db")

    # Scheduler
    SCHEDULER_INTERVAL: int = int(os.getenv("SCHEDULER_INTERVAL", "60"))  # ثواني

    # Retry
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY: int = int(os.getenv("RETRY_DELAY", "5"))  # ثواني

    @classmethod
    def validate(cls) -> list[str]:
        """التحقق من وجود جميع المتغيرات المطلوبة"""
        missing = []
        required = [
            ("BOT_TOKEN", cls.BOT_TOKEN),
            ("CHAT_ID", cls.CHAT_ID),
            ("GROQ_API_KEY", cls.GROQ_API_KEY),
            ("TG_API_ID", cls.TG_API_ID),
            ("TG_API_HASH", cls.TG_API_HASH),
        ]
        for name, value in required:
            if not value or value == "0":
                missing.append(name)
        if missing:
            logger.error(f"Missing env vars: {missing}")
        return missing
