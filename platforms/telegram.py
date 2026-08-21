"""
KODA-7 Telegram Platform
تكامل كامل مع Telegram باستخدام Telethon
يدعم تسجيل الدخول التفاعلي (رمز التحقق + 2FA)
"""
import os
import asyncio
import logging
from typing import Dict, Any, Optional
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError, 
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    FloodWaitError,
    AuthKeyUnregisteredError
)
from telethon.sessions import StringSession
from .base import PlatformPlugin
from db import db
from config import Config

logger = logging.getLogger(__name__)

class TelegramBot(PlatformPlugin):
    """بوت Telegram - يدير الجلسات والمراسلة"""

    name = "telegram"

    def __init__(self):
        super().__init__()
        self.client: Optional[TelegramClient] = None
        self.session_string: Optional[str] = None
        self.phone: Optional[str] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_loop(self):
        """الحصول على حلقة الأحداث"""
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    def _init_client(self, session_str: str = None):
        """تهيئة عميل Telethon"""
        session = StringSession(session_str) if session_str else StringSession()
        self.client = TelegramClient(
            session,
            Config.TG_API_ID,
            Config.TG_API_HASH,
            device_model="KODA7 Agent",
            system_version="1.0",
            app_version="1.0"
        )
        return self.client

    def _save_session(self, username: str, session_str: str):
        """حفظ الجلسة في قاعدة البيانات"""
        try:
            db.save_session(
                platform="telegram",
                username=username,
                credentials={"phone": self.phone},
                session_data={"session_string": session_str},
                status="active"
            )
            logger.info(f"Telegram session saved for {username}")
        except Exception as e:
            logger.error(f"Failed to save Telegram session: {e}")

    def login(self, username: str = None, password: str = None, **kwargs) -> Dict[str, Any]:
        """
        تسجيل الدخول إلى Telegram
        يدعم: جلسة محفوظة، تسجيل دخول جديد برقم الهاتف
        """
        result = {"success": False, "message": "", "session_data": {}}

        # محاولة استرجاع الجلسة المحفوظة
        session = db.get_session("telegram", username)
        if session and session["session_data"].get("session_string"):
            try:
                self._init_client(session["session_data"]["session_string"])
                self._get_loop().run_until_complete(self.client.connect())

                if self._get_loop().run_until_complete(self.client.is_user_authorized()):
                    me = self._get_loop().run_until_complete(self.client.get_me())
                    self.is_authenticated = True
                    self.current_user = me.username or str(me.id)
                    result["success"] = True
                    result["message"] = f"✅ تم استرجاع الجلسة كـ {self.current_user}"
                    logger.info(f"Telegram session restored for {self.current_user}")
                    return result
                else:
                    self._get_loop().run_until_complete(self.client.disconnect())
                    logger.info("Saved Telegram session expired")
            except Exception as e:
                logger.warning(f"Telegram session restore failed: {e}")

        # إذا لم يكن هناك جلسة محفوظة، نحتاج إلى تسجيل دخول جديد
        result["message"] = "🔐 يرجى بدء تسجيل الدخول باستخدام الأمر: /login telegram <phone_number>"
        return result

    def start_login(self, phone: str) -> Dict[str, Any]:
        """بدء عملية تسجيل الدخول - إرسال رمز التحقق"""
        result = {"success": False, "message": ""}

        try:
            self.phone = phone
            self._init_client()
            self._get_loop().run_until_complete(self.client.connect())

            sent = self._get_loop().run_until_complete(self.client.send_code_request(phone))
            result["success"] = True
            result["message"] = f"📩 تم إرسال رمز التحقق إلى {phone}. يرجى إدخال الرمز باستخدام: /verify telegram <code>"
            result["phone_code_hash"] = sent.phone_code_hash
            logger.info(f"Verification code sent to {phone}")

        except FloodWaitError as e:
            result["message"] = f"⏳ يرجى الانتظار {e.seconds} ثانية قبل المحاولة مجددًا"
            logger.error(f"Flood wait: {e.seconds}s")
        except Exception as e:
            result["message"] = f"❌ فشل إرسال رمز التحقق: {str(e)}"
            logger.exception("Failed to send code")

        return result

    def verify_code(self, code: str, password: str = None) -> Dict[str, Any]:
        """التحقق من الرمز وإكمال تسجيل الدخول"""
        result = {"success": False, "message": ""}

        if not self.client or not self.phone:
            result["message"] = "❌ لم يتم بدء عملية تسجيل الدخول. استخدم /login telegram <phone> أولاً"
            return result

        try:
            self._get_loop().run_until_complete(
                self.client.sign_in(self.phone, code)
            )

            # نجاح بدون 2FA
            me = self._get_loop().run_until_complete(self.client.get_me())
            self.is_authenticated = True
            self.current_user = me.username or str(me.id)

            # حفظ الجلسة
            session_str = self._get_loop().run_until_complete(self.client.session.save())
            self._save_session(self.current_user, session_str)

            result["success"] = True
            result["message"] = f"✅ تم تسجيل الدخول بنجاح كـ {self.current_user}"
            logger.info(f"Telegram login successful for {self.current_user}")

        except SessionPasswordNeededError:
            # يتطلب 2FA
            if password:
                try:
                    self._get_loop().run_until_complete(
                        self.client.sign_in(password=password)
                    )
                    me = self._get_loop().run_until_complete(self.client.get_me())
                    self.is_authenticated = True
                    self.current_user = me.username or str(me.id)

                    session_str = self._get_loop().run_until_complete(self.client.session.save())
                    self._save_session(self.current_user, session_str)

                    result["success"] = True
                    result["message"] = f"✅ تم تسجيل الدخول بنجاح (مع 2FA) كـ {self.current_user}"
                    logger.info(f"Telegram login with 2FA successful for {self.current_user}")
                except Exception as e:
                    result["message"] = f"❌ كلمة المرور الثنائية غير صحيحة: {str(e)}"
                    logger.error(f"2FA failed: {e}")
            else:
                result["message"] = "🔐 يتطلب الحساب كلمة مرور ثنائية. أرسل: /verify telegram <code> <password>"
                logger.info("2FA password needed")
        except PhoneCodeInvalidError:
            result["message"] = "❌ رمز التحقق غير صحيح. يرجى التحقق والمحاولة مجددًا."
            logger.error("Invalid verification code")
        except PhoneCodeExpiredError:
            result["message"] = "⏰ رمز التحقق منتهي الصلاحية. يرجى طلب رمز جديد."
            logger.error("Expired verification code")
        except Exception as e:
            result["message"] = f"❌ فشل التحقق: {str(e)}"
            logger.exception("Verification failed")

        return result

    def logout(self) -> bool:
        """تسجيل الخروج"""
        try:
            if self.client:
                self._get_loop().run_until_complete(self.client.log_out())
                self._get_loop().run_until_complete(self.client.disconnect())
            self.is_authenticated = False
            self.current_user = None
            self.session_string = None
            return True
        except Exception as e:
            logger.error(f"Telegram logout error: {e}")
            return False

    def check_session(self) -> bool:
        """التحقق من صلاحية الجلسة"""
        if not self.client or not self.is_authenticated:
            return False
        try:
            return self._get_loop().run_until_complete(self.client.is_user_authorized())
        except AuthKeyUnregisteredError:
            self.is_authenticated = False
            logger.warning("Telegram auth key unregistered")
            return False
        except Exception as e:
            logger.error(f"Telegram session check error: {e}")
            return False

    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """تنفيذ الإجراءات المدعومة"""
        if not self.is_authenticated and action not in ["login", "start_login", "verify_code"]:
            return {"success": False, "message": "❌ يجب تسجيل الدخول أولاً"}

        handlers = {
            "login": self._handle_login,
            "start_login": self._handle_start_login,
            "verify_code": self._handle_verify_code,
            "send_message": self._handle_send_message,
            "send_file": self._handle_send_file,
            "get_dialogs": self._handle_get_dialogs,
        }

        handler = handlers.get(action)
        if handler:
            return handler(params)
        return {"success": False, "message": f"❌ الإجراء '{action}' غير مدعوم على Telegram"}

    def _handle_login(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """معالج تسجيل الدخول (استرجاع جلسة)"""
        return self.login()

    def _handle_start_login(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """بدء تسجيل الدخول برقم الهاتف"""
        phone = params.get("phone")
        if not phone:
            return {"success": False, "message": "❌ يجب توفير رقم الهاتف"}
        return self.start_login(phone)

    def _handle_verify_code(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """التحقق من الرمز"""
        code = params.get("code")
        password = params.get("password")
        if not code:
            return {"success": False, "message": "❌ يجب توفير رمز التحقق"}
        return self.verify_code(code, password)

    def _handle_send_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """إرسال رسالة"""
        result = {"success": False, "message": ""}

        try:
            target = params.get("target")  # username, id, or phone
            text = params.get("text", "")

            if not target or not text:
                result["message"] = "❌ يجب توفير المستلم والنص"
                return result

            entity = self._get_loop().run_until_complete(self.client.get_entity(target))
            self._get_loop().run_until_complete(
                self.client.send_message(entity, text)
            )

            result["success"] = True
            result["message"] = f"✅ تم إرسال الرسالة إلى {target}"
            logger.info(f"Message sent to {target}")

        except Exception as e:
            result["message"] = f"❌ فشل إرسال الرسالة: {str(e)}"
            logger.exception("Send message failed")

        return result

    def _handle_send_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """إرسال ملف"""
        result = {"success": False, "message": ""}

        try:
            target = params.get("target")
            path = params.get("path")
            caption = params.get("caption", "")

            if not target or not path or not os.path.exists(path):
                result["message"] = "❌ يجب توفير المستلم ومسار الملف الصحيح"
                return result

            entity = self._get_loop().run_until_complete(self.client.get_entity(target))
            self._get_loop().run_until_complete(
                self.client.send_file(entity, path, caption=caption)
            )

            result["success"] = True
            result["message"] = f"✅ تم إرسال الملف إلى {target}"
            logger.info(f"File sent to {target}")

        except Exception as e:
            result["message"] = f"❌ فشل إرسال الملف: {str(e)}"
            logger.exception("Send file failed")

        return result

    def _handle_get_dialogs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """جلب قائمة المحادثات"""
        result = {"success": False, "message": "", "data": {"dialogs": []}}

        try:
            limit = params.get("limit", 20)
            dialogs = self._get_loop().run_until_complete(
                self.client.get_dialogs(limit=limit)
            )

            dialog_list = []
            for dialog in dialogs:
                dialog_list.append({
                    "name": dialog.name,
                    "id": dialog.id,
                    "unread": dialog.unread_count,
                    "type": "group" if dialog.is_group else "user" if dialog.is_user else "channel"
                })

            result["success"] = True
            result["message"] = f"📋 تم جلب {len(dialog_list)} محادثة"
            result["data"]["dialogs"] = dialog_list
            logger.info(f"Retrieved {len(dialog_list)} dialogs")

        except Exception as e:
            result["message"] = f"❌ فشل جلب المحادثات: {str(e)}"
            logger.exception("Get dialogs failed")

        return result

    def get_supported_actions(self) -> list[str]:
        return [
            "login", "start_login", "verify_code",
            "send_message", "send_file", "get_dialogs"
        ]
