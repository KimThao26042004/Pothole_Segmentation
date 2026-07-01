"""
Map service cho web.

File này chỉ xử lý các phần liên quan đến bản đồ:
- Đọc marker báo cáo cũ từ SQLite.
- Tạo popup cho marker.
- Render Folium map ra iframe HTML.
- Cập nhật map theo vị trí hiện tại / GPS CSV / marker phát hiện.

Lưu ý refactor:
- Các hàm map đã từng bị khai báo trùng trong `web_adapter.py` và `web_map.py`.
- Sau refactor, chỉ giữ bản chính ở đây. Các file khác chỉ import lại, không viết lại.
"""

import html
import os
import sqlite3
from typing import Any, Dict, List, Optional

import folium

from app_settings import DATABASE_PATH
from web.config import DEFAULT_MAP_CENTER


Marker = Dict[str, Any]
Point = List[float]


# ============================================================
# 1. HÀM TIỆN ÍCH
# ============================================================

def safe_float(value, default=None):
    """Ép kiểu float an toàn cho dữ liệu lấy từ SQLite / Gradio."""
    try:
        return float(value)
    except Exception:
        return default


def popup_text(value) -> str:
    """Escape text trước khi đưa vào popup HTML."""
    if value is None:
        return ""
    return html.escape(str(value)).replace("\n", "<br>")


def has_valid_gps(lat, lng) -> bool:
    """Kiểm tra cặp tọa độ có hợp lệ không."""
    try:
        if lat is None or lng is None:
            return False

        lat_text = str(lat).strip()
        lng_text = str(lng).strip()

        if not lat_text or not lng_text:
            return False

        float(lat_text)
        float(lng_text)
        return True
    except Exception:
        return False


def build_current_location(lat, lng) -> Optional[Marker]:
    """Tạo dict current_location nếu lat/lng hợp lệ."""
    if not has_valid_gps(lat, lng):
        return None

    return {
        "lat": float(lat),
        "lng": float(lng),
    }


# ============================================================
# 2. LOAD MARKER TỪ DATABASE
# ============================================================

