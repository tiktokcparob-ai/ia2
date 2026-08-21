"""
KODA-7 Base Platform Plugin
واجهة موحدة لجميع المنصات - أي منصة جديدة يجب أن ترث من هذا الكلاس
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class PlatformPlugin(ABC):
    """الواجهة الأساسية لجميع البوتات"""

    name: str = "base"

    def __init__(self):
        self.is_authenticated: bool = False
        self.current_user: Optional[str] = None

    @abstractmethod
    def login(self, username: str, password: str, **kwargs) -> Dict[str, Any]:
        """
        تسجيل الدخول إلى المنصة
        Returns: {"success": bool, "message": str, "session_data": dict}
        """
        pass

    @abstractmethod
    def logout(self) -> bool:
        """تسجيل الخروج"""
        pass

    @abstractmethod
    def check_session(self) -> bool:
        """التحقق من صلاحية الجلسة"""
        pass

    @abstractmethod
    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        تنفيذ إجراء على المنصة
        Returns: {"success": bool, "message": str, "data": dict}
        """
        pass

    def get_supported_actions(self) -> list[str]:
        """الإجراءات المدعومة"""
        return ["login", "logout", "check_session"]
