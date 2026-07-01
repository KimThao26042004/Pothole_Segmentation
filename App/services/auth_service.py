import os
import sqlite3
import hashlib
import hmac
from datetime import datetime

from app_settings import DATABASE_PATH


class AuthService:
    def __init__(self, database_path=DATABASE_PATH):
        self.database_path = database_path
        self.ensure_tables()

    def connect(self):
        return sqlite3.connect(self.database_path)

    def ensure_column(self, cursor, table_name, column_name, column_definition):
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]

        if column_name not in columns:
            cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
            )

    def ensure_tables(self):
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                full_name TEXT,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT
            )
        """)

        # Gắn người gửi báo cáo vào bảng report
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pothole_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT,
                latitude REAL,
                longitude REAL,
                image_count INTEGER DEFAULT 1,
                created_at TEXT,
                status TEXT DEFAULT 'pending',
                analysis_html TEXT
            )
        """)

        self.ensure_column(
            cursor,
            "pothole_reports",
            "reporter_user_id",
            "INTEGER"
        )

        self.ensure_column(
            cursor,
            "pothole_reports",
            "manager_note",
            "TEXT"
        )

        conn.commit()
        conn.close()

    def hash_password(self, password, salt=None):
        if salt is None:
            salt = os.urandom(16).hex()

        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            200000,
        ).hex()

        return password_hash, salt

    def verify_password(self, password, password_hash, salt):
        new_hash, _ = self.hash_password(password, salt)
        return hmac.compare_digest(new_hash, password_hash)

    def create_user(self, username, password, email="", full_name="", role="user"):
        username = str(username or "").strip()
        email = str(email or "").strip()
        full_name = str(full_name or "").strip()
        role = str(role or "user").strip().lower()

        if role not in ["user", "manager"]:
            raise ValueError("Role không hợp lệ. Chỉ dùng user hoặc manager.")

        if not username:
            raise ValueError("Vui lòng nhập tên đăng nhập.")

        if len(password or "") < 6:
            raise ValueError("Mật khẩu phải có ít nhất 6 ký tự.")

        password_hash, salt = self.hash_password(password)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = self.connect()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO users (
                    username,
                    email,
                    full_name,
                    password_hash,
                    salt,
                    role,
                    is_active,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                username,
                email or None,
                full_name,
                password_hash,
                salt,
                role,
                1,
                created_at,
            ))

            conn.commit()
            return cursor.lastrowid

        except sqlite3.IntegrityError:
            raise ValueError("Tên đăng nhập hoặc email đã tồn tại.")

        finally:
            conn.close()

    def authenticate(self, username_or_email, password):
        username_or_email = str(username_or_email or "").strip()

        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                id,
                username,
                email,
                full_name,
                password_hash,
                salt,
                role,
                is_active
            FROM users
            WHERE username = ? OR email = ?
            LIMIT 1
        """, (
            username_or_email,
            username_or_email,
        ))

        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        (
            user_id,
            username,
            email,
            full_name,
            password_hash,
            salt,
            role,
            is_active,
        ) = row

        if not is_active:
            return None

        if not self.verify_password(password, password_hash, salt):
            return None

        return {
            "id": user_id,
            "username": username,
            "email": email or "",
            "full_name": full_name or "",
            "role": role,
        }

    def has_manager_account(self):
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*)
            FROM users
            WHERE role = 'manager'
        """)

        count = cursor.fetchone()[0]
        conn.close()

        return count > 0

    def seed_default_manager(self):
        """
        Tạo tài khoản quản lý mặc định nếu chưa có manager.
        Chỉ dùng cho demo. Sau đó nên đổi mật khẩu.
        """

        if self.has_manager_account():
            return

        self.create_user(
            username="manager",
            password="Manager@123",
            email="manager@example.com",
            full_name="Người quản lý",
            role="manager",
        )

    def get_user_by_id(self, user_id):
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, username, email, full_name, role, is_active
            FROM users
            WHERE id = ?
            LIMIT 1
        """, (user_id,))

        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        return {
            "id": row[0],
            "username": row[1],
            "email": row[2] or "",
            "full_name": row[3] or "",
            "role": row[4],
            "is_active": row[5],
        }