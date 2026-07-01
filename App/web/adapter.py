"""
Adapter cho web Gradio.

Nhiệm vụ của file này:
- Nhận input từ giao diện web.
- Gọi service xử lý ảnh/video/realtime.
- Chuẩn hóa kết quả để trả về cho Gradio.
- Quản lý GPS sidecar, marker phát hiện, báo cáo gửi admin.

Lưu ý refactor:
- Không render map trực tiếp trong file này nữa. Map đã chuyển sang `web.map_service`.
- Các phần bị trùng với `web_map.py` cũ đã được comment/gỡ khỏi adapter để tránh sửa một chức năng ở nhiều nơi.
"""

import html
import os
import sqlite3
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app_settings import DATABASE_PATH, HOMOGRAPHY_DIR, MODEL_PATH
from services.analysis_service import PotholeAnalysisService
from services.gps_service import GPSService
from user.view_helpers import build_analysis_html
from utils.geo_utils import haversine
from utils.time_utils import format_video_time

from web.config import (
    CAMERA_SETUPS,
    DEFAULT_SETUP_DISPLAY_NAME,
    GPS_SEARCH_DIRS,
    MAX_VIDEO_SECONDS,
    SAME_POTHOLE_RADIUS_M,
    VIDEO_FRAME_STEP,
    WEB_GPS_DIR,
    WEB_IMAGE_OUTPUT_DIR,
    WEB_VIDEO_OUTPUT_DIR,
    WEBRTC_ANALYZE_EVERY,
    WEBRTC_MAX_WIDTH,
)
from web.map_service import (
    has_valid_gps,
    refresh_map,
    render_map_html,
)


Marker = Dict[str, Any]
Point = List[float]


# ============================================================
# 1. SERVICE PHÂN TÍCH
# ============================================================

_analysis_service: Optional[PotholeAnalysisService] = None


def get_analysis_service() -> PotholeAnalysisService:
    """Load YOLO/depth model một lần, dùng lại cho ảnh/video/realtime."""
    global _analysis_service

    if _analysis_service is None:
        _analysis_service = PotholeAnalysisService(MODEL_PATH, depth_interval=10)
        _analysis_service.load_model_if_needed()

    return _analysis_service


def get_setup_name(setup_display_name: str) -> str:
    """Đổi tên setup hiển thị trên web sang tên file homography."""
    if not setup_display_name:
        setup_display_name = DEFAULT_SETUP_DISPLAY_NAME

    return CAMERA_SETUPS.get(setup_display_name, CAMERA_SETUPS[DEFAULT_SETUP_DISPLAY_NAME])


def check_homography_exists(setup_name: str) -> None:
    """Kiểm tra file homography .npy có tồn tại không."""
    homography_path = Path(HOMOGRAPHY_DIR) / f"{setup_name}.npy"

    if not homography_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file homography cho setup: {setup_name}\n"
            f"Đường dẫn cần có: {homography_path}"
        )


def save_result_image(frame_bgr, prefix="image_result") -> str:
    """Lưu ảnh kết quả để Gradio hiển thị ở output image."""
    timestamp = int(time.time() * 1000)
    output_path = WEB_IMAGE_OUTPUT_DIR / f"{prefix}_{timestamp}.jpg"
    cv2.imwrite(str(output_path), frame_bgr)
    return str(output_path)


# ============================================================
# 2. BÁO CÁO WEB GIỐNG APP PYQT5
# ============================================================

def ensure_report_column(cursor, table_name: str, column_name: str, column_definition: str) -> None:
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]

    if column_name not in columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def ensure_report_tables_for_web(cursor) -> None:
    """Tạo/bổ sung bảng báo cáo để web lưu giống app PyQt5."""

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pothole_report_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER,
            image_path TEXT,
            image_name TEXT,
            detected_image_path TEXT,
            analysis_html TEXT,
            area_m2 REAL DEFAULT 0,
            setup_name TEXT,
            FOREIGN KEY(report_id) REFERENCES pothole_reports(id)
        )
    """)

    ensure_report_column(cursor, "pothole_reports", "analysis_html", "TEXT")
    ensure_report_column(cursor, "pothole_reports", "status", "TEXT DEFAULT 'pending'")
    ensure_report_column(cursor, "pothole_reports", "image_count", "INTEGER DEFAULT 1")

    ensure_report_column(cursor, "pothole_report_images", "image_name", "TEXT")
    ensure_report_column(cursor, "pothole_report_images", "detected_image_path", "TEXT")
    ensure_report_column(cursor, "pothole_report_images", "analysis_html", "TEXT")
    ensure_report_column(cursor, "pothole_report_images", "area_m2", "REAL DEFAULT 0")
    ensure_report_column(cursor, "pothole_report_images", "setup_name", "TEXT")


def save_report_frame_to_file(frame_bgr, media_path="media", suffix="original") -> str:
    """Lưu frame/ảnh báo cáo vào database/reported_frames."""

    report_dir = Path(DATABASE_PATH).parent / "reported_frames"
    report_dir.mkdir(parents=True, exist_ok=True)

    media_stem = Path(str(media_path or "media")).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    file_path = report_dir / f"{media_stem}_{timestamp}_{suffix}.jpg"
    cv2.imwrite(str(file_path), frame_bgr)

    return str(file_path)


def find_nearby_pothole_report_web(lat, lng, radius_m=SAME_POTHOLE_RADIUS_M):
    """Tìm báo cáo cũ gần vị trí hiện tại trong bán kính radius_m."""

    if not os.path.exists(DATABASE_PATH):
        return None, None

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        ensure_report_tables_for_web(cursor)

        cursor.execute("""
            SELECT id, latitude, longitude
            FROM pothole_reports
            WHERE latitude IS NOT NULL
              AND longitude IS NOT NULL
        """)

        rows = cursor.fetchall()
        conn.commit()
    finally:
        conn.close()

    nearest_report = None
    nearest_distance = None

    for report_id, old_lat, old_lng in rows:
        if old_lat is None or old_lng is None:
            continue

        distance = haversine(float(lat), float(lng), float(old_lat), float(old_lng))

        if distance <= radius_m:
            if nearest_distance is None or distance < nearest_distance:
                nearest_distance = distance
                nearest_report = {
                    "id": report_id,
                    "latitude": old_lat,
                    "longitude": old_lng,
                }

    return nearest_report, nearest_distance


def add_report_image_detail_web(
    report_id,
    original_image_path,
    detected_image_path,
    analysis_html,
    area_m2,
    setup_name,
) -> None:
    """Thêm 1 ảnh/frame vào báo cáo có sẵn."""

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        ensure_report_tables_for_web(cursor)

        cursor.execute("""
            INSERT INTO pothole_report_images (
                report_id,
                image_path,
                image_name,
                detected_image_path,
                analysis_html,
                area_m2,
                setup_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            report_id,
            original_image_path,
            os.path.basename(original_image_path),
            detected_image_path,
            analysis_html,
            area_m2,
            setup_name,
        ))

        cursor.execute("""
            UPDATE pothole_reports
            SET image_count = COALESCE(image_count, 0) + 1
            WHERE id = ?
        """, (report_id,))

        conn.commit()
    finally:
        conn.close()