def load_database_report_markers() -> List[Marker]:
    """
    Đọc các marker báo cáo cũ từ SQLite.

    Marker màu xanh dương trên map.
    Có fallback cho database cũ chưa có đủ cột detected_image_path / area_m2.
    """

    markers: List[Marker] = []

    if not os.path.exists(DATABASE_PATH):
        return markers

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    r.id,
                    r.address,
                    r.latitude,
                    r.longitude,
                    r.image_count,
                    r.created_at,
                    COALESCE(i.detected_image_path, i.image_path, '') AS image_path,
                    COALESCE(i.analysis_html, r.analysis_html, '') AS analysis_html,
                    COALESCE(i.area_m2, 0) AS area_m2
                FROM pothole_reports r
                LEFT JOIN pothole_report_images i
                    ON r.id = i.report_id
                GROUP BY r.id
                ORDER BY r.id DESC
            """)
        except Exception:
            # Fallback cho DB cũ.
            cursor.execute("""
                SELECT
                    r.id,
                    r.address,
                    r.latitude,
                    r.longitude,
                    r.image_count,
                    r.created_at,
                    COALESCE(i.image_path, '') AS image_path,
                    COALESCE(r.analysis_html, '') AS analysis_html,
                    0 AS area_m2
                FROM pothole_reports r
                LEFT JOIN pothole_report_images i
                    ON r.id = i.report_id
                GROUP BY r.id
                ORDER BY r.id DESC
            """)

        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            report_id, address, lat, lng, image_count, created_at, image_path, analysis_html, area_m2 = row

            lat = safe_float(lat)
            lng = safe_float(lng)

            if lat is None or lng is None:
                continue

            markers.append({
                "type": "database",
                "report_id": report_id,
                "lat": lat,
                "lng": lng,
                "address": address or "Chưa xác định",
                "created_at": created_at or "",
                "image_count": image_count or 0,
                "image_path": image_path or "",
                "analysis_html": analysis_html or "",
                "area_m2": area_m2 or 0,
            })

    except Exception as error:
        print("Lỗi load marker database:", error)

    return markers


# ============================================================
# 3. POPUP HTML
# ============================================================

def make_database_popup(marker: Marker) -> str:
    return f"""
    <div style="font-family:Arial; font-size:13px; line-height:1.45;">
        <div style="font-weight:800; color:#2563eb; font-size:15px;">
            Báo cáo từ database
        </div>
        <b>Địa chỉ:</b> {popup_text(marker.get("address"))}<br>
        <b>Thời gian gửi:</b> {popup_text(marker.get("created_at"))}<br>
        <b>Số file:</b> {marker.get("image_count", 0)}<br>
        <b>Diện tích:</b> {float(marker.get("area_m2", 0) or 0):.3f} m²<br>
        <b>Tọa độ:</b> {marker.get("lat"):.6f}, {marker.get("lng"):.6f}<br>
    </div>
    """


def make_detected_popup(marker: Marker) -> str:
    return f"""
    <div style="font-family:Arial; font-size:13px; line-height:1.45;">
        <div style="font-weight:800; color:#dc2626; font-size:15px;">
            Ổ gà được phát hiện
        </div>
        <b>Nguồn:</b> {popup_text(marker.get("source", "Video"))}<br>
        <b>Tuyến đường:</b> {popup_text(marker.get("road_name", "Chưa xác định"))}<br>
        <b>Thời điểm:</b> {popup_text(marker.get("time_text", ""))}<br>
        <b>Frame:</b> {marker.get("frame_index", "")}<br>
        <b>Số lần ghi nhận:</b> {marker.get("capture_count", 1)}<br>
        <b>Confidence:</b> {float(marker.get("confidence", 0) or 0):.3f}<br>
        <b>Diện tích:</b> {float(marker.get("area_m2", 0) or 0):.3f} m²<br>
        <b>Độ sâu:</b> {popup_text(marker.get("depth_level", "Chưa đánh giá"))}<br>
        <b>Trạng thái nước:</b> {popup_text(marker.get("water_text", "Chưa xác định"))}<br>
        <b>Tọa độ:</b> {marker.get("lat"):.6f}, {marker.get("lng"):.6f}<br>
    </div>
    """


# ============================================================
# 4. RENDER MAP
# ============================================================

def get_map_center(
    database_markers: Optional[List[Marker]] = None,
    detected_markers: Optional[List[Marker]] = None,
    current_location: Optional[Marker] = None,
    route_points: Optional[List[Point]] = None,
) -> Point:
    """Ưu tiên center theo vị trí hiện tại, route, marker mới, marker DB."""

    database_markers = database_markers or []
    detected_markers = detected_markers or []
    route_points = route_points or []

    if current_location and current_location.get("lat") is not None and current_location.get("lng") is not None:
        return [current_location["lat"], current_location["lng"]]

    if route_points:
        return route_points[0]

    if detected_markers:
        last_marker = detected_markers[-1]
        return [last_marker["lat"], last_marker["lng"]]

    if database_markers:
        first_marker = database_markers[0]
        return [first_marker["lat"], first_marker["lng"]]

    return DEFAULT_MAP_CENTER


def collect_map_bounds(
    database_markers: List[Marker],
    detected_markers: List[Marker],
    route_points: List[Point],
    current_location: Optional[Marker],
) -> List[Point]:
    bounds: List[Point] = []

    for marker in database_markers:
        bounds.append([marker["lat"], marker["lng"]])

    for marker in detected_markers:
        bounds.append([marker["lat"], marker["lng"]])

    for point in route_points:
        bounds.append(point)

    if current_location and current_location.get("lat") is not None and current_location.get("lng") is not None:
        bounds.append([current_location["lat"], current_location["lng"]])

    return bounds


def render_map_html(
    detected_markers: Optional[List[Marker]] = None,
    route_points: Optional[List[Point]] = None,
    current_location: Optional[Marker] = None,
    zoom_start: int = 15,
) -> str:
    """
    Render Leaflet map bằng Folium.

    - Marker xanh dương: dữ liệu báo cáo cũ từ database.
    - Marker đỏ: ổ gà phát hiện trong phiên web hiện tại.
    - Marker xanh lá: vị trí hiện tại.
    - Đường xanh dương: route GPS từ CSV.
    """

    detected_markers = detected_markers or []
    route_points = route_points or []

    database_markers = load_database_report_markers()

    center = get_map_center(
        database_markers=database_markers,
        detected_markers=detected_markers,
        current_location=current_location,
        route_points=route_points,
    )

    map_zoom = 18 if current_location else zoom_start

    folium_map = folium.Map(
        location=center,
        zoom_start=map_zoom,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    if route_points:
        folium.PolyLine(
            locations=route_points,
            color="#2563eb",
            weight=5,
            opacity=0.85,
            tooltip="Tuyến GPS từ CSV",
        ).add_to(folium_map)

        folium.Marker(
            location=route_points[0],
            tooltip="Điểm bắt đầu GPS",
            popup="Điểm bắt đầu GPS",
            icon=folium.Icon(color="green", icon="play"),
        ).add_to(folium_map)

        folium.Marker(
            location=route_points[-1],
            tooltip="Điểm kết thúc GPS",
            popup="Điểm kết thúc GPS",
            icon=folium.Icon(color="gray", icon="stop"),
        ).add_to(folium_map)

    for marker in database_markers:
        folium.Marker(
            location=[marker["lat"], marker["lng"]],
            popup=folium.Popup(make_database_popup(marker), max_width=380),
            tooltip="Báo cáo từ database",
            icon=folium.Icon(color="blue", icon="info-sign"),
        ).add_to(folium_map)

    for marker in detected_markers:
        folium.Marker(
            location=[marker["lat"], marker["lng"]],
            popup=folium.Popup(make_detected_popup(marker), max_width=400),
            tooltip="Ổ gà được phát hiện",
            icon=folium.Icon(color="red", icon="warning-sign"),
        ).add_to(folium_map)

    if current_location and current_location.get("lat") is not None and current_location.get("lng") is not None:
        folium.Marker(
            location=[current_location["lat"], current_location["lng"]],
            popup=folium.Popup(
                f"""
                <b>Vị trí hiện tại</b><br>
                Tọa độ: {current_location["lat"]:.6f}, {current_location["lng"]:.6f}
                """,
                max_width=300,
            ),
            tooltip="Vị trí hiện tại",
            icon=folium.Icon(color="green", icon="screenshot"),
        ).add_to(folium_map)

    # Khi có vị trí hiện tại thì ưu tiên zoom thẳng đến đó.
    # Khi không có vị trí hiện tại nhưng có route, fit theo route để dễ xem đường đi.
    if not current_location and route_points and len(route_points) >= 2:
        folium_map.fit_bounds(route_points, padding=(30, 30))

    map_html = folium_map.get_root().render()

    return f"""
    <iframe
        srcdoc="{html.escape(map_html)}"
        width="100%"
        height="430"
        style="border:1px solid #444; border-radius:12px;"
    ></iframe>
    """


def refresh_map(detected_markers, route_points, current_lat, current_lng) -> str:
    """Render lại map theo state hiện tại của Gradio."""
    return render_map_html(
        detected_markers=detected_markers or [],
        route_points=route_points or [],
        current_location=build_current_location(current_lat, current_lng),
    )


def update_current_location_on_map(detected_markers, route_points, current_lat, current_lng):
    """
    Callback sau khi JavaScript lấy GPS trình duyệt.
    Trả về map_html, status, lat, lng.
    """
    try:
        current_lat = float(current_lat)
        current_lng = float(current_lng)
    except Exception:
        return (
            render_map_html(
                detected_markers=detected_markers or [],
                route_points=route_points or [],
                current_location=None,
            ),
            "Chưa lấy được vị trí hiện tại.",
            "",
            "",
        )

    current_location = {
        "lat": current_lat,
        "lng": current_lng,
    }

    map_html = render_map_html(
        detected_markers=detected_markers or [],
        route_points=route_points or [],
        current_location=current_location,
    )

    status = f"Đã lấy vị trí hiện tại: {current_lat:.6f}, {current_lng:.6f}"

    return map_html, status, str(current_lat), str(current_lng)
