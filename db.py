"""
KODA-7 Database Layer
طبقة قاعدة البيانات SQLite - جميع العمليات مركزية هنا
"""
import sqlite3
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from config import Config

logger = logging.getLogger(__name__)

class Database:
    """مدير قاعدة البيانات الموحد"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DB_PATH
        self._init_db()

    @contextmanager
    def _connect(self):
        """سياق الاتصال بقاعدة البيانات"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"DB error: {e}")
            raise
        finally:
            conn.close()

    def _init_db(self):
        """تهيئة الجداول"""
        with self._connect() as conn:
            cursor = conn.cursor()

            # جلسات المنصات
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    username TEXT,
                    credentials TEXT,
                    session_data TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(platform, username)
                )
            """)

            # المهام
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    action TEXT NOT NULL,
                    params TEXT,
                    status TEXT DEFAULT 'pending',
                    retries INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    error_msg TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    executed_at TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)

            # المهام المجدولة (cron)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cron_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cron_expr TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    action TEXT NOT NULL,
                    params TEXT,
                    is_active INTEGER DEFAULT 1,
                    last_run TIMESTAMP,
                    next_run TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # العمليات المعلقة
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    step TEXT NOT NULL,
                    data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)

            # السجلات (logs)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    source TEXT,
                    message TEXT NOT NULL,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # المحادثات
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
            logger.info("Database initialized successfully")

    def save_session(self, platform: str, username: str, credentials: dict, 
                     session_data: dict, status: str = "active") -> bool:
        try:
            with self._connect() as conn:
                conn.execute("""
                    INSERT INTO sessions (platform, username, credentials, session_data, status)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(platform, username) DO UPDATE SET
                        credentials=excluded.credentials,
                        session_data=excluded.session_data,
                        status=excluded.status,
                        updated_at=CURRENT_TIMESTAMP
                """, (platform, username, json.dumps(credentials), json.dumps(session_data), status))
                return True
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            return False

    def get_session(self, platform: str, username: str = None) -> Optional[Dict[str, Any]]:
        try:
            with self._connect() as conn:
                if username:
                    row = conn.execute(
                        "SELECT * FROM sessions WHERE platform=? AND username=? AND status='active'",
                        (platform, username)
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT * FROM sessions WHERE platform=? AND status='active' ORDER BY updated_at DESC LIMIT 1",
                        (platform,)
                    ).fetchone()
                if row:
                    return {
                        "id": row["id"],
                        "platform": row["platform"],
                        "username": row["username"],
                        "credentials": json.loads(row["credentials"] or "{}"),
                        "session_data": json.loads(row["session_data"] or "{}"),
                        "status": row["status"]
                    }
                return None
        except Exception as e:
            logger.error(f"Failed to get session: {e}")
            return None

    def update_session_status(self, platform: str, username: str, status: str) -> bool:
        try:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE sessions SET status=?, updated_at=CURRENT_TIMESTAMP WHERE platform=? AND username=?",
                    (status, platform, username)
                )
                return True
        except Exception as e:
            logger.error(f"Failed to update session status: {e}")
            return False

    def add_task(self, platform: str, action: str, params: dict) -> int:
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "INSERT INTO tasks (platform, action, params, status) VALUES (?, ?, ?, 'pending')",
                    (platform, action, json.dumps(params))
                )
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to add task: {e}")
            return -1

    def get_pending_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT * FROM tasks 
                       WHERE status IN ('pending', 'failed') 
                       AND retries < max_retries 
                       ORDER BY created_at ASC LIMIT ?""",
                    (limit,)
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get pending tasks: {e}")
            return []

    def update_task(self, task_id: int, status: str, error_msg: str = None) -> bool:
        try:
            with self._connect() as conn:
                if status == "running":
                    conn.execute(
                        "UPDATE tasks SET status=?, retries=retries+1, executed_at=CURRENT_TIMESTAMP WHERE id=?",
                        (status, task_id)
                    )
                elif status in ("completed", "failed"):
                    conn.execute(
                        "UPDATE tasks SET status=?, error_msg=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
                        (status, error_msg, task_id)
                    )
                else:
                    conn.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
                return True
        except Exception as e:
            logger.error(f"Failed to update task: {e}")
            return False

    def add_cron_job(self, cron_expr: str, platform: str, action: str, params: dict) -> int:
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "INSERT INTO cron_jobs (cron_expr, platform, action, params) VALUES (?, ?, ?, ?)",
                    (cron_expr, platform, action, json.dumps(params))
                )
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to add cron job: {e}")
            return -1

    def get_active_cron_jobs(self) -> List[Dict[str, Any]]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM cron_jobs WHERE is_active=1"
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get cron jobs: {e}")
            return []

    def update_cron_job(self, job_id: int, last_run: str, next_run: str) -> bool:
        try:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE cron_jobs SET last_run=?, next_run=? WHERE id=?",
                    (last_run, next_run, job_id)
                )
                return True
        except Exception as e:
            logger.error(f"Failed to update cron job: {e}")
            return False

    def delete_cron_job(self, job_id: int) -> bool:
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM cron_jobs WHERE id=?", (job_id,))
                return True
        except Exception as e:
            logger.error(f"Failed to delete cron job: {e}")
            return False

    def set_pending(self, user_id: str, platform: str, step: str, data: dict, 
                    expires_minutes: int = 10) -> bool:
        try:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM pending WHERE user_id=? AND platform=?",
                    (user_id, platform)
                )
                conn.execute("""
                    INSERT INTO pending (user_id, platform, step, data, expires_at)
                    VALUES (?, ?, ?, ?, datetime('now', '+{} minutes'))
                """.format(expires_minutes), (user_id, platform, step, json.dumps(data)))
                return True
        except Exception as e:
            logger.error(f"Failed to set pending: {e}")
            return False

    def get_pending(self, user_id: str, platform: str) -> Optional[Dict[str, Any]]:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """SELECT * FROM pending 
                       WHERE user_id=? AND platform=? 
                       AND expires_at > datetime('now')""",
                    (user_id, platform)
                ).fetchone()
                if row:
                    return {
                        "id": row["id"],
                        "step": row["step"],
                        "data": json.loads(row["data"] or "{}"),
                        "created_at": row["created_at"]
                    }
                return None
        except Exception as e:
            logger.error(f"Failed to get pending: {e}")
            return None

    def clear_pending(self, user_id: str, platform: str) -> bool:
        try:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM pending WHERE user_id=? AND platform=?",
                    (user_id, platform)
                )
                return True
        except Exception as e:
            logger.error(f"Failed to clear pending: {e}")
            return False

    def add_log(self, level: str, message: str, source: str = None, details: str = None) -> bool:
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO logs (level, source, message, details) VALUES (?, ?, ?, ?)",
                    (level, source, message, details)
                )
                return True
        except Exception as e:
            logger.error(f"Failed to add log: {e}")
            return False

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM logs ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get logs: {e}")
            return []

    def add_message(self, user_id: str, role: str, content: str) -> bool:
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO conversations (user_id, role, content) VALUES (?, ?, ?)",
                    (user_id, role, content)
                )
                return True
        except Exception as e:
            logger.error(f"Failed to add message: {e}")
            return False

    def get_conversation(self, user_id: str, limit: int = 20) -> List[Dict[str, str]]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT role, content FROM conversations 
                       WHERE user_id=? ORDER BY created_at DESC LIMIT ?""",
                    (user_id, limit)
                ).fetchall()
                return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
        except Exception as e:
            logger.error(f"Failed to get conversation: {e}")
            return []

# Singleton instance
db = Database()
