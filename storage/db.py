"""
SQLite Database - 對話、排程、設定
"""

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class Database:
    """SQLite 資料庫"""
    
    def __init__(self, db_path: str = "./data/agent.db"):
        self.db_path = db_path
        self.conn = None
        
        # 建立目錄
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    def connect(self):
        """連接資料庫"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            self._init_tables()
    
    def close(self):
        """關閉連接"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def _init_tables(self):
        """初始化資料表"""
        cursor = self.conn.cursor()
        
        # 對話歷史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                message TEXT NOT NULL,
                response TEXT,
                intent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 排程表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                cron_expression TEXT NOT NULL,
                func_name TEXT NOT NULL,
                func_args TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_run TIMESTAMP,
                next_run TIMESTAMP
            )
        """)
        
        # 設定表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 使用者偏好表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT PRIMARY KEY,
                preferences TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.commit()
    
    # ===== 對話歷史 =====
    
    def add_conversation(self, user_id: str, message: str, response: str = None, intent: str = None) -> int:
        """新增對話記錄"""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO conversations (user_id, message, response, intent) VALUES (?, ?, ?, ?)",
            (user_id, message, response, intent)
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def get_conversations(self, user_id: str, limit: int = 50) -> List[Dict]:
        """取得對話歷史"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM conversations WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def clear_conversations(self, user_id: str):
        """清除對話歷史"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
        self.conn.commit()
    
    # ===== 排程 =====
    
    def add_schedule(self, job_id: str, name: str, cron_expression: str, func_name: str, func_args: Dict = None) -> int:
        """新增排程"""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO schedules (job_id, name, cron_expression, func_name, func_args) VALUES (?, ?, ?, ?, ?)",
            (job_id, name, cron_expression, func_name, json.dumps(func_args or {}))
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def get_schedules(self) -> List[Dict]:
        """取得所有排程"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM schedules ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def update_schedule(self, job_id: str, **kwargs):
        """更新排程"""
        fields = []
        values = []
        
        for key, value in kwargs.items():
            fields.append(f"{key} = ?")
            values.append(value)
        
        if fields:
            values.append(job_id)
            cursor = self.conn.cursor()
            cursor.execute(
                f"UPDATE schedules SET {', '.join(fields)} WHERE job_id = ?",
                values
            )
            self.conn.commit()
    
    def delete_schedule(self, job_id: str):
        """刪除排程"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM schedules WHERE job_id = ?", (job_id,))
        self.conn.commit()
    
    # ===== 設定 =====
    
    def set_setting(self, key: str, value: str):
        """設定值"""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, datetime.now().isoformat())
        )
        self.conn.commit()
    
    def get_setting(self, key: str, default: str = None) -> Optional[str]:
        """取得設定值"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default
    
    def get_all_settings(self) -> Dict[str, str]:
        """取得所有設定"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in cursor.fetchall()}
    
    # ===== 使用者偏好 =====
    
    def set_user_preference(self, user_id: str, preferences: Dict):
        """設定使用者偏好"""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO user_preferences (user_id, preferences, updated_at) VALUES (?, ?, ?)",
            (user_id, json.dumps(preferences), datetime.now().isoformat())
        )
        self.conn.commit()
    
    def get_user_preference(self, user_id: str) -> Dict:
        """取得使用者偏好"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT preferences FROM user_preferences WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return json.loads(row["preferences"]) if row else {}
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()