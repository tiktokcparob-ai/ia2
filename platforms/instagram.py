"""
KODA-7 Instagram Platform
تكامل كامل مع Instagram باستخدام instagrapi
"""
import os
import time
import logging
from typing import Dict, Any, Optional
from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired, ChallengeRequired, 
    TwoFactorRequired, BadPassword,
    PleaseWaitFewMinutes, RateLimitError
)
from .base import PlatformPlugin
from db import db
from config import Config

logger = logging.getLogger(__name__)

class InstagramBot(PlatformPlugin):
    """بوت Instagram - يدير الجلسات والتفاعلات"""

    name = "instagram"

    def __init__(self):
        super().__init__()
        self.client = Client()
        self.client.delay_range = [2, 5]  # تأخير عشوائي بين الطلبات
        self.session_file = "instagram_session.json"

    def _save_session_file(self, username: str):
        """حفظ ملف الجلسة وتحديث قاعدة البيانات"""
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, 'r') as f:
                    session_str = f.read()
                db.save_session(
                    platform="instagram",
                    username=username,
                    credentials={},
                    session_data={"file_content": session_str},
                    status="active"
                )
                logger.info(f"Instagram session saved for {username}")
        except Exception as e:
            logger.error(f"Failed to save Instagram session: {e}")

    def _load_session_file(self, session_data: dict) -> bool:
        """استرجاع الجلسة من قاعدة البيانات"""
        try:
            if session_data and "file_content" in session_data:
                with open(self.session_file, 'w') as f:
                    f.write(session_data["file_content"])
                self.client.load_settings(self.session_file)
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to load Instagram session: {e}")
            return False

    def login(self, username: str, password: str, **kwargs) -> Dict[str, Any]:
        """
        تسجيل الدخول إلى Instagram
        يحاول أولاً استرجاع الجلسة المحفوظة، وإذا فشل يعيد تسجيل الدخول
        """
        result = {"success": False, "message": "", "session_data": {}}

        try:
            # محاولة استرجاع الجلسة القديمة
            session = db.get_session("instagram", username)
            if session and self._load_session_file(session["session_data"]):
                try:
                    self.client.login(username, password)
                    if self.client.user_id:
                        self.is_authenticated = True
                        self.current_user = username
                        result["success"] = True
                        result["message"] = f"✅ تم استرجاع الجلسة وتسجيل الدخول كـ {username}"
                        logger.info(f"Session restored for {username}")
                        return result
                except LoginRequired:
                    logger.info(f"Saved session expired for {username}, re-logging...")
                except Exception as e:
                    logger.warning(f"Session restore failed: {e}")

            # تسجيل الدخول الجديد
            logger.info(f"Attempting fresh login for {username}")
            self.client.login(username, password)

            if self.client.user_id:
                self.is_authenticated = True
                self.current_user = username
                self._save_session_file(username)

                # حفظ بيانات الاعتماد للاستخدام المستقبلي
                db.save_session(
                    platform="instagram",
                    username=username,
                    credentials={"password_hint": "stored"},
                    session_data={"user_id": str(self.client.user_id)},
                    status="active"
                )

                result["success"] = True
                result["message"] = f"✅ تم تسجيل الدخول بنجاح كـ {username}"
                result["session_data"] = {"user_id": self.client.user_id}
                logger.info(f"Fresh login successful for {username}")
            else:
                result["message"] = "❌ فشل تسجيل الدخول: لم يتم استرداد معرف المستخدم"

        except TwoFactorRequired:
            result["message"] = "🔐 يتطلب Instagram التحقق بخطوتين. يرجى تعطيله مؤقتًا أو استخدام كود الاسترداد."
            logger.error(f"2FA required for {username}")
        except ChallengeRequired:
            result["message"] = "⚠️ Instagram يتطلب تحدي أمان. يرجى تسجيل الدخول يدويًا من المتصفح أولاً."
            logger.error(f"Challenge required for {username}")
        except BadPassword:
            result["message"] = "❌ كلمة المرور غير صحيحة."
            logger.error(f"Bad password for {username}")
        except (PleaseWaitFewMinutes, RateLimitError):
            result["message"] = "⏳ تم تجاوز الحد المسموح. يرجى الانتظار بضع دقائق."
            logger.error(f"Rate limit hit for {username}")
        except Exception as e:
            result["message"] = f"❌ خطأ غير متوقع: {str(e)}"
            logger.exception(f"Unexpected login error for {username}")

        return result

    def logout(self) -> bool:
        """تسجيل الخروج"""
        try:
            if self.is_authenticated:
                self.client.logout()
            self.is_authenticated = False
            self.current_user = None
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
            return True
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return False

    def check_session(self) -> bool:
        """التحقق من صلاحية الجلسة"""
        if not self.is_authenticated:
            return False
        try:
            # محاولة جلب معلومات الحساب كاختبار
            self.client.account_info()
            return True
        except LoginRequired:
            self.is_authenticated = False
            logger.warning("Instagram session expired")
            return False
        except Exception as e:
            logger.error(f"Session check error: {e}")
            return False

    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """تنفيذ الإجراءات المدعومة"""
        if not self.is_authenticated and action != "login":
            return {"success": False, "message": "❌ يجب تسجيل الدخول أولاً"}

        handlers = {
            "login": self._handle_login,
            "interact_stories": self._handle_interact_stories,
            "post_photo": self._handle_post_photo,
            "post_video": self._handle_post_video,
            "like_post": self._handle_like_post,
            "follow_user": self._handle_follow_user,
            "send_dm": self._handle_send_dm,
        }

        handler = handlers.get(action)
        if handler:
            return handler(params)
        return {"success": False, "message": f"❌ الإجراء '{action}' غير مدعوم على Instagram"}

    def _handle_login(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """معالج تسجيل الدخول"""
        username = params.get("username")
        password = params.get("password")
        if not username or not password:
            return {"success": False, "message": "❌ يجب توفير اسم المستخدم وكلمة المرور"}
        return self.login(username, password)

    def _handle_interact_stories(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """التفاعل مع الستوريات"""
        result = {"success": False, "message": "", "data": {"viewed": 0, "liked": 0}}

        try:
            # جلب الستوريات من المتابعين
            stories = self.client.get_reels_tray()
            if not stories:
                result["message"] = "ℹ️ لا توجد ستوريات متاحة حاليًا"
                return result

            viewed = 0
            liked = 0

            for story in stories[:20]:  # الحد الأقصى 20 ستوري
                try:
                    # مشاهدة الستوري
                    self.client.story_seen(story.id)
                    viewed += 1
                    time.sleep(1)

                    # محاولة الإعجاب (إن وجد)
                    try:
                        self.client.story_like(story.id)
                        liked += 1
                    except:
                        pass

                    time.sleep(2)
                except Exception as e:
                    logger.warning(f"Failed to interact with story: {e}")
                    continue

            result["success"] = True
            result["message"] = f"✅ تم التفاعل مع {viewed} ستوري (إعجاب: {liked})"
            result["data"] = {"viewed": viewed, "liked": liked}
            logger.info(f"Interacted with {viewed} stories, liked {liked}")

        except Exception as e:
            result["message"] = f"❌ فشل التفاعل مع الستوريات: {str(e)}"
            logger.exception("Stories interaction failed")

        return result

    def _handle_post_photo(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """نشر صورة"""
        result = {"success": False, "message": "", "data": {}}

        try:
            path = params.get("path")
            caption = params.get("caption", "")

            if not path or not os.path.exists(path):
                result["message"] = "❌ مسار الصورة غير موجود"
                return result

            media = self.client.photo_upload(path, caption)
            result["success"] = True
            result["message"] = f"✅ تم نشر الصورة بنجاح"
            result["data"] = {"media_id": media.id, "code": media.code}
            logger.info(f"Photo posted: {media.code}")

        except Exception as e:
            result["message"] = f"❌ فشل نشر الصورة: {str(e)}"
            logger.exception("Photo post failed")

        return result

    def _handle_post_video(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """نشر فيديو"""
        result = {"success": False, "message": "", "data": {}}

        try:
            path = params.get("path")
            caption = params.get("caption", "")

            if not path or not os.path.exists(path):
                result["message"] = "❌ مسار الفيديو غير موجود"
                return result

            media = self.client.video_upload(path, caption)
            result["success"] = True
            result["message"] = f"✅ تم نشر الفيديو بنجاح"
            result["data"] = {"media_id": media.id, "code": media.code}
            logger.info(f"Video posted: {media.code}")

        except Exception as e:
            result["message"] = f"❌ فشل نشر الفيديو: {str(e)}"
            logger.exception("Video post failed")

        return result

    def _handle_like_post(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """الإعجاب بمنشور"""
        result = {"success": False, "message": ""}

        try:
            url = params.get("url")
            media_id = params.get("media_id")

            if url:
                media_id = self.client.media_pk_from_url(url)

            if not media_id:
                result["message"] = "❌ يجب توفير رابط المنشور أو معرفه"
                return result

            self.client.media_like(media_id)
            result["success"] = True
            result["message"] = "✅ تم الإعجاب بالمنشور"
            logger.info(f"Liked media: {media_id}")

        except Exception as e:
            result["message"] = f"❌ فشل الإعجاب: {str(e)}"
            logger.exception("Like failed")

        return result

    def _handle_follow_user(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """متابعة مستخدم"""
        result = {"success": False, "message": ""}

        try:
            username = params.get("username")
            if not username:
                result["message"] = "❌ يجب توفير اسم المستخدم"
                return result

            user_id = self.client.user_id_from_username(username)
            self.client.user_follow(user_id)
            result["success"] = True
            result["message"] = f"✅ تم متابعة {username}"
            logger.info(f"Followed user: {username}")

        except Exception as e:
            result["message"] = f"❌ فشل المتابعة: {str(e)}"
            logger.exception("Follow failed")

        return result

    def _handle_send_dm(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """إرسال رسالة خاصة"""
        result = {"success": False, "message": ""}

        try:
            username = params.get("username")
            text = params.get("text", "")

            if not username or not text:
                result["message"] = "❌ يجب توفير اسم المستخدم والنص"
                return result

            user_id = self.client.user_id_from_username(username)
            self.client.direct_send(text, [user_id])
            result["success"] = True
            result["message"] = f"✅ تم إرسال الرسالة إلى {username}"
            logger.info(f"DM sent to: {username}")

        except Exception as e:
            result["message"] = f"❌ فشل إرسال الرسالة: {str(e)}"
            logger.exception("DM failed")

        return result

    def get_supported_actions(self) -> list[str]:
        return [
            "login", "interact_stories", "post_photo", 
            "post_video", "like_post", "follow_user", "send_dm"
        ]