def create_report_with_detail_web(
    latitude,
    longitude,
    confidence,
    frame_time,
    original_image_path,
    detected_image_path,
    media_path,
    media_type,
    road_name,
    analysis_html,
    area_m2,
    setup_name,
):
    """Tạo báo cáo mới và ảnh/frame đầu tiên."""

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_text = "Video" if media_type == "video" else "Ảnh"

    address = (
        f"Tuyến đường: {road_name} "
        f"Nguồn: {source_text} {os.path.basename(str(media_path or 'media'))} "
        f"Thời điểm video: {format_video_time(float(frame_time or 0))}"
    )

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        ensure_report_tables_for_web(cursor)

        cursor.execute("""
            INSERT INTO pothole_reports (
                address,
                latitude,
                longitude,
                image_count,
                created_at,
                status,
                analysis_html
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            address,
            latitude,
            longitude,
            1,
            created_at,
            "pending",
            analysis_html,
        ))

        report_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO pothole_report_images (
                report_id,
                image_path,
                image_name,
                detected_image_path,
                analysis_html,
                area_m2,
                setup_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            report_id,
            original_image_path,
            os.path.basename(original_image_path),
            detected_image_path,
            analysis_html,
            area_m2,
            setup_name,
        ))

        conn.commit()
    finally:
        conn.close()

    return report_id, created_at


def get_marker_report_items(marker: Marker) -> List[Marker]:
    """
    Lấy danh sách ảnh/frame của marker.

    Nếu marker cũ chưa có report_items thì tạo 1 item từ chính marker để tương thích.
    """
    items = marker.get("report_items")

    if items:
        return items

    return [{
        "original_image_path": marker.get("original_image_path", ""),
        "detected_image_path": marker.get("detected_image_path", ""),
        "analysis_html": marker.get("analysis_html", ""),
        "area_m2": marker.get("area_m2", 0),
        "setup_name": marker.get("setup_name", ""),
        "confidence": marker.get("confidence", 0),
        "frame_index": marker.get("frame_index", 0),
        "time_sec": marker.get("time_sec", 0),
        "time_text": marker.get("time_text", ""),
        "media_path": marker.get("media_path", ""),
        "media_type": marker.get("media_type", ""),
        "road_name": marker.get("road_name", "Chưa xác định"),
    }]


def submit_latest_report_to_admin(detected_markers, route_points, current_lat, current_lng):
    """
    Nút Báo cáo trên web.

    - Lấy marker ổ gà mới nhất.
    - Nếu gần báo cáo cũ trong 2m thì thêm ảnh/frame vào báo cáo cũ.
    - Nếu chưa có thì tạo báo cáo mới.
    - Nếu marker đã gộp nhiều lần chụp trong phạm vi 2m, gửi tất cả ảnh/frame trong marker đó.
    """

    detected_markers = detected_markers or []
    route_points = route_points or []

    if not detected_markers:
        return (
            refresh_map(detected_markers, route_points, current_lat, current_lng),
            "Chưa có ổ gà nào để báo cáo. Hãy phân tích ảnh/video trước.",
            detected_markers,
        )

    marker = detected_markers[-1]

    if marker.get("is_reported"):
        return (
            refresh_map(detected_markers, route_points, current_lat, current_lng),
            "Báo cáo này đã được gửi trước đó.",
            detected_markers,
        )

    try:
        lat = float(marker.get("lat"))
        lng = float(marker.get("lng"))
    except Exception:
        return (
            refresh_map(detected_markers, route_points, current_lat, current_lng),
            "Không gửi được báo cáo vì chưa có tọa độ hợp lệ.",
            detected_markers,
        )

    items = get_marker_report_items(marker)

    valid_items = []
    for item in items:
        original_image_path = item.get("original_image_path", "")
        detected_image_path = item.get("detected_image_path", "")

        if original_image_path and os.path.exists(original_image_path) and detected_image_path and os.path.exists(detected_image_path):
            valid_items.append(item)

    if not valid_items:
        return (
            refresh_map(detected_markers, route_points, current_lat, current_lng),
            "Không gửi được báo cáo vì không tìm thấy ảnh gốc hoặc ảnh đã phát hiện.",
            detected_markers,
        )

    try:
        nearby_report, distance = find_nearby_pothole_report_web(lat, lng, radius_m=SAME_POTHOLE_RADIUS_M)

        if nearby_report is not None:
            report_id = nearby_report["id"]

            for item in valid_items:
                add_report_image_detail_web(
                    report_id=report_id,
                    original_image_path=item.get("original_image_path", ""),
                    detected_image_path=item.get("detected_image_path", ""),
                    analysis_html=item.get("analysis_html", ""),
                    area_m2=float(item.get("area_m2", 0) or 0),
                    setup_name=item.get("setup_name", ""),
                )

            marker["is_reported"] = True
            marker["report_id"] = report_id

            return (
                refresh_map(detected_markers, route_points, current_lat, current_lng),
                f"Ổ gà đã tồn tại gần đó. Đã thêm {len(valid_items)} ảnh/frame vào báo cáo #{report_id}.",
                detected_markers,
            )

        first_item = valid_items[0]

        report_id, created_at = create_report_with_detail_web(
            latitude=lat,
            longitude=lng,
            confidence=float(first_item.get("confidence", marker.get("confidence", 0)) or 0),
            frame_time=float(first_item.get("time_sec", marker.get("time_sec", 0)) or 0),
            original_image_path=first_item.get("original_image_path", ""),
            detected_image_path=first_item.get("detected_image_path", ""),
            media_path=first_item.get("media_path", marker.get("media_path", "")),
            media_type=first_item.get("media_type", marker.get("media_type", "video")),
            road_name=first_item.get("road_name", marker.get("road_name", "Chưa xác định")),
            analysis_html=first_item.get("analysis_html", marker.get("analysis_html", "")),
            area_m2=float(first_item.get("area_m2", marker.get("area_m2", 0)) or 0),
            setup_name=first_item.get("setup_name", marker.get("setup_name", "")),
        )

        for item in valid_items[1:]:
            add_report_image_detail_web(
                report_id=report_id,
                original_image_path=item.get("original_image_path", ""),
                detected_image_path=item.get("detected_image_path", ""),
                analysis_html=item.get("analysis_html", ""),
                area_m2=float(item.get("area_m2", 0) or 0),
                setup_name=item.get("setup_name", ""),
            )

        marker["is_reported"] = True
        marker["report_id"] = report_id

        return (
            refresh_map(detected_markers, route_points, current_lat, current_lng),
            (
                f"Đã gửi báo cáo cho admin/cơ quan chức năng. "
                f"Mã báo cáo: #{report_id} | GPS {lat:.6f}, {lng:.6f} | "
                f"Số ảnh/frame: {len(valid_items)}"
            ),
            detected_markers,
        )

    except Exception as error:
        return (
            refresh_map(detected_markers, route_points, current_lat, current_lng),
            f"Lỗi gửi báo cáo: {error}",
            detected_markers,
        )


# ============================================================
# 3. GPS TỰ ĐỘNG THEO TÊN FILE
# ============================================================

def find_sidecar_gps_csv(media_path) -> Optional[str]:
    """
    Tự tìm GPS CSV theo tên ảnh/video.

    Ví dụ:
    pothole 8.jpg  -> pothole 8_gps.csv
    demo.mp4       -> demo_gps.csv

    Nơi tìm sau refactor:
    1. Cùng thư mục file media do Gradio lưu.
    2. App/web/gps_csv.
    3. App/web_gps_csv cũ.
    4. App hiện tại.
    5. Current working directory và current working directory/web_gps_csv.
    """

    if not media_path:
        return None

    media_path = Path(str(media_path))
    expected_name = f"{media_path.stem}_gps.csv"

    search_dirs = [
        media_path.parent,
        WEB_GPS_DIR,
        *GPS_SEARCH_DIRS,
        Path.cwd(),
        Path.cwd() / "web_gps_csv",
        Path.cwd() / "web" / "gps_csv",
    ]

    seen = set()

    for folder in search_dirs:
        try:
            folder = Path(folder)
            if folder in seen:
                continue
            seen.add(folder)

            if not folder.exists():
                continue

            direct_path = folder / expected_name
            if direct_path.exists():
                return str(direct_path)

            for csv_file in folder.glob("*.csv"):
                if csv_file.name.lower() == expected_name.lower():
                    return str(csv_file)

        except Exception:
            pass

    return None


def load_gps_csv_path(gps_csv_path):
    gps_service = GPSService()
    gps_points = gps_service.load_csv(gps_csv_path)

    route_points = [
        [point["latitude"], point["longitude"]]
        for point in gps_points
    ]

    lat, lng, road_name = gps_service.get_by_time(0)

    return gps_service, gps_points, lat, lng, road_name, route_points


def preview_media_gps_on_map(media_path, detected_markers=None, current_lat=None, current_lng=None):
    """
    Khi user vừa chọn ảnh/video:
    - Nếu tìm thấy file tên_media_gps.csv thì map lia tới CSV.
    - Nếu không có CSV nhưng đã lấy vị trí hiện tại thì map lia tới vị trí hiện tại.
    - Nếu không có gì thì giữ map bình thường.
    """

    detected_markers = detected_markers or []
    route_points: List[Point] = []

    if media_path is None:
        return refresh_map(detected_markers, route_points, current_lat, current_lng), route_points

    auto_gps_csv_path = find_sidecar_gps_csv(media_path)

    if auto_gps_csv_path:
        try:
            _, _, gps_lat, gps_lng, road_name, route_points = load_gps_csv_path(auto_gps_csv_path)

            if route_points and len(route_points) >= 2:
                map_html = render_map_html(
                    detected_markers=detected_markers,
                    route_points=route_points,
                    current_location=None,
                )
            else:
                map_html = render_map_html(
                    detected_markers=detected_markers,
                    route_points=route_points,
                    current_location={
                        "lat": float(gps_lat),
                        "lng": float(gps_lng),
                    },
                )

            return map_html, route_points

        except Exception as error:
            print("Không preview được GPS CSV:", error)

    return refresh_map(detected_markers, route_points, current_lat, current_lng), route_points


def build_gps_required_html(mode="ảnh", media_name="") -> str:
    if mode == "video":
        message = f"""
        <b>Không tìm thấy GPS CSV cho video.</b><br><br>
        Web đã tự tìm file theo dạng <b>tên_video_gps.csv</b> nhưng không thấy.<br>
        File đang phân tích: <b>{html.escape(media_name or "video")}</b><br><br>
        Bạn cần làm một trong hai cách:<br>
        1. Đặt file GPS CSV vào thư mục <b>App/web/gps_csv</b> hoặc <b>App/web_gps_csv</b> với đúng tên, ví dụ <b>demo_gps.csv</b>.<br>
        2. Hoặc bấm nút <b>📍 Lấy vị trí hiện tại</b> trước khi phân tích video.<br><br>
        Sau đó bấm lại <b>Phân tích video</b>.
        """
    else:
        message = f"""
        <b>Không tìm thấy GPS CSV cho ảnh.</b><br><br>
        Web đã tự tìm file theo dạng <b>tên_ảnh_gps.csv</b> nhưng không thấy.<br>
        File đang phân tích: <b>{html.escape(media_name or "ảnh")}</b><br><br>
        Bạn cần làm một trong hai cách:<br>
        1. Đặt file GPS CSV vào thư mục <b>App/web/gps_csv</b> hoặc <b>App/web_gps_csv</b> với đúng tên, ví dụ <b>pothole 8_gps.csv</b>.<br>
        2. Hoặc bấm nút <b>📍 Lấy vị trí hiện tại</b> trước khi phân tích ảnh.<br><br>
        Sau đó bấm lại <b>Phân tích ảnh</b>.
        """

    return f"""
    <div style="
        color:white;
        border:1px solid #ffcc00;
        padding:14px;
        background:#111111;
        border-radius:8px;
        font-size:15px;
        line-height:1.55;
    ">
        <div style="color:#ffcc00; font-weight:bold; font-size:17px;">
            YÊU CẦU GPS
        </div>
        <br>
        {message}
    </div>
    """


# ============================================================
# 4. HTML BẢNG PHÂN TÍCH TRÊN WEB
# ============================================================

def build_single_frame_html(analysis: dict, setup_name: str, frame_index: int = 0, time_sec: float = 0.0) -> str:
    has_pothole = analysis.get("has_pothole", False)
    confidence = float(analysis.get("confidence", 0.0) or 0.0)
    area_m2 = float(analysis.get("area_m2", 0.0) or 0.0)
    depth_info = analysis.get("depth_info")
    error = analysis.get("error")

    if not has_pothole or depth_info is None:
        return f"""
        <div style="
            border:1px solid #ffffff;
            padding:12px;
            margin-top:10px;
            color:white;
            background:#111111;
            font-size:15px;
        ">
            <b>KẾT QUẢ PHÂN TÍCH FRAME</b><br><br>
            <b>Setup camera:</b> {setup_name}<br>
            <b>Frame:</b> {frame_index}<br>
            <b>Thời gian video:</b> {time_sec:.2f} giây<br>
            <b>Phát hiện ổ gà:</b> {'Có' if has_pothole else 'Không'}<br>
            <b>Confidence:</b> {confidence:.3f}<br>
            <b>Diện tích:</b> {area_m2:.3f} m²<br><br>
            Chưa có dữ liệu nước / ánh sáng / độ sâu cho frame này.
        </div>
        """

    error_html = ""
    if error:
        error_html = f"""
        <br>
        <b style="color:#ffcc00;">Cảnh báo:</b> {html.escape(str(error))}
        """

    analysis_table = build_analysis_html(depth_info)

    return f"""
    <div style="
        border:1px solid #ffffff;
        padding:12px;
        margin-top:10px;
        color:white;
        background:#111111;
        font-size:15px;
    ">
        <b>KẾT QUẢ PHÂN TÍCH FRAME</b><br><br>
        <b>Setup camera:</b> {setup_name}<br>
        <b>Frame:</b> {frame_index}<br>
        <b>Thời gian video:</b> {time_sec:.2f} giây<br>
        <b>Phát hiện ổ gà:</b> Có<br>
        <b>Confidence:</b> {confidence:.3f}<br>
        <b>Diện tích:</b> {area_m2:.3f} m²
        {error_html}
    </div>

    <div style="
        margin-top:8px;
        border:1px solid #ffffff;
        background:#111111;
        color:white;
        font-size:15px;
    ">
        {analysis_table}
    </div>
    """


def build_video_all_frames_html(video_summary: dict, detected_frame_items: list) -> str:
    """Hiển thị tổng quan video và các frame có ổ gà."""

    setup_name = video_summary.get("setup_name", "")
    total_frames = video_summary.get("total_frames", 0)
    frames_read = video_summary.get("frames_read", 0)
    processed_frames = video_summary.get("processed_frames", 0)
    pothole_frames = video_summary.get("pothole_frames", 0)
    fps = float(video_summary.get("fps", 0) or 0)
    frame_step = video_summary.get("frame_step", 0)
    max_seconds = video_summary.get("max_seconds", 0)
    gps_source = video_summary.get("gps_source", "Chưa xác định")
    gps_csv_name = video_summary.get("gps_csv_name", "")

    html_result = f"""
    <div style="
        border:1px solid #ffffff;
        padding:12px;
        margin-top:10px;
        color:white;
        background:#111111;
        font-size:15px;
        width:100%;
        box-sizing:border-box;
    ">
        <b>KẾT QUẢ PHÂN TÍCH VIDEO</b><br><br>

        <b>Góc camera:</b> {setup_name}<br>
        <b>Nguồn GPS:</b> {gps_source}<br>
        <b>File GPS CSV:</b> {gps_csv_name or 'Không dùng'}<br>
        <b>Tổng frame video:</b> {total_frames}<br>
        <b>Số frame đã đọc:</b> {frames_read}<br>
        <b>Số frame được phân tích:</b> {processed_frames}<br>
        <b>Số frame phát hiện ổ gà:</b> {pothole_frames}<br>
        <b>FPS:</b> {fps:.2f}<br>
        <b>Giới hạn thời lượng web demo:</b> {max_seconds} giây<br>
        <b>Bước nhảy frame:</b> {frame_step}<br>
    </div>
    """

    if not detected_frame_items:
        html_result += """
        <div style="
            border:1px solid #ffffff;
            padding:12px;
            margin-top:10px;
            color:white;
            background:#111111;
            font-size:15px;
            width:100%;
            box-sizing:border-box;
        ">
            Không có frame nào đủ điều kiện để hiển thị thông tin nước / ánh sáng / độ sâu.
        </div>
        """
        return html_result

    html_result += """
    <div style="
        border:1px solid #ffffff;
        padding:12px;
        margin-top:10px;
        color:white;
        background:#111111;
        font-size:15px;
        width:100%;
        box-sizing:border-box;
    ">
        <b>DANH SÁCH FRAME CÓ Ổ GÀ</b><br>
        <span>Bấm vào từng frame để xem bảng thông tin giống phần phân tích ảnh.</span>
    </div>
    """

    for index, item in enumerate(detected_frame_items):
        frame_index = item["frame_index"]
        time_sec = item["time_sec"]
        confidence = item["confidence"]
        area_m2 = item["area_m2"]
        frame_html = item["frame_html"]
        open_attr = "open" if index == 0 else ""

        html_result += f"""
        <details {open_attr} style="
            border:1px solid #ffffff;
            margin-top:10px;
            background:#111111;
            color:white;
            font-size:15px;
            width:100%;
            box-sizing:border-box;
        ">
            <summary style="
                cursor:pointer;
                font-weight:bold;
                padding:12px;
                background:#111111;
                color:white;
                border-bottom:1px solid #ffffff;
            ">
                Frame {frame_index} | {time_sec:.2f}s | Confidence {confidence:.3f} | Diện tích {area_m2:.3f} m²
            </summary>

            <div style="
                padding:0;
                margin:0;
                width:100%;
                box-sizing:border-box;
            ">
                {frame_html}
            </div>
        </details>
        """

    return html_result


# ============================================================
# 5. MARKER MAP
# ============================================================

def get_water_text_from_depth_info(depth_info):
    if not depth_info:
        return "Chưa xác định"

    has_water = depth_info.get("has_water", False)
    return "Có nước" if has_water else "Không có nước"


def get_depth_level_from_depth_info(depth_info):
    if not depth_info:
        return "Chưa đánh giá"

    return depth_info.get("depth_level", "Chưa đánh giá")


def find_nearby_detected_marker_index(detected_markers, lat, lng, radius_m=SAME_POTHOLE_RADIUS_M):
    """Tìm marker phát hiện gần vị trí mới. Nếu <= radius_m thì xem là cùng 1 ổ gà."""

    if lat is None or lng is None:
        return None, None

    try:
        lat = float(lat)
        lng = float(lng)
    except Exception:
        return None, None

    nearest_index = None
    nearest_distance = None

    for index, marker in enumerate(detected_markers or []):
        old_lat = marker.get("lat")
        old_lng = marker.get("lng")

        if old_lat is None or old_lng is None:
            continue

        try:
            distance = haversine(lat, lng, float(old_lat), float(old_lng))
        except Exception:
            continue

        if distance <= radius_m:
            if nearest_distance is None or distance < nearest_distance:
                nearest_distance = distance
                nearest_index = index

    return nearest_index, nearest_distance


def init_marker_report_items(marker: Marker) -> Marker:
    """Chuẩn hóa marker để luôn có report_items."""

    if "report_items" not in marker or not marker.get("report_items"):
        marker["report_items"] = [{
            "original_image_path": marker.get("original_image_path", ""),
            "detected_image_path": marker.get("detected_image_path", ""),
            "analysis_html": marker.get("analysis_html", ""),
            "area_m2": marker.get("area_m2", 0),
            "setup_name": marker.get("setup_name", ""),
            "confidence": marker.get("confidence", 0),
            "frame_index": marker.get("frame_index", 0),
            "time_sec": marker.get("time_sec", 0),
            "time_text": marker.get("time_text", ""),
            "media_path": marker.get("media_path", ""),
            "media_type": marker.get("media_type", ""),
            "road_name": marker.get("road_name", "Chưa xác định"),
        }]

    marker["capture_count"] = len(marker.get("report_items", []))
    return marker


def append_or_merge_detected_marker(detected_markers, new_marker, radius_m=SAME_POTHOLE_RADIUS_M):
    """
    Nếu marker mới nằm gần marker cũ <= 2m thì gộp vào marker cũ.
    Nếu chưa có marker gần đó thì append marker mới.
    """

    detected_markers = detected_markers or []
    new_marker = init_marker_report_items(new_marker)

    nearby_index, distance = find_nearby_detected_marker_index(
        detected_markers,
        new_marker.get("lat"),
        new_marker.get("lng"),
        radius_m=radius_m,
    )

    if nearby_index is None:
        detected_markers.append(new_marker)
        return detected_markers, True, None

    old_marker = init_marker_report_items(detected_markers[nearby_index])

    old_items = list(old_marker.get("report_items", []))
    new_items = list(new_marker.get("report_items", []))
    merged_items = old_items + new_items

    old_conf = float(old_marker.get("confidence", 0) or 0)
    new_conf = float(new_marker.get("confidence", 0) or 0)

    if new_conf >= old_conf:
        keep_lat = old_marker.get("lat")
        keep_lng = old_marker.get("lng")
        old_marker.update(new_marker)
        old_marker["lat"] = keep_lat
        old_marker["lng"] = keep_lng

    old_marker["report_items"] = merged_items
    old_marker["capture_count"] = len(merged_items)
    old_marker["duplicate_distance_m"] = distance
    old_marker["is_reported"] = False

    detected_markers[nearby_index] = old_marker
    return detected_markers, False, nearby_index


def should_add_new_marker(
    current_time,
    lat,
    lng,
    last_marker_time,
    last_marker_lat,
    last_marker_lng,
    min_seconds=2.5,
    min_distance_m=SAME_POTHOLE_RADIUS_M,
):
    if lat is None or lng is None:
        return False

    if last_marker_time is None:
        return True

    time_ok = current_time - last_marker_time >= min_seconds

    distance_ok = False
    if last_marker_lat is not None and last_marker_lng is not None:
        distance = haversine(lat, lng, last_marker_lat, last_marker_lng)
        distance_ok = distance >= min_distance_m

    return time_ok or distance_ok


def make_detected_marker_from_analysis(
    analysis,
    lat,
    lng,
    frame_index,
    current_time,
    road_name="Chưa xác định",
    source="Video",
):
    depth_info = analysis.get("depth_info") or {}

    return {
        "type": "detected",
        "source": source,
        "lat": float(lat),
        "lng": float(lng),
        "frame_index": int(frame_index),
        "time_sec": float(current_time),
        "time_text": format_video_time(current_time),
        "road_name": road_name or "Chưa xác định",
        "confidence": float(analysis.get("confidence", 0.0) or 0.0),
        "area_m2": float(analysis.get("area_m2", 0.0) or 0.0),
        "depth_level": get_depth_level_from_depth_info(depth_info),
        "water_text": get_water_text_from_depth_info(depth_info),
    }


# ============================================================
# 6. VẼ BẢNG 2 CỘT VÀO DƯỚI VIDEO
# ============================================================

def get_video_font(size=24, bold=False):
    if bold:
        font_paths = [
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    else:
        font_paths = [
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]

    for font_path in font_paths:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass

    return ImageFont.load_default()


def format_brightness_video(value):
    try:
        value = float(value or 0)
        percent = value / 255 * 100
        return f"{percent:.2f}% ({value:.2f}/255)"
    except Exception:
        return "--"


def build_bottom_panel_lines(analysis, setup_name, frame_index, time_sec):
    has_pothole = analysis.get("has_pothole", False)
    confidence = float(analysis.get("confidence", 0.0) or 0.0)
    area_m2 = float(analysis.get("area_m2", 0.0) or 0.0)
    depth_info = analysis.get("depth_info")

    if not has_pothole or depth_info is None:
        left_lines = [
            ("THÔNG TIN NƯỚC / ÁNH SÁNG", "title"),
            ("", "normal"),
            (f"Setup camera: {setup_name}", "normal"),
            (f"Frame: {frame_index}", "normal"),
            (f"Thời gian: {time_sec:.2f} giây", "normal"),
            ("Phát hiện ổ gà: Không", "normal"),
            (f"Confidence: {confidence:.3f}", "normal"),
            (f"Diện tích: {area_m2:.3f} m²", "normal"),
        ]

        right_lines = [
            ("THÔNG TIN ĐỘ SÂU", "title"),
            ("", "normal"),
            ("Chưa có dữ liệu độ sâu.", "normal"),
        ]

        return left_lines, right_lines

    water_info = depth_info.get("water_info", {})
    has_water = depth_info.get("has_water", False)
    is_night = water_info.get("is_night", False)
    night_text = "Đúng" if is_night else "Sai"
    water_text = "Có nước" if has_water else "Không có nước"

    left_lines = [
        ("THÔNG TIN NƯỚC / ÁNH SÁNG", "title"),
        ("", "normal"),
        (f"Frame: {frame_index} | Thời gian: {time_sec:.2f}s", "normal"),
        (f"Độ tin cậy: {confidence:.3f}", "normal"),
        (f"Diện tích: {area_m2:.3f} m²", "normal"),
        ("", "normal"),
        (f"Ảnh ban đêm: {night_text}", "normal"),
        (f"Độ sáng toàn ảnh: {format_brightness_video(water_info.get('global_mean_v', 0))}", "normal"),
        (f"Độ sáng vùng ổ gà: {format_brightness_video(water_info.get('pothole_mean_v', 0))}", "normal"),
        (f"Tỷ lệ vùng tối toàn ảnh: {water_info.get('dark_global_ratio', 0) * 100:.2f}%", "normal"),
        (f"Tỷ lệ vùng sáng toàn ảnh: {water_info.get('bright_global_ratio', 0) * 100:.2f}%", "normal"),
        (f"Trạng thái nước: {water_text}", "danger"),
        (f"Điểm nước: {water_info.get('water_score', 0)}", "danger"),
        (f"Phản chiếu sáng: {water_info.get('highlight_ratio', 0) * 100:.2f}%", "normal"),
        (f"Vùng tối mịn: {water_info.get('dark_smooth_ratio', 0) * 100:.2f}%", "normal"),
        (f"Texture thấp: {water_info.get('low_texture_ratio', 0) * 100:.2f}%", "normal"),
    ]

    depth_level = depth_info.get("depth_level", "Không xác định")
    depth_score = float(depth_info.get("depth_score", 0.0) or 0.0)

    right_lines = [
        ("THÔNG TIN ĐỘ SÂU", "title"),
        ("", "normal"),
        (f"Phương pháp: {depth_info.get('depth_method', 'CLAHE brightness')}", "normal"),
        (f"Độ sâu tương đối: {depth_level}", "danger" if depth_level == "Sâu" else "normal"),
        (f"Độ tin cậy: {depth_info.get('depth_confidence', 'Thấp')}", "normal"),
        (f"Điểm độ sâu cuối cùng: {depth_score:.2f}", "normal"),
        (f"Điểm Depth Anything: {float(depth_info.get('depth_score_da', 0) or 0):.2f}", "normal"),
        (f"Điểm viền tối: {float(depth_info.get('rim_score', 0) or 0):.2f}", "normal"),
        (f"Điểm tương phản: {float(depth_info.get('contrast_score', 0) or 0):.2f}", "normal"),
        (f"Độ sâu TB ổ gà: {float(depth_info.get('pothole_depth_mean', 0) or 0):.3f}", "normal"),
        (f"Độ sâu TB mặt đường: {float(depth_info.get('road_depth_mean', 0) or 0):.3f}", "normal"),
        (f"Tỷ lệ viền tối: {float(depth_info.get('dark_rim_ratio', 0) or 0) * 100:.2f}%", "normal"),
        (f"Độ sáng ổ gà: {format_brightness_video(depth_info.get('pothole_brightness', 0))}", "normal"),
        (f"Độ sáng mặt đường: {format_brightness_video(depth_info.get('road_brightness', 0))}", "normal"),
    ]

    return left_lines, right_lines


def draw_text_lines(draw, lines, x, y, font_normal, font_title, font_bold, line_height=26):
    for item in lines:
        if isinstance(item, tuple):
            text, style = item
        else:
            text, style = str(item), "normal"

        if style == "title":
            font = font_title
            color = (255, 255, 255)
        elif style == "danger":
            font = font_bold
            color = (220, 50, 50)
        else:
            font = font_normal
            color = (255, 255, 255)

        draw.text((x, y), str(text), font=font, fill=color)
        y += line_height


def draw_video_frame_with_bottom_table(
    frame_bgr,
    analysis,
    setup_name,
    frame_index,
    time_sec,
    display_mode="Laptop",
):
    h, w = frame_bgr.shape[:2]

    is_mobile = str(display_mode).strip().lower() in [
        "điện thoại",
        "dien thoai",
        "mobile",
    ]

    panel_height = 320 if is_mobile else 430

    output_height = h + panel_height
    output_width = w

    output = np.zeros((output_height, output_width, 3), dtype=np.uint8)
    output[0:h, 0:w] = frame_bgr

    panel_y = h
    output[panel_y:output_height, :] = (15, 15, 15)

    output_rgb = cv2.cvtColor(output, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(output_rgb)
    draw = ImageDraw.Draw(pil_img)

    if is_mobile:
        font_title = get_video_font(16, bold=True)
        font_normal = get_video_font(10, bold=False)
        font_bold = get_video_font(10, bold=True)
        line_height = 15
        padding_x = 8
        start_padding_y = 12
    else:
        font_title = get_video_font(24, bold=True)
        font_normal = get_video_font(14, bold=False)
        font_bold = get_video_font(14, bold=True)
        line_height = 20
        padding_x = 22
        start_padding_y = 20

    border_color = (255, 255, 255)
    middle_color = (120, 210, 140)

    draw.rectangle(
        [(0, panel_y), (output_width - 1, output_height - 1)],
        outline=border_color,
        width=2,
    )

    middle_x = output_width // 2

    draw.line(
        [(middle_x, panel_y), (middle_x, output_height)],
        fill=middle_color,
        width=2,
    )

    left_lines, right_lines = build_bottom_panel_lines(
        analysis=analysis,
        setup_name=setup_name,
        frame_index=frame_index,
        time_sec=time_sec,
    )

    start_y = panel_y + start_padding_y

    draw_text_lines(draw, left_lines, padding_x, start_y, font_normal, font_title, font_bold, line_height)
    draw_text_lines(draw, right_lines, middle_x + padding_x, start_y, font_normal, font_title, font_bold, line_height)

    output_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    return output_bgr


# ============================================================
# 7. PHÂN TÍCH ẢNH
# ============================================================

def analyze_image_for_web(
    image_path: str,
    setup_display_name: str,
    detected_markers=None,
    current_lat=None,
    current_lng=None,
    route_points=None,
):
    detected_markers = detected_markers or []
    route_points = route_points or []

    try:
        if image_path is None:
            return (
                None,
                """
                <div style="color:white; border:1px solid white; padding:12px;">
                    Vui lòng chụp hoặc chọn ảnh.
                </div>
                """,
                refresh_map(detected_markers, route_points, current_lat, current_lng),
                detected_markers,
                route_points,
            )

        image_name = Path(str(image_path)).name
        auto_gps_csv_path = find_sidecar_gps_csv(image_path)

        road_name = "Vị trí hiện tại"
        gps_source = "Ảnh vị trí hiện tại"

        if auto_gps_csv_path:
            try:
                _, _, gps_lat, gps_lng, road_name, csv_route_points = load_gps_csv_path(auto_gps_csv_path)
                current_lat = gps_lat
                current_lng = gps_lng
                route_points = csv_route_points
                gps_source = "Ảnh GPS CSV"
            except Exception as gps_error:
                return (
                    None,
                    f"""
                    <div style="color:white; border:1px solid #ffcc00; padding:12px; background:#111111;">
                        <b style="color:#ffcc00;">Lỗi đọc GPS CSV tự động</b><br><br>
                        File: {html.escape(str(auto_gps_csv_path))}<br><br>
                        {html.escape(str(gps_error))}
                    </div>
                    """,
                    refresh_map(detected_markers, route_points, current_lat, current_lng),
                    detected_markers,
                    route_points,
                )

        if not has_valid_gps(current_lat, current_lng):
            return (
                None,
                build_gps_required_html(mode="ảnh", media_name=image_name),
                refresh_map(detected_markers, route_points, current_lat, current_lng),
                detected_markers,
                route_points,
            )

        setup_name = get_setup_name(setup_display_name)
        check_homography_exists(setup_name)

        frame = cv2.imread(str(image_path))

        if frame is None:
            return (
                None,
                """
                <div style="color:white; border:1px solid white; padding:12px;">
                    Không đọc được ảnh đầu vào.
                </div>
                """,
                refresh_map(detected_markers, route_points, current_lat, current_lng),
                detected_markers,
                route_points,
            )

        analysis_service = get_analysis_service()

        analysis = analysis_service.analyze_frame(
            frame=frame,
            setup_name=setup_name,
            frame_index=0,
            use_depth_cache=False,
        )

        annotated_frame = analysis.get("annotated_frame", frame)

        original_report_image_path = save_report_frame_to_file(frame, image_path, "original")
        detected_report_image_path = save_report_frame_to_file(annotated_frame, image_path, "detected")
        output_image_path = save_result_image(annotated_frame)

        output_html = build_single_frame_html(
            analysis=analysis,
            setup_name=setup_name,
            frame_index=0,
            time_sec=0.0,
        )

        if analysis.get("has_pothole"):
            try:
                marker = make_detected_marker_from_analysis(
                    analysis=analysis,
                    lat=float(current_lat),
                    lng=float(current_lng),
                    frame_index=0,
                    current_time=0,
                    road_name=road_name,
                    source=gps_source,
                )

                depth_info = analysis.get("depth_info") or {}

                marker.update({
                    "media_type": "image",
                    "media_path": str(image_path),
                    "original_image_path": original_report_image_path,
                    "detected_image_path": detected_report_image_path,
                    "analysis_html": build_analysis_html(depth_info) if depth_info else "",
                    "setup_name": setup_name,
                    "is_reported": False,
                })

                detected_markers, is_new_marker, nearby_index = append_or_merge_detected_marker(
                    detected_markers=detected_markers,
                    new_marker=marker,
                    radius_m=SAME_POTHOLE_RADIUS_M,
                )
            except Exception as marker_error:
                print("Không tạo được marker ảnh:", marker_error)

        map_html = refresh_map(
            detected_markers=detected_markers,
            route_points=route_points,
            current_lat=current_lat,
            current_lng=current_lng,
        )

        return output_image_path, output_html, map_html, detected_markers, route_points

    except Exception:
        error_text = "Lỗi khi phân tích ảnh:\n\n" + traceback.format_exc()

        return (
            None,
            f"""
            <pre style="
                color:white;
                border:1px solid white;
                padding:12px;
                background:#111111;
                white-space:pre-wrap;
            ">{html.escape(error_text)}</pre>
            """,
            refresh_map(detected_markers, route_points, current_lat, current_lng),
            detected_markers,
            route_points,
        )


# ============================================================
# 8. PHÂN TÍCH VIDEO
# ============================================================

def analyze_video_for_web(
    video_path: str,
    setup_display_name: str,
    detected_markers=None,
    current_lat=None,
    current_lng=None,
    display_mode="Laptop",
):
    detected_markers = detected_markers or []
    route_points: List[Point] = []

    try:
        if video_path is None:
            return (
                None,
                """
                <div style="color:white; border:1px solid white; padding:12px;">
                    Vui lòng chọn video.
                </div>
                """,
                refresh_map(detected_markers, route_points, current_lat, current_lng),
                detected_markers,
                route_points,
            )

        video_name = Path(str(video_path)).name
        auto_gps_csv_path = find_sidecar_gps_csv(video_path)

        if not auto_gps_csv_path and not has_valid_gps(current_lat, current_lng):
            return (
                None,
                build_gps_required_html(mode="video", media_name=video_name),
                refresh_map(detected_markers, route_points, current_lat, current_lng),
                detected_markers,
                route_points,
            )

        setup_name = get_setup_name(setup_display_name)
        check_homography_exists(setup_name)

        gps_service = GPSService()
        gps_points = []
        gps_source = "Vị trí hiện tại"
        gps_csv_name = ""

        if auto_gps_csv_path:
            gps_points = gps_service.load_csv(auto_gps_csv_path)
            route_points = [
                [point["latitude"], point["longitude"]]
                for point in gps_points
            ]
            gps_source = "GPS CSV tự động"
            gps_csv_name = Path(auto_gps_csv_path).name

        analysis_service = get_analysis_service()
        analysis_service.reset_depth_cache()

        cap = cv2.VideoCapture(str(video_path))

        if not cap.isOpened():
            return (
                None,
                """
                <div style="color:white; border:1px solid white; padding:12px;">
                    Không mở được video.
                </div>
                """,
                refresh_map(detected_markers, route_points, current_lat, current_lng),
                detected_markers,
                route_points,
            )

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 25

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        max_frames = min(total_frames, int(MAX_VIDEO_SECONDS * fps))

        if width % 2 != 0:
            width -= 1
        if height % 2 != 0:
            height -= 1

        timestamp = int(time.time() * 1000)
        output_video_path = WEB_VIDEO_OUTPUT_DIR / f"video_result_{timestamp}.mp4"

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        is_mobile = str(display_mode).strip().lower() in ["điện thoại", "dien thoai", "mobile"]
        panel_height = 320 if is_mobile else 430

        writer = cv2.VideoWriter(
            str(output_video_path),
            fourcc,
            fps,
            (width, height + panel_height),
        )

        frame_index = 0
        processed_frames = 0
        pothole_frames = 0
        detected_frame_items = []

        last_marker_time = None
        last_marker_lat = None
        last_marker_lng = None

        last_panel_analysis = {
            "has_pothole": False,
            "confidence": 0.0,
            "area_m2": 0.0,
            "depth_info": None,
        }

        while frame_index < max_frames:
            ret, frame = cap.read()
            if not ret:
                break

            time_sec = frame_index / fps

            if frame_index % VIDEO_FRAME_STEP == 0:
                analysis = analysis_service.analyze_frame(
                    frame=frame,
                    setup_name=setup_name,
                    frame_index=frame_index,
                    use_depth_cache=True,
                )

                annotated_frame = analysis.get("annotated_frame", frame)
                if annotated_frame is None:
                    annotated_frame = frame

                annotated_frame = cv2.resize(annotated_frame, (width, height))
                processed_frames += 1

                has_pothole = analysis.get("has_pothole", False)

                if has_pothole:
                    pothole_frames += 1
                    last_panel_analysis = analysis

                    confidence = float(analysis.get("confidence", 0.0) or 0.0)
                    area_m2 = float(analysis.get("area_m2", 0.0) or 0.0)

                    frame_html = build_single_frame_html(
                        analysis=analysis,
                        setup_name=setup_name,
                        frame_index=frame_index,
                        time_sec=time_sec,
                    )

                    detected_frame_items.append({
                        "frame_index": frame_index,
                        "time_sec": time_sec,
                        "confidence": confidence,
                        "area_m2": area_m2,
                        "frame_html": frame_html,
                    })

                    marker_lat = None
                    marker_lng = None
                    road_name = "Chưa xác định"
                    marker_source = "Video"

                    if gps_points:
                        marker_lat, marker_lng, road_name = gps_service.get_by_time(time_sec)
                        marker_source = "Video GPS CSV"
                    elif has_valid_gps(current_lat, current_lng):
                        marker_lat = float(current_lat)
                        marker_lng = float(current_lng)
                        road_name = "Vị trí hiện tại"
                        marker_source = "Video vị trí hiện tại"

                    if marker_lat is not None and marker_lng is not None:
                        if should_add_new_marker(
                            current_time=time_sec,
                            lat=marker_lat,
                            lng=marker_lng,
                            last_marker_time=last_marker_time,
                            last_marker_lat=last_marker_lat,
                            last_marker_lng=last_marker_lng,
                        ):
                            original_report_image_path = save_report_frame_to_file(frame, video_path, "original")
                            detected_report_image_path = save_report_frame_to_file(annotated_frame, video_path, "detected")

                            marker = make_detected_marker_from_analysis(
                                analysis=analysis,
                                lat=marker_lat,
                                lng=marker_lng,
                                frame_index=frame_index,
                                current_time=time_sec,
                                road_name=road_name,
                                source=marker_source,
                            )

                            depth_info = analysis.get("depth_info") or {}

                            marker.update({
                                "media_type": "video",
                                "media_path": str(video_path),
                                "original_image_path": original_report_image_path,
                                "detected_image_path": detected_report_image_path,
                                "analysis_html": build_analysis_html(depth_info) if depth_info else "",
                                "setup_name": setup_name,
                                "is_reported": False,
                            })

                            detected_markers, is_new_marker, nearby_index = append_or_merge_detected_marker(
                                detected_markers=detected_markers,
                                new_marker=marker,
                                radius_m=SAME_POTHOLE_RADIUS_M,
                            )

                            last_marker_time = time_sec
                            last_marker_lat = marker_lat
                            last_marker_lng = marker_lng

                else:
                    last_panel_analysis = analysis

                frame_with_table = draw_video_frame_with_bottom_table(
                    frame_bgr=annotated_frame,
                    analysis=analysis,
                    setup_name=setup_name,
                    frame_index=frame_index,
                    time_sec=time_sec,
                    display_mode=display_mode,
                )

                writer.write(frame_with_table)

            else:
                frame_resized = cv2.resize(frame, (width, height))

                frame_with_table = draw_video_frame_with_bottom_table(
                    frame_bgr=frame_resized,
                    analysis=last_panel_analysis,
                    setup_name=setup_name,
                    frame_index=frame_index,
                    time_sec=time_sec,
                    display_mode=display_mode,
                )

                writer.write(frame_with_table)

            frame_index += 1

        cap.release()
        writer.release()

        video_summary = {
            "setup_name": setup_name,
            "total_frames": total_frames,
            "frames_read": frame_index,
            "processed_frames": processed_frames,
            "pothole_frames": pothole_frames,
            "fps": fps,
            "frame_step": VIDEO_FRAME_STEP,
            "max_seconds": MAX_VIDEO_SECONDS,
            "gps_source": gps_source,
            "gps_csv_name": gps_csv_name,
        }

        output_html = build_video_all_frames_html(
            video_summary=video_summary,
            detected_frame_items=detected_frame_items,
        )

        if route_points:
            map_html = render_map_html(
                detected_markers=detected_markers,
                route_points=route_points,
                current_location=None,
            )
        else:
            map_html = refresh_map(
                detected_markers=detected_markers,
                route_points=route_points,
                current_lat=current_lat,
                current_lng=current_lng,
            )

        return str(output_video_path), output_html, map_html, detected_markers, route_points

    except Exception:
        error_text = "Lỗi khi phân tích video:\n\n" + traceback.format_exc()

        return (
            None,
            f"""
            <pre style="
                color:white;
                border:1px solid white;
                padding:12px;
                background:#111111;
                white-space:pre-wrap;
            ">{html.escape(error_text)}</pre>
            """,
            refresh_map(detected_markers, route_points, current_lat, current_lng),
            detected_markers,
            route_points,
        )


# ============================================================
# 9. CAMERA REALTIME WEBRTC
# ============================================================

_webrtc_frame_index = 0
_webrtc_last_analysis = None


def resize_for_webrtc(frame_bgr, max_width=WEBRTC_MAX_WIDTH):
    h, w = frame_bgr.shape[:2]

    if w <= max_width:
        return frame_bgr

    scale = max_width / w
    new_w = int(w * scale)
    new_h = int(h * scale)

    if new_w % 2 != 0:
        new_w -= 1
    if new_h % 2 != 0:
        new_h -= 1

    return cv2.resize(frame_bgr, (new_w, new_h))


def analyze_webrtc_frame_for_web(frame_rgb, setup_display_name: str, display_mode="Laptop"):
    """
    Xử lý frame realtime từ WebRTC/FastRTC.

    Tối ưu:
    - Resize frame về chiều rộng tối đa WEBRTC_MAX_WIDTH.
    - Chỉ chạy YOLO/depth mỗi WEBRTC_ANALYZE_EVERY frame.
    - Các frame còn lại dùng lại kết quả phân tích gần nhất.
    """

    global _webrtc_frame_index
    global _webrtc_last_analysis

    try:
        if frame_rgb is None:
            return None

        setup_name = get_setup_name(setup_display_name)
        check_homography_exists(setup_name)

        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        frame_bgr = resize_for_webrtc(frame_bgr, WEBRTC_MAX_WIDTH)

        analysis_service = get_analysis_service()

        should_analyze = (
            _webrtc_last_analysis is None
            or _webrtc_frame_index % WEBRTC_ANALYZE_EVERY == 0
        )

        if should_analyze:
            analysis = analysis_service.analyze_frame(
                frame=frame_bgr,
                setup_name=setup_name,
                frame_index=_webrtc_frame_index,
                use_depth_cache=True,
            )
            _webrtc_last_analysis = analysis
        else:
            analysis = _webrtc_last_analysis

        annotated_frame = analysis.get("annotated_frame", frame_bgr)
        if annotated_frame is None:
            annotated_frame = frame_bgr

        annotated_frame = resize_for_webrtc(annotated_frame, WEBRTC_MAX_WIDTH)

        frame_with_table_bgr = draw_video_frame_with_bottom_table(
            frame_bgr=annotated_frame,
            analysis=analysis,
            setup_name=setup_name,
            frame_index=_webrtc_frame_index,
            time_sec=0.0,
            display_mode=display_mode,
        )

        _webrtc_frame_index += 1

        return cv2.cvtColor(frame_with_table_bgr, cv2.COLOR_BGR2RGB)

    except Exception as error:
        print("Lỗi camera realtime:", error)

        error_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        cv2.putText(
            error_frame,
            "Loi camera realtime",
            (40, 220),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        return error_frame


# ============================================================
# 10. TƯƠNG THÍCH IMPORT CŨ
# ============================================================

# Các hàm map dưới đây đã chuyển sang `web.map_service`.
# Giữ import/re-export để nếu file cũ còn `from web.adapter import refresh_map`
# hoặc `from web_adapter import refresh_map` thì vẫn dễ chỉnh hơn.
# Không khai báo lại logic map ở đây để tránh trùng code.
