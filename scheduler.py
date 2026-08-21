"""
KODA-7 Cron Scheduler
نظام المهام المجدولة باستخدام croniter
"""
import time
import logging
from datetime import datetime
from typing import List, Dict, Any
from croniter import croniter
from db import db
from config import Config

logger = logging.getLogger(__name__)

class TaskScheduler:
    """مجدول المهام - يتحقق كل دقيقة من المهام المستحقة"""

    def __init__(self):
        self.running = False
        self.interval = Config.SCHEDULER_INTERVAL

    def get_next_run(self, cron_expr: str, base_time: datetime = None) -> datetime:
        """حساب التشغيل التالي لمهمة مجدولة"""
        try:
            itr = croniter(cron_expr, base_time or datetime.now())
            return itr.get_next(datetime)
        except Exception as e:
            logger.error(f"Invalid cron expression '{cron_expr}': {e}")
            return None

    def check_due_jobs(self) -> List[Dict[str, Any]]:
        """التحقق من المهام المستحقة وإضافتها إلى قائمة المهام"""
        due_jobs = []
        now = datetime.now()

        try:
            jobs = db.get_active_cron_jobs()
            for job in jobs:
                try:
                    cron_expr = job["cron_expr"]
                    last_run = job["last_run"]

                    # تحويل last_run إلى datetime إذا لزم
                    if last_run:
                        try:
                            last_run_dt = datetime.fromisoformat(last_run.replace('Z', '+00:00'))
                        except:
                            last_run_dt = None
                    else:
                        last_run_dt = None

                    # حساب التشغيل التالي
                    next_run = self.get_next_run(cron_expr, last_run_dt or datetime.min)

                    if next_run and next_run <= now:
                        # المهمة مستحقة
                        due_jobs.append(job)

                        # إضافة إلى قائمة المهام
                        task_id = db.add_task(
                            platform=job["platform"],
                            action=job["action"],
                            params=json.loads(job["params"] or "{}")
                        )

                        # تحديث توقيت آخر تشغيل
                        next_next_run = self.get_next_run(cron_expr, now)
                        db.update_cron_job(
                            job_id=job["id"],
                            last_run=now.isoformat(),
                            next_run=next_next_run.isoformat() if next_next_run else None
                        )

                        logger.info(f"Cron job {job['id']} triggered, task {task_id} created")

                except Exception as e:
                    logger.error(f"Error processing cron job {job['id']}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Scheduler check failed: {e}")

        return due_jobs

    def run(self):
        """حلقة المجدول الرئيسية"""
        self.running = True
        logger.info("Task scheduler started")

        while self.running:
            try:
                due = self.check_due_jobs()
                if due:
                    logger.info(f"Triggered {len(due)} scheduled tasks")
                time.sleep(self.interval)
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                time.sleep(self.interval)

    def stop(self):
        """إيقاف المجدول"""
        self.running = False
        logger.info("Task scheduler stopped")

# Singleton instance
scheduler = TaskScheduler()
