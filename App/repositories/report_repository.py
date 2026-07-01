import os
import sqlite3
from datetime import datetime
from pathlib import Path

from app_settings import DATABASE_DIR, DATABASE_PATH, REPORTED_IMAGE_DIR, DETECTED_FRAME_DIR
from utils.time_utils import format_video_time


class ReportRepository:
    """Lớp thao tác SQLite cho cả user app và admin app."""

    def __init__(self, database_path=DATABASE_PATH):
        self.database_path = database_path

    def ensure_folders(self):
        os.makedirs(DATABASE_DIR, exist_ok=True)
        os.makedirs(REPORTED_IMAGE_DIR, exist_ok=True)
        os.makedirs(DETECTED_FRAME_DIR, exist_ok=True)

    def ensure_column(self, cursor, table_name, column_name, column_definition):
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [column[1] for column in cursor.fetchall()]

        if column_name not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")

    def init_database(self):
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pothole_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT,
                latitude REAL,
                longitude REAL,
                image_count INTEGER DEFAULT 1,
                created_at TEXT,
                status TEXT DEFAULT 'pending',
                analysis_html TEXT,
                reporter_user_id INTEGER
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pothole_report_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                image_path TEXT,
                image_name TEXT,
                detected_image_path TEXT,
                analysis_html TEXT,
                area_m2 REAL DEFAULT 0,
                setup_name TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (report_id) REFERENCES pothole_reports(id)
            )
        """)

        cursor.execute("PRAGMA table_info(pothole_report_images)")
        image_columns = [col[1] for col in cursor.fetchall()]

        if "detected_image_path" not in image_columns:
            cursor.execute("ALTER TABLE pothole_report_images ADD COLUMN detected_image_path TEXT")

        if "analysis_html" not in image_columns:
            cursor.execute("ALTER TABLE pothole_report_images ADD COLUMN analysis_html TEXT")

        if "area_m2" not in image_columns:
            cursor.execute("ALTER TABLE pothole_report_images ADD COLUMN area_m2 REAL DEFAULT 0")

        if "setup_name" not in image_columns:
            cursor.execute("ALTER TABLE pothole_report_images ADD COLUMN setup_name TEXT")

        conn.commit()
        conn.close()

    def get_all_reports(self):
        if not os.path.exists(self.database_path):
            return []

        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, address, latitude, longitude, image_count, created_at
            FROM pothole_reports
            ORDER BY id DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "id": row[0],
                "address": row[1],
                "latitude": row[2],
                "longitude": row[3],
                "image_count": row[4],
                "created_at": row[5],
            }
            for row in rows
        ]

    def get_all_report_locations(self):
        if not os.path.exists(self.database_path):
            return []

        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                id,
                latitude,
                longitude,
                address,
                image_count
            FROM pothole_reports
            ORDER BY id DESC
        """)

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "id": row[0],
                "latitude": row[1],
                "longitude": row[2],
                "address": row[3],
                "image_count": row[4],
            }
            for row in rows
        ]
        
    def increase_image_count(self, report_id):
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE pothole_reports
            SET image_count = image_count + 1
            WHERE id = ?
        """, (report_id,))

        conn.commit()
        conn.close()
    
    def create_video_report(self, latitude, longitude, confidence, frame_time, image_path, video_path,road_name, analysis_html):
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_text = format_video_time(frame_time)
        video_name = Path(video_path).name if video_path else None

        address = (
            f"Tuyến đường: {road_name}\n"
            f"Nguồn: Video {video_name}\n"
            f"Thời điểm video: {time_text}"
        )

        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pothole_reports (
                address,
                latitude,
                longitude,
                image_count,
                status,
                created_at,
                video_name,
                frame_time,
                confidence,
                gps_source,
                report_type,
                analysis_html
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            address,
            latitude,
            longitude,
            1,
            "pending",
            created_at,
            video_name,
            frame_time,
            confidence,
            "csv_simulated",
            "video_detection",
            analysis_html,
        ))

        report_id = cursor.lastrowid
        self._insert_report_image(cursor, report_id, image_path)

        conn.commit()
        conn.close()
        return report_id

    def create_manual_report(self, address, latitude, longitude, image_count):
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pothole_reports (
                address,
                latitude,
                longitude,
                image_count,
                status,
                created_at,
                gps_source,
                report_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            address,
            latitude,
            longitude,
            image_count,
            "pending",
            created_at,
            "manual",
            "manual_report"
        ))

        report_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return report_id, created_at

    def add_report_image(self, report_id, image_path):
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        self._insert_report_image(cursor, report_id, image_path)
        conn.commit()
        conn.close()

    def _insert_report_image(self, cursor, report_id, image_path):
        cursor.execute("""
            INSERT INTO pothole_report_images (
                report_id,
                image_path,
                image_name
            )
            VALUES (?, ?, ?)
        """, (
            report_id,
            image_path,
            os.path.basename(image_path)
        ))
        
    # def ensure_report_image_analysis_column():
    #     conn = sqlite3.connect(DATABASE_PATH)
    #     cursor = conn.cursor()

    #     cursor.execute("PRAGMA table_info(pothole_report_images)")
    #     columns = [column[1] for column in cursor.fetchall()]

    #     if "analysis_json" not in columns:
    #         cursor.execute("""
    #             ALTER TABLE pothole_report_images
    #             ADD COLUMN analysis_json TEXT
    #         """)

    #     if "detected_image_path" not in columns:
    #         cursor.execute("""
    #             ALTER TABLE pothole_report_images
    #             ADD COLUMN detected_image_path TEXT
    #         """)

    #     conn.commit()
    #     conn.close()
        
    # def ensure_report_detail_columns(self):
    #     conn = sqlite3.connect(self.database_path)
    #     cursor = conn.cursor()

    #     cursor.execute("PRAGMA table_info(pothole_report_images)")
    #     columns = [column[1] for column in cursor.fetchall()]

    #     if "detected_image_path" not in columns:
    #         cursor.execute("""
    #             ALTER TABLE pothole_report_images
    #             ADD COLUMN detected_image_path TEXT
    #         """)

    #     if "analysis_html" not in columns:
    #         cursor.execute("""
    #             ALTER TABLE pothole_report_images
    #             ADD COLUMN analysis_html TEXT
    #         """)

    #     if "area_m2" not in columns:
    #         cursor.execute("""
    #             ALTER TABLE pothole_report_images
    #             ADD COLUMN area_m2 REAL DEFAULT 0
    #         """)

    #     if "setup_name" not in columns:
    #         cursor.execute("""
    #             ALTER TABLE pothole_report_images
    #             ADD COLUMN setup_name TEXT
    #         """)

    #     conn.commit()
    #     conn.close()