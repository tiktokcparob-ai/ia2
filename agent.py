
import os
import sys
import time
import json
import logging
import threading
from typing import Dict, Any

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("koda7.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# استيراد المكونات
from config import Config
from db import db
from ai_engine import ai_engine
from scheduler import scheduler
from platforms import InstagramBot, TelegramBot

# استيراد telebot
import telebot
from telebot.types import Message


class KODA7Agent:
    """الوكيل الرئيسي KODA-7"""

    def __init__(self):
        self.bot = telebot.TeleBot(Config.BOT_TOKEN, parse_mode="HTML")
        self.chat_id = Config.CHAT_ID
        self.platforms: Dict[str, Any] = {}
        self._running = False
        self._init_platforms()
        self._setup_handlers()

    def _init_platforms(self):
        """تهيئة المنصات"""
        self.platforms["instagram"] = InstagramBot()
        self.platforms["telegram"] = TelegramBot()
        logger.info("Platforms initialized")

    def _send_notification(self, text: str):
        """إرسال إشعار إلى المستخدم"""
        try:
            if self.chat_id:
                self.bot.send_message(self.chat_id, text)
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    def _setup_handlers(self):
        """إعداد معالجات أوامر Telegram"""

        @self.bot.message_handler(commands=["start"])
        def handle_start(message: Message):
            """أمر البداية"""
            user_id = str(message.from_user.id)
            welcome = """🤖 <b>مرحبًا بك في KODA-7</b>

أنا وكيلك الذكي لإدارة حساباتك الاجتماعية.

<b>الأوامر المتاحة:</b>
• <code>/login &lt;platform&gt; &lt;credentials&gt;</code> - تسجيل الدخول
• <code>/task &lt;platform&gt; &lt;action&gt; [params]</code> - إضافة مهمة
• <code>/cron add "&lt;expression&gt;" "&lt;command&gt;"</code> - مهمة مجدولة
• <code>/cron list</code> - عرض المهام المجدولة
• <code>/cron remove &lt;id&gt;</code> - حذف مهمة مجدولة
• <code>/status</code> - حالة المنصات
• <code>/logs</code> - عرض السجلات
• <code>/help</code> - المساعدة

<b>أمثلة على الأوامر الطبيعية:</b>
"سجل الدخول إلى إنستغرام ibrahim_3_6_9"
"تفاعل مع ستوريات المتابعين"
"أرسل رسالة إلى @username"
"انشر صورة جديدة مع تعليق"""
            self.bot.reply_to(message, welcome)
            db.add_message(user_id, "user", "/start")
            db.add_message(user_id, "assistant", welcome)

        @self.bot.message_handler(commands=["help"])
        def handle_help(message: Message):
            """المساعدة"""
            help_text = """📖 <b>دليل استخدام KODA-7</b>

<b>1. تسجيل الدخول:</b>
<code>/login instagram username password</code>
<code>/login telegram +123456789</code> (ثم <code>/verify telegram &lt;code&gt;</code>)

<b>2. تنفيذ مهمة فورية:</b>
<code>/task instagram interact_stories</code>
<code>/task telegram send_message target=@user text=مرحبًا</code>

<b>3. مهام مجدولة:</b>
<code>/cron add "0 9 * * *" "انشر منشور صباحي" platform=instagram</code>

<b>4. الأوامر الطبيعية:</b>
فقط اكتب ما تريد وسأحاول فهمه وتنفيذه!

<b>5. المساعدة:</b>
<code>/status</code> - حالة الجلسات
<code>/logs</code> - آخر 20 سجل"""
            self.bot.reply_to(message, help_text)

        @self.bot.message_handler(commands=["login"])
        def handle_login(message: Message):
            """تسجيل الدخول إلى منصة"""
            user_id = str(message.from_user.id)
            parts = message.text.split(maxsplit=3)

            if len(parts) < 3:
                msg = """❌ الاستخدام: /login &lt;platform&gt; &lt;username&gt; [password]
أو: /login telegram &lt;phone&gt;"""
                self.bot.reply_to(message, msg)
                return

            platform = parts[1].lower()

            if platform == "telegram":
                phone = parts[2]
                bot_instance = self.platforms.get("telegram")
                if not bot_instance:
                    self.bot.reply_to(message, "❌ منصة Telegram غير متاحة")
                    return

                # حفظ حالة الانتظار
                db.set_pending(user_id, "telegram", "phone_sent", {"phone": phone})

                # إرسال رمز التحقق
                result = bot_instance.start_login(phone)
                self.bot.reply_to(message, result["message"])

                if result["success"]:
                    db.set_pending(user_id, "telegram", "code_sent", {"phone": phone})

            elif platform == "instagram":
                if len(parts) < 4:
                    self.bot.reply_to(
                        message,
                        "❌ الاستخدام: /login instagram &lt;username&gt; &lt;password&gt;"
                    )
                    return

                username = parts[2]
                password = parts[3]
                bot_instance = self.platforms.get("instagram")

                if not bot_instance:
                    self.bot.reply_to(message, "❌ منصة Instagram غير متاحة")
                    return

                self.bot.reply_to(
                    message,
                    f"🔐 جاري تسجيل الدخول إلى Instagram كـ {username}..."
                )

                result = bot_instance.login(username, password)
                self.bot.reply_to(message, result["message"])

                if not result["success"]:
                    db.add_log(
                        "ERROR",
                        f"Instagram login failed for {username}",
                        "agent",
                        result["message"]
                    )
            else:
                self.bot.reply_to(
                    message,
                    f"❌ المنصة '{platform}' غير مدعومة. المنصات المتاحة: instagram, telegram"
                )

        @self.bot.message_handler(commands=["verify"])
        def handle_verify(message: Message):
            """التحقق من رمز Telegram"""
            user_id = str(message.from_user.id)
            parts = message.text.split(maxsplit=3)

            if len(parts) < 3:
                self.bot.reply_to(
                    message,
                    "❌ الاستخدام: /verify telegram &lt;code&gt; [password]"
                )
                return

            platform = parts[1].lower()
            if platform != "telegram":
                self.bot.reply_to(message, "❌ الأمر يعمل فقط مع Telegram")
                return

            code = parts[2]
            password = parts[3] if len(parts) > 3 else None

            # التحقق من وجود عملية معلقة
            pending = db.get_pending(user_id, "telegram")
            if not pending or pending["step"] not in ["phone_sent", "code_sent"]:
                msg = """❌ لا توجد عملية تسجيل دخول معلقة.
استخدم /login telegram &lt;phone&gt; أولاً"""
                self.bot.reply_to(message, msg)
                return

            bot_instance = self.platforms.get("telegram")
            if not bot_instance:
                self.bot.reply_to(message, "❌ خطأ في تهيئة منصة Telegram")
                return

            self.bot.reply_to(message, "🔐 جاري التحقق من الرمز...")

            result = bot_instance.verify_code(code, password)
            self.bot.reply_to(message, result["message"])

            if result["success"]:
                db.clear_pending(user_id, "telegram")
            else:
                db.add_log("ERROR", "Telegram verification failed", "agent", result["message"])

        @self.bot.message_handler(commands=["task"])
        def handle_task(message: Message):
            """إضافة مهمة يدوية"""
            user_id = str(message.from_user.id)
            parts = message.text.split(maxsplit=3)

            if len(parts) < 3:
                self.bot.reply_to(
                    message,
                    "❌ الاستخدام: /task &lt;platform&gt; &lt;action&gt; [params_json]"
                )
                return

            platform = parts[1].lower()
            action = parts[2]
            params = {}

            if len(parts) > 3:
                try:
                    # محاولة تحليل JSON
                    params = json.loads(parts[3])
                except json.JSONDecodeError:
                    # تحليل key=value pairs
                    for pair in parts[3].split():
                        if "=" in pair:
                            k, v = pair.split("=", 1)
                            params[k] = v

            task_id = db.add_task(platform, action, params)

            if task_id > 0:
                msg = f"✅ تمت إضافة المهمة #{task_id}\nالمنصة: {platform}\nالإجراء: {action}"
                self.bot.reply_to(message, msg)
                logger.info(f"Task {task_id} added by user {user_id}")
            else:
                self.bot.reply_to(message, "❌ فشل إضافة المهمة")

        @self.bot.message_handler(commands=["cron"])
        def handle_cron(message: Message):
            """إدارة المهام المجدولة"""
            user_id = str(message.from_user.id)
            parts = message.text.split(maxsplit=1)

            if len(parts) < 2:
                msg = """❌ الاستخدام:
/cron add "&lt;expression&gt;" "&lt;command&gt;" platform=&lt;platform&gt;
/cron list
/cron remove &lt;id&gt;"""
                self.bot.reply_to(message, msg)
                return

            subcommand = parts[1].split()[0].lower()

            if subcommand == "add":
                # /cron add "0 9 * * *" "post morning" platform=instagram
                rest = parts[1][4:].strip()

                # محاولة استخدام AI لفهم الأمر
                parsed = ai_engine.generate_cron_params(rest)

                if "error" in parsed:
                    self.bot.reply_to(message, f"❌ فشل تحليل الأمر: {parsed['error']}")
                    return

                cron_expr = parsed.get("cron_expr")
                platform = parsed.get("platform", "instagram")
                action = parsed.get("action", "post_photo")
                task_params = parsed.get("params", {})

                job_id = db.add_cron_job(cron_expr, platform, action, task_params)

                if job_id > 0:
                    msg = (
                        f"📌 تمت إضافة المهمة المجدولة #{job_id}\n"
                        f"التعبير: <code>{cron_expr}</code>\n"
                        f"المنصة: {platform}\n"
                        f"الإجراء: {action}"
                    )
                    self.bot.reply_to(message, msg)
                    logger.info(f"Cron job {job_id} added")
                else:
                    self.bot.reply_to(message, "❌ فشل إضافة المهمة المجدولة")

            elif subcommand == "list":
                jobs = db.get_active_cron_jobs()
                if not jobs:
                    self.bot.reply_to(message, "📋 لا توجد مهام مجدولة نشطة")
                    return

                text = "📋 <b>المهام المجدولة:</b>\n\n"
                for job in jobs:
                    text += f"<b>#{job['id']}</b> | <code>{job['cron_expr']}</code>\n"
                    text += f"المنصة: {job['platform']} | الإجراء: {job['action']}\n"
                    text += f"آخر تشغيل: {job['last_run'] or 'لم يُشغل'}\n\n"

                self.bot.reply_to(message, text)

            elif subcommand == "remove":
                try:
                    job_id = int(parts[1].split()[1])
                    if db.delete_cron_job(job_id):
                        self.bot.reply_to(message, f"✅ تم حذف المهمة المجدولة #{job_id}")
                    else:
                        self.bot.reply_to(message, "❌ فشل الحذف")
                except (IndexError, ValueError):
                    self.bot.reply_to(message, "❌ الاستخدام: /cron remove &lt;id&gt;")

            else:
                self.bot.reply_to(
                    message,
                    "❌ الأمر الفرعي غير معروف. استخدم: add, list, remove"
                )

        @self.bot.message_handler(commands=["status"])
        def handle_status(message: Message):
            """عرض حالة المنصات"""
            text = "📊 <b>حالة المنصات:</b>\n\n"

            for name, bot in self.platforms.items():
                status = "✅ متصل" if bot.check_session() else "❌ غير متصل"
                user = bot.current_user or "غير مسجل"
                actions = ", ".join(bot.get_supported_actions()[:5])
                text += f"<b>{name.upper()}</b>: {status}\n"
                text += f"المستخدم: {user}\n"
                text += f"الإجراءات: {actions}...\n\n"

            # عدد المهام المعلقة
            pending = db.get_pending_tasks(limit=100)
            text += f"<b>المهام المعلقة:</b> {len(pending)}\n"

            # عدد المهام المجدولة
            cron_jobs = db.get_active_cron_jobs()
            text += f"<b>المهام المجدولة:</b> {len(cron_jobs)}"

            self.bot.reply_to(message, text)

        @self.bot.message_handler(commands=["logs"])
        def handle_logs(message: Message):
            """عرض السجلات"""
            logs = db.get_logs(limit=20)
            if not logs:
                self.bot.reply_to(message, "📋 لا توجد سجلات")
                return

            text = "📜 <b>آخر السجلات:</b>\n\n"
            for log in logs:
                emoji = "🔴" if log["level"] == "ERROR" else "🟡" if log["level"] == "WARNING" else "🟢"
                text += f"{emoji} <b>{log['level']}</b> | {log['created_at']}\n"
                text += f"{log['message'][:100]}\n\n"

            self.bot.reply_to(message, text)

        @self.bot.message_handler(func=lambda message: True)
        def handle_natural(message: Message):
            """معالجة الأوامر الطبيعية"""
            user_id = str(message.from_user.id)
            user_input = message.text

            # التحقق من وجود عملية معلقة
            for platform in ["telegram", "instagram"]:
                pending = db.get_pending(user_id, platform)
                if pending:
                    if platform == "telegram" and pending["step"] == "code_sent":
                        # المستخدم يرسل رمز التحقق بدون أمر /verify
                        bot_instance = self.platforms.get("telegram")
                        if bot_instance:
                            result = bot_instance.verify_code(user_input.strip())
                            self.bot.reply_to(message, result["message"])
                            if result["success"]:
                                db.clear_pending(user_id, "telegram")
                            return

            # تحليل الأمر باستخدام AI
            parsed = ai_engine.understand(user_input)

            if parsed["response"]:
                self.bot.reply_to(message, parsed["response"])

            # إذا كان هناك إجراء محدد، نفذه
            if parsed["platform"] and parsed["action"]:
                platform_name = parsed["platform"].lower()
                action = parsed["action"]
                params = parsed.get("params", {})

                bot_instance = self.platforms.get(platform_name)
                if not bot_instance:
                    self.bot.reply_to(
                        message,
                        f"❌ المنصة '{platform_name}' غير متاحة حاليًا"
                    )
                    return

                # التحقق من تسجيل الدخول (إذا لزم)
                if action != "login" and not bot_instance.check_session():
                    msg = (
                        f"⚠️ أنت غير مسجل الدخول إلى {platform_name}. "
                        f"استخدم: /login {platform_name} ..."
                    )
                    self.bot.reply_to(message, msg)
                    return

                # تنفيذ الإجراء
                self.bot.reply_to(
                    message,
                    f"⚙️ جاري تنفيذ: {action} على {platform_name}..."
                )

                result = bot_instance.execute(action, params)

                if result.get("success"):
                    self.bot.reply_to(message, f"✅ {result.get('message', 'تم التنفيذ')}")
                else:
                    self.bot.reply_to(message, f"❌ {result.get('message', 'فشل التنفيذ')}")
                    db.add_log(
                        "ERROR",
                        f"Action failed: {action} on {platform_name}",
                        "agent",
                        result.get("message")
                    )
            else:
                # محادثة عامة
                response = ai_engine.chat(user_id, user_input)
                if response and not parsed.get("response"):
                    self.bot.reply_to(message, response)

    def _task_worker(self):
        """خيط معالجة المهام الخلفية"""
        logger.info("Task worker started")

        while self._running:
            try:
                tasks = db.get_pending_tasks(limit=5)

                for task in tasks:
                    task_id = task["id"]
                    platform = task["platform"]
                    action = task["action"]
                    params = json.loads(task["params"] or "{}")
                    retries = task["retries"]

                    logger.info(f"Processing task {task_id}: {action} on {platform}")
                    db.update_task(task_id, "running")

                    bot_instance = self.platforms.get(platform)
                    if not bot_instance:
                        db.update_task(
                            task_id,
                            "failed",
                            f"Platform {platform} not available"
                        )
                        continue

                    try:
                        # التحقق من الجلسة
                        if action != "login" and not bot_instance.check_session():
                            # محاولة إعادة تسجيل الدخول
                            session = db.get_session(platform)
                            if session and session["credentials"]:
                                creds = session["credentials"]
                                if (
                                    platform == "instagram"
                                    and "password_hint" in creds
                                ):
                                    # لا يمكننا إعادة تسجيل الدخول بدون كلمة المرور
                                    db.update_task(
                                        task_id,
                                        "failed",
                                        "Session expired and cannot auto-relogin without password"
                                    )
                                    self._send_notification(
                                        f"⚠️ مهمة #{task_id} فشلت: انتهت جلسة {platform}. "
                                        "يرجى تسجيل الدخول مجددًا."
                                    )
                                    continue
                                elif platform == "telegram":
                                    bot_instance.login()
                                    if not bot_instance.check_session():
                                        db.update_task(
                                            task_id,
                                            "failed",
                                            "Telegram session expired"
                                        )
                                        continue
                            else:
                                db.update_task(
                                    task_id,
                                    "failed",
                                    "No active session"
                                )
                                continue

                        # تنفيذ المهمة
                        result = bot_instance.execute(action, params)

                        if result.get("success"):
                            db.update_task(task_id, "completed")
                            logger.info(f"Task {task_id} completed successfully")
                        else:
                            if retries >= Config.MAX_RETRIES - 1:
                                db.update_task(
                                    task_id,
                                    "failed",
                                    result.get("message", "Unknown error")
                                )
                                self._send_notification(
                                    f"❌ مهمة #{task_id} فشلت نهائيًا: {result.get('message')}"
                                )
                            else:
                                db.update_task(
                                    task_id,
                                    "pending",
                                    result.get("message")
                                )
                                logger.warning(
                                    f"Task {task_id} failed, will retry "
                                    f"({retries + 1}/{Config.MAX_RETRIES})"
                                )

                    except Exception as e:
                        error_msg = str(e)
                        logger.exception(f"Task {task_id} execution error")

                        if retries >= Config.MAX_RETRIES - 1:
                            db.update_task(task_id, "failed", error_msg)
                            self._send_notification(f"❌ مهمة #{task_id} فشلت: {error_msg}")
                        else:
                            db.update_task(task_id, "pending", error_msg)

                    time.sleep(2)  # تأخير بين المهام

                time.sleep(10)  # فحص كل 10 ثواني

            except Exception as e:
                logger.error(f"Task worker error: {e}")
                time.sleep(30)

    def _scheduler_worker(self):
        """خيط المجدول"""
        logger.info("Scheduler worker started")
        scheduler.run()

    def start(self):
        """تشغيل الوكيل"""
        # التحقق من الإعدادات
        missing = Config.validate()
        if missing:
            logger.error(f"Missing required environment variables: {missing}")
            print(f"❌ المتغيرات البيئية المفقودة: {missing}")
            sys.exit(1)

        self._running = True

        # إرسال إشعار بدء التشغيل
        try:
            self._send_notification(
                "🚀 <b>KODA-7 Started</b>\nالوكيل يعمل الآن وينتظر الأوامر."
            )
        except Exception as e:
            logger.warning(f"Could not send startup notification: {e}")

        # تشغيل الخيوط الخلفية
        task_thread = threading.Thread(target=self._task_worker, daemon=True)
        task_thread.start()

        scheduler_thread = threading.Thread(
            target=self._scheduler_worker, daemon=True
        )
        scheduler_thread.start()

        logger.info("KODA-7 Agent started successfully")
        print("🤖 KODA-7 Agent is running...")

        # تشغيل البوت
        try:
            self.bot.polling(none_stop=True, interval=1, timeout=60)
        except Exception as e:
            logger.error(f"Bot polling error: {e}")
            self._running = False
            scheduler.stop()
            raise

    def stop(self):
        """إيقاف الوكيل"""
        self._running = False
        scheduler.stop()
        logger.info("KODA-7 Agent stopped")


if __name__ == "__main__":
    agent = KODA7Agent()
    try:
        agent.start()
    except KeyboardInterrupt:
        print("\n🛑 Stopping KODA-7...")
        agent.stop()
    except Exception as e:
        logger.exception("Fatal error")
        agent.stop()
        sys.exit(1)

