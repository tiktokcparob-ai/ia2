"""
KODA-7 AI Engine
محرك الذكاء الاصطناعي باستخدام Groq API
يفهم الأوامر الطبيعية ويولد ردودًا ذكية
"""
import json
import logging
from typing import Dict, Any, Optional, List
from groq import Groq
from config import Config
from db import db

logger = logging.getLogger(__name__)

class AIEngine:
    """محرك الذكاء الاصطناعي المركزي"""

    def __init__(self):
        self.client = Groq(api_key=Config.GROQ_API_KEY)
        self.model = Config.GROQ_MODEL
        self.max_tokens = Config.GROQ_MAX_TOKENS

    def _call_groq(self, messages: List[Dict[str, str]], temperature: float = 0.3, 
                   response_format: str = None) -> Optional[str]:
        """استدعاء Groq API مع معالجة الأخطاء"""
        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": self.max_tokens
            }
            if response_format:
                kwargs["response_format"] = {"type": response_format}

            response = self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            return None

    def understand(self, user_input: str) -> Dict[str, Any]:
        """
        تحليل الأمر الطبيعي واستخراج:
        - platform: المنصة المستهدفة
        - action: الإجراء المطلوب
        - params: المعاملات
        - response: رد للمستخدم
        """
        system_prompt = """أنت محلل أوامر ذكي لوكيل KODA-7. مهمتك تحليل نص المستخدم واستخراج معلومات منظمة.

المنصات المدعومة: instagram, telegram, facebook, twitter, tiktok
الإجراءات المدعومة: login, logout, interact_stories, post_photo, post_video, like_post, follow_user, send_dm, send_message, send_file, get_dialogs

أخرج JSON فقط بهذا الشكل:
{
    "platform": "اسم المنصة",
    "action": "الإجراء",
    "params": {},
    "response": "رد ودي للمستخدم بالعربية"
}

إذا لم يكن الأمر واضحًا:
{
    "platform": null,
    "action": null,
    "params": {},
    "response": "سؤال توضيحي"
}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"حلل هذا الأمر: '{user_input}'"}
        ]

        response = self._call_groq(messages, temperature=0.2, response_format="json_object")

        if not response:
            return {
                "platform": None,
                "action": None,
                "params": {},
                "response": "⚠️ عذرًا، حدث خطأ في تحليل الأمر. يرجى المحاولة بصيغة أوضح."
            }

        try:
            parsed = json.loads(response)
            # التحقق من الحقول
            return {
                "platform": parsed.get("platform"),
                "action": parsed.get("action"),
                "params": parsed.get("params", {}),
                "response": parsed.get("response", "")
            }
        except json.JSONDecodeError:
            logger.error(f"Failed to parse AI response: {response}")
            return {
                "platform": None,
                "action": None,
                "params": {},
                "response": "⚠️ لم أفهم الأمر تمامًا. هل يمكنك إعادة صياغته؟"
            }

    def chat(self, user_id: str, user_input: str) -> str:
        """
        محادثة عامة مع الذاكرة
        """
        # استرجاع السياق
        history = db.get_conversation(user_id, limit=10)
        messages = [{"role": "system", "content": "أنت KODA-7، وكيل ذكي يساعد المستخدم في إدارة حساباته الاجتماعية. تحدث بالعربية الفصحى."}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        response = self._call_groq(messages, temperature=0.7)

        if response:
            # حفظ المحادثة
            db.add_message(user_id, "user", user_input)
            db.add_message(user_id, "assistant", response)
            return response

        return "⚠️ عذرًا، لا يمكنني الرد حاليًا. يرجى المحاولة لاحقًا."

    def generate_cron_params(self, user_input: str) -> Dict[str, Any]:
        """
        تحليل أمر إضافة مهمة مجدولة واستخراج:
        - cron_expr: تعبير cron
        - description: وصف المهمة
        """
        system_prompt = """أنت محلل جداول cron. استخرج من النص:
1. تعبير cron صحيح (5 حقول: دقيقة ساعة يوم شهر يوم_الأسبوع)
2. وصف المهمة
3. المنصة والإجراء المستهدف

أخرج JSON فقط:
{
    "cron_expr": "* * * * *",
    "description": "وصف",
    "platform": "instagram",
    "action": "post_photo",
    "params": {}
}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"حلل: '{user_input}'"}
        ]

        response = self._call_groq(messages, temperature=0.2, response_format="json_object")

        if not response:
            return {"error": "فشل التحليل"}

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {"error": "فشل تحليل الرد"}

    def explain_error(self, error: str, platform: str) -> str:
        """توليد شرح خطأ للمستخدم"""
        system_prompt = f"""اشرح هذا الخأ بلغة عربية بسيطة وقدم حلاً عمليًا:
المنصة: {platform}
الخطأ: {error}"""

        messages = [
            {"role": "system", "content": "أنت مساعد تقني. اشرح الأخطاء ببساطة وقدم حلولًا واضحة بالعربية."},
            {"role": "user", "content": system_prompt}
        ]

        response = self._call_groq(messages, temperature=0.5)
        return response or "⚠️ حدث خطأ غير معروف. يرجى التحقق من السجلات."

# Singleton instance
ai_engine = AIEngine()
