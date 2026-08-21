"""
KODA-7 Platforms Package
"""
from .base import PlatformPlugin
from .instagram import InstagramBot
from .telegram import TelegramBot

__all__ = ["PlatformPlugin", "InstagramBot", "TelegramBot"]
