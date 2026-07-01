import os
import json
import html
import math
import urllib.parse
import urllib.request
import sys
import time
import sqlite3
from datetime import datetime
from pathlib import Path
from app_settings import DATABASE_PATH


REPORT_STATUS_INFO = {
    "pending": {
        "label": "Chờ duyệt",
        "text_color": "#1D4ED8",
        "bg_color": "#DBEAFE",
        "border_color": "#93C5FD",
        "marker_color": "#2563EB",
    },
    "approved": {
        "label": "Đã duyệt",
        "text_color": "#15803D",
        "bg_color": "#DCFCE7",
        "border_color": "#86EFAC",
        "marker_color": "#16A34A",
    },
    "processing": {
        "label": "Đang xử lý",
        "text_color": "#B45309",
        "bg_color": "#FEF3C7",
        "border_color": "#FCD34D",
        "marker_color": "#F59E0B",
    },
    "resolved": {
        "label": "Đã xử lý",
        "text_color": "#15803D",
        "bg_color": "#DCFCE7",
        "border_color": "#86EFAC",
        "marker_color": "#16A34A",
    },
    "need_more": {
        "label": "Cần bổ sung",
        "text_color": "#B45309",
        "bg_color": "#FEF3C7",
        "border_color": "#FCD34D",
        "marker_color": "#F59E0B",
    },
    "invalid": {
        "label": "Không hợp lệ",
        "text_color": "#B91C1C",
        "bg_color": "#FEE2E2",
        "border_color": "#FCA5A5",
        "marker_color": "#DC2626",
    },
    "waiting": {
        "label": "Chờ người dùng báo cáo",
        "text_color": "#1D4ED8",
        "bg_color": "#DBEAFE",
        "border_color": "#93C5FD",
        "marker_color": "#2563EB",
    },
}

import cv2
from PyQt5.QtCore import QTimer, QStringListModel, Qt, QEvent
from PyQt5.QtPositioning import QGeoPositionInfoSource
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QMainWindow,
    QFileDialog,
    QMessageBox,
    QCompleter,
    QInputDialog,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QFrame,
    QSizePolicy,
    QListWidgetItem,
)

try:
    import winsound
except Exception:
    winsound = None

from app_settings import (
    BASE_DIR,
    MAP_HTML_PATH,
    HOMOGRAPHY_DIR,
    SAMPLE_VIDEO_DIR,
    MEDIA_EXTS,
    VIDEO_EXTS,
    MODEL_PATH,
)
from ui.map_report_ui import setup_map_report_ui, apply_map_report_style
from user.map_bridge import MapBridge
from user.view_helpers import build_analysis_html
from services.analysis_service import PotholeAnalysisService
from services.geocoding_service import GeocodingService
from services.gps_service import GPSService
from services.media_service import MediaService
from repositories.report_repository import ReportRepository
from utils.geo_utils import haversine
from utils.time_utils import format_video_time

class PotholeMapReportWindow(QMainWindow):
    def __init__(self, current_user=None):
        super().__init__()

        self.current_user = current_user or {}

        username = self.current_user.get("username", "user")
        role = self.current_user.get("role", "user")

        self.setWindowTitle(f"User - {username} ({role})")
        self.resize(1450, 850)

        # Services / repositories.
        self.report_repository = ReportRepository()
        self.gps_service = GPSService()
        self.geocoding_service = GeocodingService()
        self.media_service = MediaService()
        self.analysis_service = PotholeAnalysisService(MODEL_PATH, depth_interval=10)

        self.gps_csv_path = None
        self.current_lat = None
        self.current_lon = None
        self.use_current_location = False
        self.gps_source = None

        # Dữ liệu báo cáo thủ công.
        self.selected_lat = None
        self.selected_lng = None
        self.selected_image_paths = []
        self.current_road_name = "Chưa xác định"

        # Map state.
        self.is_map_loaded = False
        self.pending_markers = []
        self.search_suggestions = {}
        self.route_search_suggestions = {"start": {}, "end": {}}
        self.route_selected_points = {"start": None, "end": None}
        self.route_recent_locations = []
        self.active_route_point_key = None
        self.pending_set_route_point_from_gps = None
        self.pending_set_route_start_from_gps = False

        # Trạng thái đồng bộ báo cáo / lộ trình.
        # Admin cập nhật trạng thái trong database, user app sẽ đọc lại định kỳ
        # để marker và danh sách lộ trình không phải tắt mở app mới cập nhật.
        self.is_refreshing_reports = False
        self.current_route_points = []
        self.current_route_start_point = None
        self.current_route_end_point = None
        self.current_route_distance_m = 0
        self.current_route_duration_s = 0
        self.current_route_filter_active = False

        # Cache thông tin preview theo đường dẫn ảnh marker.
        # Khi user bấm marker, hệ thống dùng cache này để lấy đúng ảnh đã detect
        # và đúng analysis_html/diện tích/setup từ database, tránh lỗi khác dấu \\ và /.
        self.report_preview_cache_by_image_path = {}

        # Media demo state.
        self.video_path = None
        self.media_path = None
        self.media_type = None  # "image" hoặc "video"
        self.gps_csv_path = None
        self.model_path = MODEL_PATH
        self.cap = None
        self.fps = 0
        self.frame_index = 0
        self.video_timer = QTimer()
        self.video_timer.timeout.connect(self.process_video_frame)

        # Trạng thái điều khiển phát video / ảnh trong khung demo.
        self.video_playback_speed = 1.0
        self.is_video_paused = False
        self.last_display_frame = None
        self.fullscreen_dialog = None
        self.fullscreen_video_label = None
        self.fullscreen_info_label = None
        self.fullscreen_control_bar = None
        self.fullscreen_btn_play_pause = None
        self.fullscreen_btn_replay = None
        self.fullscreen_speed_caption = None
        self.fullscreen_speed_combo = None
        self.fullscreen_btn_exit = None

        self.gps_points = []
        self.gps_timestamps = []
        self.current_lat = None
        self.current_lng = None
        self.current_time = 0
        self.detected_potholes = []
        self.last_saved_pothole_time = -999
        self.last_saved_pothole_location = None
        self.video_frame_saved_count = 0
        self.last_alert_sound_time = 0
        self.alert_sound_cooldown = 3

        # Area/depth display state.
        self.current_setup_name = None
        self.current_pothole_area_m2 = 0.0

        self.current_depth_info = None
        self.current_analysis_html = ""

        self.pending_original_frame = None
        self.pending_detected_frame = None
        self.pending_report_data = None
        self.pending_report_is_saved = False

        apply_map_report_style(self)
        setup_map_report_ui(self, MAP_HTML_PATH, MapBridge)
        self.update_video_controls_visibility()
        self.update_play_pause_button_text()
        if hasattr(self, "btn_save_report"):
            self.btn_save_report.setEnabled(False)
        # self.btn_get_current_location.clicked.connect(self.get_current_location)

        self.setup_search_autocomplete()
        self.setup_route_autocomplete()
        self.load_existing_reports()
        self.start_report_auto_refresh()
        self.update_demo_status()

        self.lbl_analysis_info.setTextFormat(Qt.RichText)
        self.lbl_analysis_info.setWordWrap(True)
        self.lbl_analysis_info.setAlignment(Qt.AlignTop | Qt.AlignLeft)

    # =========================
    # ĐỒNG BỘ TRẠNG THÁI BÁO CÁO TỪ DATABASE
    # =========================

    def start_report_auto_refresh(self):
        """Tự đọc lại báo cáo để user thấy trạng thái admin vừa cập nhật.

        SQLite không tự đẩy sự kiện thay đổi sang app đang mở, nên user app
        cần polling nhẹ theo chu kỳ. 5 giây là đủ mượt cho demo và không gây
        tải đáng kể vì chỉ đọc các báo cáo/marker.
        """
        self.report_refresh_timer = QTimer(self)
        self.report_refresh_timer.setInterval(5000)
        self.report_refresh_timer.timeout.connect(self.refresh_reports_from_database)
        self.report_refresh_timer.start()

    def refresh_reports_from_database(self):
        """Cập nhật marker và danh sách lộ trình khi admin đổi trạng thái."""
        if self.is_refreshing_reports:
            return

        if not os.path.exists(DATABASE_PATH):
            return

        self.is_refreshing_reports = True
        try:
            self.load_existing_reports(silent=True)

            # Nếu user đang xem kết quả tra cứu theo lộ trình thì cập nhật lại
            # trạng thái trong danh sách và marker trên tuyến luôn.
            if self.current_route_filter_active and self.current_route_points:
                self.refresh_active_route_results_from_database()
        finally:
            self.is_refreshing_reports = False

    def refresh_active_route_results_from_database(self):
        if not self.current_route_points:
            return

        nearby_reports = self.find_pothole_reports_near_route(
            self.current_route_points,
            max_distance_m=25
        )

        self.draw_shortest_route_on_map(
            route_points=self.current_route_points,
            start_point=self.current_route_start_point,
            end_point=self.current_route_end_point,
            nearby_reports=nearby_reports,
            route_distance_m=self.current_route_distance_m,
            route_duration_s=self.current_route_duration_s,
        )

        self.update_route_result_ui(
            start_point=self.current_route_start_point,
            end_point=self.current_route_end_point,
            route_distance_m=self.current_route_distance_m,
            route_duration_s=self.current_route_duration_s,
            nearby_reports=nearby_reports,
        )

    def clear_user_report_markers_on_map(self):
        if not self.is_map_loaded:
            return

        self.web_view.page().runJavaScript("""
            (function() {
                if (window.userReportLayer) {
                    window.userReportLayer.clearLayers();
                }
            })();
        """)

    # =========================
    # AUTOCOMPLETE TÌM KIẾM
    # =========================

    def setup_search_autocomplete(self):
        self.completer_model = QStringListModel()
        self.completer = QCompleter()
        self.completer.setModel(self.completer_model)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.setMaxVisibleItems(8)
        self.txt_search.setCompleter(self.completer)

        self.search_timer = QTimer()
        self.search_timer.setInterval(600)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.fetch_search_suggestions)

        self.txt_search.textChanged.connect(self.on_search_text_changed)
        self.completer.activated[str].connect(self.on_suggestion_selected)

    def on_search_text_changed(self, text):
        text = text.strip()
        if len(text) < 3:
            self.completer_model.setStringList([])
            return
        self.search_timer.start()

    def fetch_search_suggestions(self):
        query = self.txt_search.text().strip()
        if len(query) < 3:
            return

        try:
            results = self.geocoding_service.search(query, limit=6)
            suggestions = []
            self.search_suggestions.clear()

            for item in results:
                display_name = item.get("display_name", "")
                if not display_name:
                    continue

                lat = float(item["lat"])
                lng = float(item["lon"])
                suggestions.append(display_name)
                self.search_suggestions[display_name] = {
                    "lat": lat,
                    "lng": lng,
                    "display_name": display_name,
                }

            self.completer_model.setStringList(suggestions)
            if suggestions:
                self.completer.complete()
        except Exception:
            pass

    def on_suggestion_selected(self, selected_text):
        item = self.search_suggestions.get(selected_text)
        if not item:
            return

        lat = item["lat"]
        lng = item["lng"]
        display_name = item["display_name"]

        self.selected_lat = lat
        self.selected_lng = lng

        self.txt_search.blockSignals(True)
        self.txt_search.setText(display_name)
        self.txt_search.blockSignals(False)
        self.completer.popup().hide()

        self.lbl_selected_location.setText(
            f"Vị trí đã chọn: {display_name}\nTọa độ: {lat:.6f}, {lng:.6f}"
        )

        safe_display_name = self.escape_js_text(display_name)
        self.web_view.page().runJavaScript(f"moveToLocation({lat}, {lng}, `{safe_display_name}`);")


    # =========================
    # AUTOCOMPLETE ĐIỂM ĐẦU / ĐIỂM CUỐI LỘ TRÌNH
    # =========================

    def setup_route_autocomplete(self):
        """Gợi ý địa chỉ cho điểm đầu/điểm cuối theo kiểu Google Maps."""
        if not hasattr(self, "txt_route_start") or not hasattr(self, "txt_route_end"):
            return

        self.route_start_model = QStringListModel()
        self.route_end_model = QStringListModel()

        # Vẫn tạo completer để tương thích code cũ, nhưng phần hiển thị chính dùng route_picker_panel.
        self.route_start_completer = QCompleter()
        self.route_start_completer.setModel(self.route_start_model)
        self.route_start_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.route_start_completer.setFilterMode(Qt.MatchContains)
        self.route_start_completer.setMaxVisibleItems(8)

        self.route_end_completer = QCompleter()
        self.route_end_completer.setModel(self.route_end_model)
        self.route_end_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.route_end_completer.setFilterMode(Qt.MatchContains)
        self.route_end_completer.setMaxVisibleItems(8)

        self.route_start_timer = QTimer()
        self.route_start_timer.setInterval(450)
        self.route_start_timer.setSingleShot(True)
        self.route_start_timer.timeout.connect(lambda: self.fetch_route_suggestions("start"))

        self.route_end_timer = QTimer()
        self.route_end_timer.setInterval(450)
        self.route_end_timer.setSingleShot(True)
        self.route_end_timer.timeout.connect(lambda: self.fetch_route_suggestions("end"))

        self.txt_route_start.installEventFilter(self)
        self.txt_route_end.installEventFilter(self)

        self.txt_route_start.textChanged.connect(lambda text: self.on_route_text_changed("start", text))
        self.txt_route_end.textChanged.connect(lambda text: self.on_route_text_changed("end", text))
        self.route_start_completer.activated[str].connect(lambda text: self.on_route_suggestion_selected("start", text))
        self.route_end_completer.activated[str].connect(lambda text: self.on_route_suggestion_selected("end", text))

    def eventFilter(self, obj, event):
        if hasattr(self, "txt_route_start") and obj is self.txt_route_start:
            if event.type() in (QEvent.FocusIn, QEvent.MouseButtonPress):
                self.activate_route_input("start")

        if hasattr(self, "txt_route_end") and obj is self.txt_route_end:
            if event.type() in (QEvent.FocusIn, QEvent.MouseButtonPress):
                self.activate_route_input("end")

        return super().eventFilter(obj, event)

    def get_route_widgets_by_key(self, point_key):
        if point_key == "start":
            return self.txt_route_start, self.route_start_model, self.route_start_completer, self.route_start_timer
        return self.txt_route_end, self.route_end_model, self.route_end_completer, self.route_end_timer

    def activate_route_input(self, point_key):
        """Đánh dấu ô đang chọn để user có thể bấm Vị trí hiện tại hoặc click map."""
        self.active_route_point_key = point_key
        self.populate_route_picker_panel(point_key)
        self.set_route_pick_active_on_map(True)

    def on_route_text_changed(self, point_key, text):
        text = text.strip()
        self.active_route_point_key = point_key

        selected_point = self.route_selected_points.get(point_key)
        if selected_point and text != selected_point.get("display_text"):
            self.route_selected_points[point_key] = None

        line_edit, model, completer, timer = self.get_route_widgets_by_key(point_key)

        if len(text) < 3:
            model.setStringList([])
            self.populate_route_picker_panel(point_key)
            return

        timer.start()

    def fetch_route_suggestions(self, point_key):
        line_edit, model, completer, _ = self.get_route_widgets_by_key(point_key)
        query = line_edit.text().strip()

        if len(query) < 3:
            return

        try:
            results = self.geocoding_service.search(query, limit=7)
            suggestions = []
            suggestion_points = []
            self.route_search_suggestions[point_key].clear()

            for item in results:
                display_name = item.get("display_name", "")
                if not display_name:
                    continue

                point = {
                    "lat": float(item["lat"]),
                    "lng": float(item["lon"]),
                    "name": display_name,
                    "display_text": display_name,
                }

                suggestions.append(display_name)
                suggestion_points.append(point)
                self.route_search_suggestions[point_key][display_name] = point

            model.setStringList(suggestions)
            self.populate_route_picker_panel(point_key, suggestions=suggestion_points)
        except Exception:
            pass

    def on_route_suggestion_selected(self, point_key, selected_text):
        point = self.route_search_suggestions.get(point_key, {}).get(selected_text)
        if not point:
            return

        self.set_route_point(point_key, point, add_recent=True, draw_marker=True)

    def make_route_picker_item(self, title, subtitle="", payload=None, enabled=True):
        text = title if not subtitle else f"{title}\n{subtitle}"
        item = QListWidgetItem(text)
        item.setData(Qt.UserRole, payload)
        if not enabled:
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled & ~Qt.ItemIsSelectable)
        return item

    def split_location_display(self, display_name):
        parts = [part.strip() for part in str(display_name or "").split(",") if part.strip()]
        if not parts:
            return "Vị trí đã chọn", ""
        title = parts[0]
        subtitle = ", ".join(parts[1:4])
        return title, subtitle

    def populate_route_picker_panel(self, point_key=None, suggestions=None):
        if not hasattr(self, "route_picker_panel") or not hasattr(self, "route_picker_list"):
            return

        point_key = point_key or self.active_route_point_key or "start"
        self.active_route_point_key = point_key
        point_label = "điểm đầu" if point_key == "start" else "điểm cuối"

        if hasattr(self, "lbl_route_picker_hint"):
            self.lbl_route_picker_hint.setText(
                f"Đang chọn {point_label}. Chọn Vị trí hiện tại, địa điểm đã tra gần đây, "
                "gợi ý tìm kiếm hoặc bấm trực tiếp lên bản đồ."
            )

        self.route_picker_list.clear()

        self.route_picker_list.addItem(
            self.make_route_picker_item(
                "◎  Vị trí hiện tại",
                "Dùng GPS hiện tại của thiết bị cho ô đang chọn",
                {"type": "current_location"}
            )
        )

        if self.route_recent_locations:
            self.route_picker_list.addItem(
                self.make_route_picker_item("Địa điểm đã tra gần đây", "", None, enabled=False)
            )
            for point in self.route_recent_locations[:5]:
                title, subtitle = self.split_location_display(point.get("name") or point.get("display_text"))
                self.route_picker_list.addItem(
                    self.make_route_picker_item(
                        f"◷  {title}",
                        subtitle,
                        {"type": "point", "point": point}
                    )
                )

        suggestions = suggestions or []
        if suggestions:
            self.route_picker_list.addItem(
                self.make_route_picker_item("Gợi ý tìm kiếm", "", None, enabled=False)
            )
            for point in suggestions:
                title, subtitle = self.split_location_display(point.get("name") or point.get("display_text"))
                self.route_picker_list.addItem(
                    self.make_route_picker_item(
                        f"⌕  {title}",
                        subtitle,
                        {"type": "point", "point": point}
                    )
                )

        self.route_picker_panel.setVisible(True)

    def on_route_picker_item_clicked(self, item):
        payload = item.data(Qt.UserRole)
        if not payload:
            return

        point_key = self.active_route_point_key or "start"
        payload_type = payload.get("type")

        if payload_type == "current_location":
            self.use_current_location_for_active_route_point(point_key)
            return

        if payload_type == "point":
            point = payload.get("point")
            if point:
                self.set_route_point(point_key, point, add_recent=True, draw_marker=True)
                if hasattr(self, "route_picker_panel"):
                    self.route_picker_panel.setVisible(False)
                self.set_route_pick_active_on_map(False)

    def add_route_recent_location(self, point):
        if not point:
            return

        lat = float(point.get("lat"))
        lng = float(point.get("lng"))
        name = point.get("name") or point.get("display_text") or f"Tọa độ {lat:.6f}, {lng:.6f}"

        new_point = {
            "lat": lat,
            "lng": lng,
            "name": name,
            "display_text": point.get("display_text") or name,
        }

        filtered = []
        for old in self.route_recent_locations:
            try:
                same_location = abs(float(old.get("lat")) - lat) < 0.00001 and abs(float(old.get("lng")) - lng) < 0.00001
                same_name = (old.get("name") or "") == name
                if same_location or same_name:
                    continue
            except Exception:
                pass
            filtered.append(old)

        self.route_recent_locations = [new_point] + filtered[:5]

    def set_route_point(self, point_key, point, add_recent=True, draw_marker=True):
        if not point:
            return

        lat = float(point.get("lat"))
        lng = float(point.get("lng"))
        name = point.get("name") or point.get("display_text") or f"Tọa độ {lat:.6f}, {lng:.6f}"
        display_text = point.get("display_text") or name

        normalized_point = {
            "lat": lat,
            "lng": lng,
            "name": name,
            "display_text": display_text,
        }

        self.route_selected_points[point_key] = normalized_point
        self.active_route_point_key = point_key

        line_edit, _, _, _ = self.get_route_widgets_by_key(point_key)
        line_edit.blockSignals(True)
        line_edit.setText(display_text)
        line_edit.blockSignals(False)

        if add_recent:
            self.add_route_recent_location(normalized_point)

        if draw_marker:
            self.draw_route_pick_marker(point_key, normalized_point)

    def use_current_location_for_route_start(self):
        """Tương thích code cũ: dùng vị trí hiện tại làm điểm đầu."""
        self.active_route_point_key = "start"
        self.use_current_location_for_active_route_point("start")

    def use_current_location_for_active_route_point(self, point_key=None):
        point_key = point_key or self.active_route_point_key or "start"

        if self.current_lat is not None and self.current_lng is not None:
            self.set_route_point_to_current_location(point_key)
            if hasattr(self, "route_picker_panel"):
                self.route_picker_panel.setVisible(False)
            self.set_route_pick_active_on_map(False)
            return

        self.pending_set_route_point_from_gps = point_key
        self.pending_set_route_start_from_gps = point_key == "start"

        if hasattr(self, "lbl_route_result"):
            label = "điểm đầu" if point_key == "start" else "điểm cuối"
            self.lbl_route_result.setText(f"Đang lấy vị trí hiện tại để làm {label}...")

        self.get_current_location()

    def set_route_start_to_current_location(self):
        self.set_route_point_to_current_location("start")

    def set_route_point_to_current_location(self, point_key="start"):
        if self.current_lat is None or self.current_lng is None:
            return

        label = "điểm đầu" if point_key == "start" else "điểm cuối"
        name = self.current_road_name or "Vị trí hiện tại"
        display_text = "Vị trí hiện tại" if point_key == "start" else f"Vị trí hiện tại ({name})"

        point = {
            "lat": float(self.current_lat),
            "lng": float(self.current_lng),
            "name": name,
            "display_text": display_text,
        }

        self.set_route_point(point_key, point, add_recent=False, draw_marker=True)

        if hasattr(self, "lbl_route_result"):
            self.lbl_route_result.setText(
                f"Đã dùng vị trí hiện tại làm {label}: {self.current_lat:.6f}, {self.current_lng:.6f}. "
                "Nhập/chọn điểm còn lại rồi bấm 'Tìm đường & lọc ổ gà'."
            )

    def get_route_point_name_from_coordinates(self, lat, lng):
        try:
            data = self.geocoding_service.reverse(lat, lng)
            display_name = data.get("display_name", "")
            if display_name:
                return display_name
        except Exception:
            pass
        return f"Vị trí đã chọn ({lat:.6f}, {lng:.6f})"

    def on_route_map_point_selected(self, lat, lng):
        point_key = self.active_route_point_key
        if point_key not in {"start", "end"}:
            return

        display_name = self.get_route_point_name_from_coordinates(lat, lng)
        point = {
            "lat": float(lat),
            "lng": float(lng),
            "name": display_name,
            "display_text": display_name,
        }

        self.set_route_point(point_key, point, add_recent=True, draw_marker=True)

        if hasattr(self, "route_picker_panel"):
            self.route_picker_panel.setVisible(False)

        self.set_route_pick_active_on_map(False)

        if hasattr(self, "lbl_route_result"):
            label = "điểm đầu" if point_key == "start" else "điểm cuối"
            self.lbl_route_result.setText(
                f"Đã chọn {label} trên bản đồ: {float(lat):.6f}, {float(lng):.6f}. "
                "Chọn điểm còn lại rồi bấm 'Tìm đường & lọc ổ gà'."
            )

    def set_route_pick_active_on_map(self, active=True):
        if not getattr(self, "is_map_loaded", False):
            return
        active_js = "true" if active else "false"
        label = "điểm đầu" if self.active_route_point_key == "start" else "điểm cuối"
        label_json = json.dumps(label, ensure_ascii=False)
        self.web_view.page().runJavaScript(
            f"if (window.setRoutePickActive) window.setRoutePickActive({active_js}, {label_json});"
        )

    def draw_route_pick_marker(self, point_key, point):
        if not getattr(self, "is_map_loaded", False):
            return

        title = "Điểm đầu" if point_key == "start" else "Điểm cuối"
        title_json = json.dumps(title, ensure_ascii=False)
        name_json = json.dumps(point.get("name") or point.get("display_text") or title, ensure_ascii=False)

        js = f"""
            (function() {{
                if (window.showRoutePickedPoint) {{
                    window.showRoutePickedPoint(
                        {json.dumps(point_key)},
                        {float(point.get('lat'))},
                        {float(point.get('lng'))},
                        {title_json},
                        {name_json}
                    );
                }}
            }})();
        """
        self.web_view.page().runJavaScript(js)

    def install_route_map_picker_js(self):
        if not getattr(self, "is_map_loaded", False):
            return

        js = """
            (function() {
                if (typeof L === 'undefined') return;
                const m = (typeof map !== 'undefined') ? map : window.map;
                if (!m) return;

                if (!window.routePickLayer) {
                    window.routePickLayer = L.layerGroup().addTo(m);
                    window.routePickMarkers = {};
                }

                window.setRoutePickActive = function(active, label) {
                    window.routePickActive = !!active;
                    window.routePickLabel = label || '';
                    if (m.getContainer && m.getContainer()) {
                        m.getContainer().style.cursor = active ? 'crosshair' : '';
                    }
                };

                window.showRoutePickedPoint = function(key, lat, lng, title, subtitle) {
                    if (!window.routePickLayer) {
                        window.routePickLayer = L.layerGroup().addTo(m);
                        window.routePickMarkers = {};
                    }

                    if (window.routePickMarkers[key]) {
                        window.routePickLayer.removeLayer(window.routePickMarkers[key]);
                    }

                    const marker = L.marker([lat, lng]).bindPopup(
                        '<b>' + (title || 'Vị trí đã chọn') + '</b><br>' +
                        (subtitle || 'Vị trí đã chọn') + '<br>' +
                        '<b>Tọa độ:</b> ' + Number(lat).toFixed(6) + ', ' + Number(lng).toFixed(6)
                    );

                    marker.addTo(window.routePickLayer);
                    window.routePickMarkers[key] = marker;
                    marker.openPopup();
                };

                function callRouteBackend(lat, lng) {
                    if (window.routeBackend && window.routeBackend.chooseRoutePoint) {
                        window.routeBackend.chooseRoutePoint(lat, lng);
                        return;
                    }

                    if (typeof QWebChannel !== 'undefined' && window.qt && window.qt.webChannelTransport) {
                        new QWebChannel(window.qt.webChannelTransport, function(channel) {
                            window.backend = window.backend || channel.objects.backend;
                            window.routeBackend = channel.objects.routeBackend;
                            if (window.routeBackend && window.routeBackend.chooseRoutePoint) {
                                window.routeBackend.chooseRoutePoint(lat, lng);
                            }
                        });
                    }
                }

                if (!window.routePickClickInstalled) {
                    window.routePickClickInstalled = true;
                    m.on('click', function(e) {
                        if (!window.routePickActive) return;
                        callRouteBackend(e.latlng.lat, e.latlng.lng);
                    });
                }
            })();
        """
        self.web_view.page().runJavaScript(js)

    # =========================
    # CAMERA SETUP
    # =========================

    def get_camera_setup_options(self):
        return {
            "Setup 1 - No Zoom": "setup1_nozoom",
            "Setup 1 - Zoom": "setup1_zoom",
            "Setup 2 - No Zoom": "setup2_nozoom",
            "Setup 2 - Zoom": "setup2_zoom",
            "Setup 3 - No Zoom": "setup3_nozoom",
        }

    def get_camera_setup_descriptions(self):
        return {
            "Setup 1 - No Zoom": (
                "Góc đặt camera setup 1, không phóng to. Phù hợp khi khung hình nhìn được nhiều mặt đường "
                "và video/ảnh được quay gần với góc đã hiệu chuẩn file setup1_nozoom.npy."
            ),
            "Setup 1 - Zoom": (
                "Cùng góc đặt setup 1 nhưng có phóng to. Dùng khi camera zoom gần mặt đường hơn, "
                "khung hình hẹp hơn và đã hiệu chuẩn bằng file setup1_zoom.npy."
            ),
            "Setup 2 - No Zoom": (
                "Góc đặt camera setup 2, không phóng to. Dùng cho vị trí/góc nghiêng khác setup 1, "
                "khi ảnh vẫn giữ tầm nhìn rộng của mặt đường."
            ),
            "Setup 2 - Zoom": (
                "Góc đặt camera setup 2 có phóng to. Dùng khi video/ảnh được quay ở setup 2 nhưng vùng ổ gà "
                "được zoom gần hơn."
            ),
            "Setup 3 - No Zoom": (
                "Góc đặt camera setup 3, không phóng to. Dùng cho bộ hiệu chuẩn setup 3 và khung hình không zoom."
            ),
        }

    def build_camera_setup_help_html(self):
        descriptions = self.get_camera_setup_descriptions()
        rows = []

        for setup_display, description in descriptions.items():
            rows.append(
                f"<li><b>{setup_display}</b><br>"
                f"<span>{description}</span></li>"
            )

        return (
            "<div style='font-size:13px; line-height:1.45; color:#334155;'>"
            "<b>Lưu ý:</b> Setup camera phải trùng với góc quay đã dùng để tạo file Homography. "
            "Nếu chọn sai setup, diện tích ước lượng theo m² có thể bị lệch.<br><br>"
            "<ul style='margin-top:0; padding-left:18px;'>"
            + "".join(rows)
            + "</ul></div>"
        )

    def choose_camera_setup(self):
        setup_options = self.get_camera_setup_options()
        descriptions = self.get_camera_setup_descriptions()
        display_names = list(setup_options.keys())

        dialog = QDialog(self)
        dialog.setWindowTitle("Chọn góc setup camera")
        dialog.setModal(True)
        dialog.setMinimumWidth(620)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #f8fafc;
            }
            QLabel#setupIcon {
                background-color: #dbeafe;
                color: #1d4ed8;
                border-radius: 23px;
                min-width: 46px;
                min-height: 46px;
                font-size: 23px;
                font-weight: 900;
            }
            QLabel#setupTitle {
                color: #0f172a;
                font-size: 20px;
                font-weight: 900;
            }
            QLabel#setupSubtitle {
                color: #64748b;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#setupCaption {
                color: #334155;
                font-size: 13px;
                font-weight: 900;
            }
            QLabel#setupDetail, QLabel#setupHelpPanel {
                background-color: #ffffff;
                border: 1px solid #dbe4ef;
                border-radius: 14px;
                padding: 11px 12px;
                color: #334155;
                font-size: 13px;
                line-height: 1.45;
            }
            QComboBox {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 12px;
                padding: 9px 12px;
                min-height: 32px;
                font-size: 14px;
                font-weight: 800;
                color: #0f172a;
            }
            QComboBox:focus {
                border: 2px solid #2563eb;
            }
            QPushButton {
                border-radius: 13px;
                padding: 9px 16px;
                font-size: 14px;
                font-weight: 900;
                min-height: 34px;
            }
            QPushButton#helpButton {
                background-color: #eef2ff;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
                border-radius: 18px;
                min-width: 36px;
                max-width: 36px;
                min-height: 36px;
                max-height: 36px;
                padding: 0px;
                font-size: 17px;
            }
            QPushButton#helpButton:hover {
                background-color: #dbeafe;
            }
            QPushButton#primaryDialogButton {
                background-color: #2563eb;
                color: #ffffff;
                border: 1px solid #1d4ed8;
            }
            QPushButton#primaryDialogButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton#secondaryDialogButton {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
            }
            QPushButton#secondaryDialogButton:hover {
                background-color: #f1f5f9;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_label = QLabel("📷")
        icon_label.setObjectName("setupIcon")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedSize(46, 46)

        title_block = QVBoxLayout()
        title_block.setSpacing(3)

        title_label = QLabel("Chọn góc setup camera")
        title_label.setObjectName("setupTitle")

        subtitle_label = QLabel("Chọn đúng setup đã hiệu chuẩn trước khi phân tích ảnh/video.")
        subtitle_label.setObjectName("setupSubtitle")
        subtitle_label.setWordWrap(True)

        title_block.addWidget(title_label)
        title_block.addWidget(subtitle_label)

        help_button = QPushButton("?")
        help_button.setObjectName("helpButton")
        help_button.setToolTip("Xem thông tin các góc setup")

        header_layout.addWidget(icon_label)
        header_layout.addLayout(title_block, 1)
        header_layout.addWidget(help_button)

        caption_label = QLabel("Setup camera")
        caption_label.setObjectName("setupCaption")

        combo = QComboBox()
        combo.addItems(display_names)

        detail_label = QLabel(descriptions.get(combo.currentText(), ""))
        detail_label.setObjectName("setupDetail")
        detail_label.setWordWrap(True)

        help_panel = QLabel(self.build_camera_setup_help_html())
        help_panel.setObjectName("setupHelpPanel")
        help_panel.setTextFormat(Qt.RichText)
        help_panel.setWordWrap(True)
        help_panel.setVisible(False)

        def update_detail(text):
            detail_label.setText(descriptions.get(text, ""))

        def toggle_help_panel():
            help_panel.setVisible(not help_panel.isVisible())
            help_button.setText("×" if help_panel.isVisible() else "?")

        combo.currentTextChanged.connect(update_detail)
        help_button.clicked.connect(toggle_help_panel)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch(1)

        cancel_button = QPushButton("Hủy")
        cancel_button.setObjectName("secondaryDialogButton")
        cancel_button.clicked.connect(dialog.reject)

        ok_button = QPushButton("Xác nhận")
        ok_button.setObjectName("primaryDialogButton")
        ok_button.clicked.connect(dialog.accept)
        ok_button.setDefault(True)

        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)

        layout.addLayout(header_layout)
        layout.addWidget(caption_label)
        layout.addWidget(combo)
        layout.addWidget(detail_label)
        layout.addWidget(help_panel)
        layout.addLayout(button_layout)

        if dialog.exec_() != QDialog.Accepted:
            return False

        selected_text = combo.currentText()
        setup_name = setup_options[selected_text]
        homography_path = os.path.join(HOMOGRAPHY_DIR, f"{setup_name}.npy")

        if not os.path.exists(homography_path):
            QMessageBox.warning(self, "Thiếu file Homography", f"Không tìm thấy file:\n{homography_path}")
            return False

        self.current_setup_name = setup_name
        self.lbl_alert.setText(f"Đã chọn setup camera: {selected_text}")
        return True

    # =========================
    # DIALOG / THÔNG BÁO ĐẸP
    # =========================

    def show_need_current_location_dialog(self, expected_csv=None):
        """Hiển thị thông báo thiếu GPS CSV và cho phép lấy vị trí hiện tại ngay."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Cần vị trí hiện tại")
        dialog.setModal(True)
        dialog.setMinimumWidth(620)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #f8fafc;
            }
            QLabel#dialogIcon {
                background-color: #dbeafe;
                color: #1d4ed8;
                border-radius: 24px;
                min-width: 48px;
                min-height: 48px;
                font-size: 25px;
                font-weight: 900;
            }
            QLabel#dialogTitle {
                color: #0f172a;
                font-size: 20px;
                font-weight: 900;
            }
            QLabel#dialogMessage {
                color: #475569;
                font-size: 14px;
                line-height: 1.45;
            }
            QLabel#dialogHint {
                background-color: #eff6ff;
                border: 1px solid #bfdbfe;
                border-radius: 14px;
                padding: 11px 12px;
                color: #1e3a8a;
                font-size: 13px;
                font-weight: 700;
                line-height: 1.4;
            }
            QLabel#dialogPath {
                background-color: #ffffff;
                border: 1px dashed #94a3b8;
                border-radius: 12px;
                padding: 10px 12px;
                color: #334155;
                font-size: 12px;
                font-family: Consolas, monospace;
            }
            QPushButton {
                border-radius: 13px;
                padding: 9px 16px;
                font-size: 14px;
                font-weight: 900;
                min-height: 36px;
            }
            QPushButton#primaryDialogButton {
                background-color: #2563eb;
                color: #ffffff;
                border: 1px solid #1d4ed8;
            }
            QPushButton#primaryDialogButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton#secondaryDialogButton {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
            }
            QPushButton#secondaryDialogButton:hover {
                background-color: #f1f5f9;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_label = QLabel("i")
        icon_label.setObjectName("dialogIcon")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedSize(48, 48)

        text_block = QVBoxLayout()
        text_block.setSpacing(4)

        title_label = QLabel("Không tìm thấy GPS CSV tương ứng")
        title_label.setObjectName("dialogTitle")

        message_label = QLabel(
            "Hệ thống cần GPS để gắn vị trí ổ gà lên bản đồ. "
            "Bạn có thể dùng vị trí hiện tại của thiết bị để tiếp tục báo cáo."
        )
        message_label.setObjectName("dialogMessage")
        message_label.setWordWrap(True)

        text_block.addWidget(title_label)
        text_block.addWidget(message_label)

        header_layout.addWidget(icon_label)
        header_layout.addLayout(text_block, 1)

        layout.addLayout(header_layout)

        if expected_csv is not None:
            path_caption = QLabel("File GPS CSV hệ thống đang tìm:")
            path_caption.setObjectName("dialogMessage")

            path_label = QLabel(str(expected_csv))
            path_label.setObjectName("dialogPath")
            path_label.setWordWrap(True)

            layout.addWidget(path_caption)
            layout.addWidget(path_label)

        hint_label = QLabel(
            "Gợi ý: Nếu ảnh/video được quay trực tiếp tại hiện trường thì bấm "
            "'Lấy vị trí hiện tại'. Nếu file được quay ở nơi khác, nên dùng GPS CSV đúng với file đó."
        )
        hint_label.setObjectName("dialogHint")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch(1)

        later_button = QPushButton("Để sau")
        later_button.setObjectName("secondaryDialogButton")
        later_button.clicked.connect(dialog.reject)

        location_button = QPushButton("Lấy vị trí hiện tại")
        location_button.setObjectName("primaryDialogButton")
        location_button.clicked.connect(dialog.accept)
        location_button.setDefault(True)

        button_layout.addWidget(later_button)
        button_layout.addWidget(location_button)
        layout.addLayout(button_layout)

        return dialog.exec_() == QDialog.Accepted

    def show_report_success_dialog(self, title, message, detail=None):
        """Hiển thị thông báo gửi báo cáo thành công theo giao diện đồng bộ với app."""
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setMinimumWidth(560)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #f8fafc;
            }
            QLabel#successIcon {
                background-color: #dcfce7;
                color: #15803d;
                border-radius: 24px;
                min-width: 48px;
                min-height: 48px;
                font-size: 24px;
                font-weight: 900;
            }
            QLabel#successTitle {
                color: #0f172a;
                font-size: 20px;
                font-weight: 900;
            }
            QLabel#successMessage {
                color: #475569;
                font-size: 14px;
                line-height: 1.45;
            }
            QLabel#successDetail {
                background-color: #ecfdf5;
                border: 1px solid #86efac;
                border-radius: 14px;
                padding: 11px 12px;
                color: #166534;
                font-size: 13px;
                font-weight: 800;
                line-height: 1.4;
            }
            QPushButton#primaryDialogButton {
                background-color: #16a34a;
                color: #ffffff;
                border: 1px solid #15803d;
                border-radius: 13px;
                padding: 9px 20px;
                font-size: 14px;
                font-weight: 900;
                min-height: 36px;
            }
            QPushButton#primaryDialogButton:hover {
                background-color: #15803d;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_label = QLabel("✓")
        icon_label.setObjectName("successIcon")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedSize(48, 48)

        text_block = QVBoxLayout()
        text_block.setSpacing(4)

        title_label = QLabel(title)
        title_label.setObjectName("successTitle")

        message_label = QLabel(message)
        message_label.setObjectName("successMessage")
        message_label.setWordWrap(True)

        text_block.addWidget(title_label)
        text_block.addWidget(message_label)

        header_layout.addWidget(icon_label)
        header_layout.addLayout(text_block, 1)
        layout.addLayout(header_layout)

        if detail:
            detail_label = QLabel(detail)
            detail_label.setObjectName("successDetail")
            detail_label.setWordWrap(True)
            layout.addWidget(detail_label)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)

        ok_button = QPushButton("OK")
        ok_button.setObjectName("primaryDialogButton")
        ok_button.clicked.connect(dialog.accept)
        ok_button.setDefault(True)

        button_layout.addWidget(ok_button)
        layout.addLayout(button_layout)

        dialog.exec_()

    # =========================
    # MAP
    # =========================

    def on_map_loaded(self):
        self.is_map_loaded = True

        for marker in self.pending_markers:
            self.add_report_marker_to_map(
                marker["lat"],
                marker["lng"],
                marker["address"],
                marker["created_at"],
                marker["image_count"],
                marker.get("image_path", ""),
                marker.get("analysis_html", ""),
                marker.get("status", "pending"),
                report_id=marker.get("report_id"),
                area_m2=marker.get("area_m2", 0),
                setup_name=marker.get("setup_name", ""),
                original_image_path=marker.get("original_image_path", ""),
                detected_image_path=marker.get("detected_image_path", ""),
            )
        self.pending_markers.clear()

        if self.gps_points:
            self.draw_route_on_map()

        self.install_route_map_picker_js()

    def update_address_from_coordinates(self, lat, lng):
        try:
            data = self.geocoding_service.reverse(lat, lng)
            display_name = data.get("display_name", "") or f"Vị trí tại tọa độ {lat:.6f}, {lng:.6f}"
            self.txt_search.blockSignals(True)
            self.txt_search.setText(display_name)
            self.txt_search.blockSignals(False)
            self.lbl_selected_location.setText(
                f"Vị trí đã chọn:\n{display_name}\nTọa độ: {lat:.6f}, {lng:.6f}"
            )
        except Exception:
            fallback_address = f"Vị trí tại tọa độ {lat:.6f}, {lng:.6f}"
            self.txt_search.blockSignals(True)
            self.txt_search.setText(fallback_address)
            self.txt_search.blockSignals(False)
            self.lbl_selected_location.setText(f"Vị trí đã chọn:\n{fallback_address}")

    def search_location_by_button(self):
        query = self.txt_search.text().strip()
        if not query:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập tên đường hoặc địa chỉ cần tìm.")
            return

        try:
            data = self.geocoding_service.search(query, limit=1)
            if not data:
                QMessageBox.information(self, "Không tìm thấy", "Không tìm thấy tên đường hoặc địa chỉ phù hợp.")
                return

            result = data[0]
            lat = float(result["lat"])
            lng = float(result["lon"])
            display_name = result["display_name"]

            self.selected_lat = lat
            self.selected_lng = lng
            self.lbl_selected_location.setText(f"Vị trí tìm thấy: {lat:.6f}, {lng:.6f}")

            safe_display_name = self.escape_js_text(display_name)
            self.web_view.page().runJavaScript(f"moveToLocation({lat}, {lng}, `{safe_display_name}`);")
        except Exception as error:
            QMessageBox.critical(self, "Lỗi tìm kiếm", f"Không thể tìm kiếm địa điểm.\n\nChi tiết lỗi:\n{error}")


    # =========================
    # TÌM ĐƯỜNG NGẮN NHẤT + LỌC Ổ GÀ GẦN TUYẾN
    # =========================

    def find_shortest_route_and_filter_potholes(self):
        start_text = self.txt_route_start.text().strip() if hasattr(self, "txt_route_start") else ""
        end_text = self.txt_route_end.text().strip() if hasattr(self, "txt_route_end") else ""

        if not start_text or not end_text:
            QMessageBox.warning(
                self,
                "Thiếu điểm đầu/cuối",
                "Vui lòng nhập đầy đủ điểm đầu và điểm cuối để tìm tuyến đường."
            )
            return

        try:
            self.lbl_route_result.setText("Đang tìm tuyến đường ngắn nhất và lọc ổ gà gần tuyến...")
            self.route_result_list.clear()
            self.route_result_list.setVisible(False)

            start_point = self.resolve_route_point(start_text, "điểm đầu", "start")
            end_point = self.resolve_route_point(end_text, "điểm cuối", "end")

            route_points, route_distance_m, route_duration_s = self.fetch_osrm_route(
                start_point["lat"],
                start_point["lng"],
                end_point["lat"],
                end_point["lng"],
            )

            if len(route_points) < 2:
                raise ValueError("Không lấy được hình dạng tuyến đường từ dịch vụ bản đồ.")

            self.current_route_points = route_points
            self.current_route_start_point = start_point
            self.current_route_end_point = end_point
            self.current_route_distance_m = route_distance_m
            self.current_route_duration_s = route_duration_s
            self.current_route_filter_active = True

            nearby_reports = self.find_pothole_reports_near_route(route_points, max_distance_m=25)
            self.draw_shortest_route_on_map(
                route_points=route_points,
                start_point=start_point,
                end_point=end_point,
                nearby_reports=nearby_reports,
                route_distance_m=route_distance_m,
                route_duration_s=route_duration_s,
            )
            self.update_route_result_ui(
                start_point=start_point,
                end_point=end_point,
                route_distance_m=route_distance_m,
                route_duration_s=route_duration_s,
                nearby_reports=nearby_reports,
            )

        except Exception as error:
            self.lbl_route_result.setText("Không thể tìm tuyến đường hoặc lọc ổ gà gần tuyến.")
            QMessageBox.critical(
                self,
                "Lỗi tra cứu lộ trình",
                f"Không thể tìm đường và lọc ổ gà gần tuyến.\n\nChi tiết lỗi:\n{error}"
            )

    def resolve_route_point(self, text, point_label, point_key=None):
        """Chuyển địa chỉ nhập vào thành tọa độ. Có hỗ trợ chọn gợi ý và nhập 'vị trí hiện tại'."""
        normalized = text.strip().lower()

        selected_point = self.route_selected_points.get(point_key) if point_key else None
        if selected_point and text.strip() == selected_point.get("display_text"):
            return {
                "lat": float(selected_point["lat"]),
                "lng": float(selected_point["lng"]),
                "name": selected_point.get("name") or text.strip(),
            }

        if normalized in {"vị trí hiện tại", "vi tri hien tai", "current location", "current"}:
            if self.current_lat is None or self.current_lng is None:
                raise ValueError(
                    f"Bạn chọn {point_label} là vị trí hiện tại nhưng hệ thống chưa có GPS. "
                    "Hãy bấm 'Lấy vị trí hiện tại' trước hoặc nhập địa chỉ cụ thể."
                )
            return {
                "lat": float(self.current_lat),
                "lng": float(self.current_lng),
                "name": "Vị trí hiện tại",
            }

        results = self.geocoding_service.search(text, limit=1)
        if not results:
            raise ValueError(f"Không tìm thấy {point_label}: {text}")

        result = results[0]
        return {
            "lat": float(result["lat"]),
            "lng": float(result["lon"]),
            "name": result.get("display_name") or text,
        }

    def fetch_osrm_route(self, start_lat, start_lng, end_lat, end_lng):
        """Lấy tuyến đường theo mạng đường bộ từ OSRM public server."""
        coords = f"{start_lng},{start_lat};{end_lng},{end_lat}"
        query = urllib.parse.urlencode({
            "overview": "full",
            "geometries": "geojson",
            "alternatives": "false",
            "steps": "false",
        })
        url = f"https://router.project-osrm.org/route/v1/driving/{coords}?{query}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "PotholeMapReportApp/1.0"}
        )

        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))

        if data.get("code") != "Ok" or not data.get("routes"):
            message = data.get("message") or data.get("code") or "Không có tuyến đường phù hợp"
            raise ValueError(f"Dịch vụ tìm đường trả về lỗi: {message}")

        route = data["routes"][0]
        geometry = route.get("geometry", {})
        coordinates = geometry.get("coordinates", [])

        route_points = []
        for lng, lat in coordinates:
            route_points.append([float(lat), float(lng)])

        return route_points, float(route.get("distance") or 0), float(route.get("duration") or 0)

    def get_all_reports_for_route_filter(self):
        """Đọc danh sách báo cáo từ database để lọc theo tuyến đường.

        Ưu tiên lấy ảnh đã detect (detected_image_path) và thông tin phân tích
        được lưu trong bảng pothole_report_images để khi user bấm vào kết quả
        thì khung bên trái hiển thị đúng ảnh sau phát hiện + thông số DB.
        """
        if not os.path.exists(DATABASE_PATH):
            return []

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(pothole_reports)")
        report_columns = [column[1] for column in cursor.fetchall()]

        cursor.execute("PRAGMA table_info(pothole_report_images)")
        image_columns = [column[1] for column in cursor.fetchall()]

        status_expr = "COALESCE(r.status, 'pending')" if "status" in report_columns else "'pending'"
        report_analysis_expr = "COALESCE(r.analysis_html, '')" if "analysis_html" in report_columns else "''"
        image_analysis_expr = "COALESCE(i.analysis_html, '')" if "analysis_html" in image_columns else "''"
        analysis_expr = f"COALESCE(NULLIF({image_analysis_expr}, ''), {report_analysis_expr}, '')"

        original_image_expr = "COALESCE(i.image_path, '')" if "image_path" in image_columns else "''"
        detected_image_expr = "COALESCE(i.detected_image_path, '')" if "detected_image_path" in image_columns else "''"
        display_image_expr = f"COALESCE(NULLIF({detected_image_expr}, ''), NULLIF({original_image_expr}, ''), '')"
        area_expr = "COALESCE(i.area_m2, 0)" if "area_m2" in image_columns else "0"
        setup_expr = "COALESCE(i.setup_name, '')" if "setup_name" in image_columns else "''"

        cursor.execute(f"""
            SELECT
                r.id,
                r.address,
                r.latitude,
                r.longitude,
                COALESCE(r.image_count, 0) AS image_count,
                COALESCE(r.created_at, '') AS created_at,
                {status_expr} AS status,
                {display_image_expr} AS image_path,
                {original_image_expr} AS original_image_path,
                {detected_image_expr} AS detected_image_path,
                {analysis_expr} AS analysis_html,
                {area_expr} AS area_m2,
                {setup_expr} AS setup_name
            FROM pothole_reports r
            LEFT JOIN pothole_report_images i
                ON r.id = i.report_id
            GROUP BY r.id
            ORDER BY datetime(r.created_at) DESC, r.id DESC
        """)

        rows = cursor.fetchall()
        conn.close()

        reports = []
        for (
            report_id,
            address,
            lat,
            lng,
            image_count,
            created_at,
            status,
            image_path,
            original_image_path,
            detected_image_path,
            analysis_html,
            area_m2,
            setup_name,
        ) in rows:
            if lat is None or lng is None:
                continue

            try:
                lat = float(lat)
                lng = float(lng)
            except Exception:
                continue

            status = self.normalize_report_status(status)
            if status == "invalid":
                # Báo cáo không hợp lệ không được tính là ổ gà trên tuyến.
                continue

            reports.append({
                "id": report_id,
                "address": address or "--",
                "latitude": lat,
                "longitude": lng,
                "image_count": image_count or 0,
                "created_at": created_at or "--",
                "status": status,
                "image_path": image_path or "",
                "original_image_path": original_image_path or "",
                "detected_image_path": detected_image_path or "",
                "analysis_html": analysis_html or "",
                "area_m2": float(area_m2 or 0),
                "setup_name": setup_name or "",
            })

        return reports

    def find_pothole_reports_near_route(self, route_points, max_distance_m=25):
        reports = self.get_all_reports_for_route_filter()
        nearby_reports = []

        for report in reports:
            distance_m = self.distance_point_to_route_m(
                report["latitude"],
                report["longitude"],
                route_points,
            )

            if distance_m <= max_distance_m:
                enriched_report = dict(report)
                enriched_report["distance_to_route_m"] = distance_m
                nearby_reports.append(enriched_report)

        nearby_reports.sort(key=lambda item: item.get("distance_to_route_m", 0))
        return nearby_reports

    def distance_point_to_route_m(self, lat, lng, route_points):
        if not route_points:
            return float("inf")

        if len(route_points) == 1:
            return haversine(lat, lng, route_points[0][0], route_points[0][1])

        min_distance = float("inf")
        for index in range(len(route_points) - 1):
            lat1, lng1 = route_points[index]
            lat2, lng2 = route_points[index + 1]
            distance = self.distance_point_to_segment_m(lat, lng, lat1, lng1, lat2, lng2)
            if distance < min_distance:
                min_distance = distance

        return min_distance

    def distance_point_to_segment_m(self, lat, lng, lat1, lng1, lat2, lng2):
        """Tính khoảng cách từ điểm tới đoạn thẳng GPS bằng phép chiếu phẳng cục bộ."""
        earth_radius = 6371000.0
        lat0 = math.radians(lat)

        def to_xy(point_lat, point_lng):
            x = math.radians(point_lng - lng) * math.cos(lat0) * earth_radius
            y = math.radians(point_lat - lat) * earth_radius
            return x, y

        px, py = 0.0, 0.0
        ax, ay = to_xy(lat1, lng1)
        bx, by = to_xy(lat2, lng2)

        dx = bx - ax
        dy = by - ay

        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)

        t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))

        closest_x = ax + t * dx
        closest_y = ay + t * dy

        return math.hypot(px - closest_x, py - closest_y)

    def format_route_distance(self, distance_m):
        distance_m = float(distance_m or 0)
        if distance_m >= 1000:
            return f"{distance_m / 1000:.2f} km"
        return f"{distance_m:.0f} m"

    def format_route_duration(self, duration_s):
        duration_s = int(duration_s or 0)
        minutes = max(1, round(duration_s / 60))
        if minutes < 60:
            return f"{minutes} phút"
        hours = minutes // 60
        remain = minutes % 60
        return f"{hours} giờ {remain} phút" if remain else f"{hours} giờ"

    def update_route_result_ui(self, start_point, end_point, route_distance_m, route_duration_s, nearby_reports):
        count_by_status = {}
        for report in nearby_reports:
            status = self.normalize_report_status(report.get("status"))
            count_by_status[status] = count_by_status.get(status, 0) + 1

        status_parts = []
        for status_key in ["pending", "need_more", "approved", "processing", "resolved"]:
            count = count_by_status.get(status_key, 0)
            if count:
                status_parts.append(f"{self.get_report_status_label(status_key)}: {count}")

        status_summary = " | ".join(status_parts) if status_parts else "Không có ổ gà gần tuyến"

        self.lbl_route_result.setText(
            f"Tuyến ngắn nhất: {self.format_route_distance(route_distance_m)} "
            f"(~{self.format_route_duration(route_duration_s)}). "
            f"Tìm thấy {len(nearby_reports)} ổ gà trong phạm vi 25 m gần tuyến.\n"
            f"{status_summary}"
        )

        self.route_result_list.clear()

        for report in nearby_reports:
            status_text = self.get_report_status_label(report.get("status"))
            road_name = self.clean_report_road_name(report.get("address"))
            source_name = self.extract_source_from_report_address(
                report.get("address"),
                report.get("image_path")
            )
            distance_text = self.format_route_distance(report.get("distance_to_route_m", 0))

            item = QListWidgetItem(
                f"[{status_text}] #{report.get('id')} | Cách tuyến {distance_text}\n"
                f"{road_name} | Nguồn: {source_name}"
            )
            item.setData(Qt.UserRole, report)
            self.route_result_list.addItem(item)

        self.route_result_list.setVisible(bool(nearby_reports))

    def draw_shortest_route_on_map(self, route_points, start_point, end_point, nearby_reports, route_distance_m, route_duration_s):
        if not self.is_map_loaded:
            return

        route_points_json = json.dumps(route_points, ensure_ascii=False)
        start_json = json.dumps(start_point, ensure_ascii=False)
        end_json = json.dumps(end_point, ensure_ascii=False)

        js_reports = []
        for report in nearby_reports:
            popup_html = self.build_report_popup_html(
                title=f"Báo cáo #{report.get('id')}",
                address=report.get("address"),
                created_at=report.get("created_at"),
                image_count=report.get("image_count"),
                status=report.get("status"),
                source_name=self.extract_source_from_report_address(report.get("address"), report.get("image_path")),
                lat=report.get("latitude"),
                lng=report.get("longitude"),
                image_path=report.get("image_path"),
            )

            js_reports.append({
                "id": str(report.get("id")),
                "lat": report.get("latitude"),
                "lng": report.get("longitude"),
                "status": self.normalize_report_status(report.get("status")),
                "marker_color": self.get_report_marker_color(report.get("status")),
                "popup_html": popup_html,
                "image_path": report.get("image_path") or "",
            })

        reports_json = json.dumps(js_reports, ensure_ascii=False)
        distance_text = self.format_route_distance(route_distance_m)
        duration_text = self.format_route_duration(route_duration_s)
        distance_json = json.dumps(distance_text, ensure_ascii=False)
        duration_json = json.dumps(duration_text, ensure_ascii=False)

        js = f"""
            (function() {{
                if (typeof L === 'undefined') return;
                const m = (typeof map !== 'undefined') ? map : window.map;
                if (!m) return;

                const routePoints = {route_points_json};
                const startPoint = {start_json};
                const endPoint = {end_json};
                const reports = {reports_json};
                const distanceText = {distance_json};
                const durationText = {duration_json};

                if (!window.userRouteLayer) {{
                    window.userRouteLayer = L.layerGroup().addTo(m);
                }}
                window.userRouteLayer.clearLayers();
                window.userRouteReportMarkers = {{}};

                if (!window.openUserReportImage) {{
                    window.openUserReportImage = function(path) {{
                        function callBackend() {{
                            if (window.backend && window.backend.showReportImage) {{
                                window.backend.showReportImage(path);
                                return true;
                            }}
                            if (window.showReportImage) {{
                                window.showReportImage(path);
                                return true;
                            }}
                            return false;
                        }}

                        if (callBackend()) return;

                        if (typeof QWebChannel !== 'undefined' && window.qt && window.qt.webChannelTransport) {{
                            new QWebChannel(window.qt.webChannelTransport, function(channel) {{
                                window.backend = channel.objects.backend;
                                callBackend();
                            }});
                        }}
                    }};
                }}

                const routeLine = L.polyline(routePoints, {{
                    color: '#2563EB',
                    weight: 6,
                    opacity: 0.85
                }}).addTo(window.userRouteLayer);

                L.marker([startPoint.lat, startPoint.lng])
                    .bindPopup('<b>Điểm đầu</b><br>' + startPoint.name)
                    .addTo(window.userRouteLayer);

                L.marker([endPoint.lat, endPoint.lng])
                    .bindPopup('<b>Điểm cuối</b><br>' + endPoint.name + '<br><b>Quãng đường:</b> ' + distanceText + '<br><b>Thời gian dự kiến:</b> ' + durationText)
                    .addTo(window.userRouteLayer);

                reports.forEach(function(r) {{
                    const marker = L.circleMarker([r.lat, r.lng], {{
                        radius: 11,
                        color: '#ffffff',
                        weight: 3,
                        fillColor: r.marker_color,
                        fillOpacity: 0.98
                    }}).bindPopup(r.popup_html);

                    marker.on('popupopen', function(event) {{
                        const popupElement = event.popup.getElement();
                        if (!popupElement) return;
                        const btn = popupElement.querySelector('.view-user-report-image');
                        if (btn) {{
                            btn.onclick = function() {{ window.openUserReportImage(r.image_path || ''); }};
                        }}
                    }});

                    marker.addTo(window.userRouteLayer);
                    window.userRouteReportMarkers[String(r.id)] = marker;
                }});

                if (routePoints.length > 0) {{
                    m.fitBounds(routeLine.getBounds(), {{ padding: [45, 45] }});
                }}
            }})();
        """

        self.web_view.page().runJavaScript(js)

    def on_route_result_item_clicked(self, item):
        report = item.data(Qt.UserRole)
        if not report:
            return

        # Khi user chọn một ổ gà trong danh sách lộ trình:
        # - map zoom tới marker
        # - khung bên trái hiển thị ảnh đã detect + thông tin phân tích từ DB
        self.focus_route_report_on_map(report)
        self.show_report_detail_on_left_panel(report)

    def focus_route_report_on_map(self, report):
        if not self.is_map_loaded:
            return

        report_id_json = json.dumps(str(report.get("id")), ensure_ascii=False)
        lat = float(report.get("latitude"))
        lng = float(report.get("longitude"))

        js = f"""
            (function() {{
                if (typeof L === 'undefined') return;
                const m = (typeof map !== 'undefined') ? map : window.map;
                if (!m) return;

                const reportId = {report_id_json};
                if (window.userRouteReportMarkers && window.userRouteReportMarkers[reportId]) {{
                    const marker = window.userRouteReportMarkers[reportId];
                    m.setView([{lat}, {lng}], 18);
                    marker.openPopup();
                    return;
                }}

                m.setView([{lat}, {lng}], 18);
            }})();
        """
        self.web_view.page().runJavaScript(js)

    def clear_route_search(self):
        self.route_selected_points = {"start": None, "end": None}
        if hasattr(self, "txt_route_start"):
            self.txt_route_start.clear()
        if hasattr(self, "txt_route_end"):
            self.txt_route_end.clear()

        if hasattr(self, "route_result_list"):
            self.route_result_list.clear()
            self.route_result_list.setVisible(False)

        if hasattr(self, "route_picker_panel"):
            self.route_picker_panel.setVisible(False)

        self.active_route_point_key = None
        self.pending_set_route_point_from_gps = None
        self.current_route_points = []
        self.current_route_start_point = None
        self.current_route_end_point = None
        self.current_route_distance_m = 0
        self.current_route_duration_s = 0
        self.current_route_filter_active = False

        if hasattr(self, "lbl_route_result"):
            self.lbl_route_result.setText(
                "Nhập điểm đầu và điểm cuối để tìm tuyến ngắn nhất, sau đó hệ thống sẽ lọc các ổ gà nằm gần tuyến."
            )

        if self.is_map_loaded:
            self.web_view.page().runJavaScript("""
                (function() {
                    if (window.userRouteLayer) {
                        window.userRouteLayer.clearLayers();
                    }
                    window.userRouteReportMarkers = {};
                    if (window.routePickLayer) {
                        window.routePickLayer.clearLayers();
                        window.routePickMarkers = {};
                    }
                    if (window.setRoutePickActive) {
                        window.setRoutePickActive(false, '');
                    }
                })();
            """)

    # =========================
    # CHỌN MEDIA + GPS + MODEL
    # =========================

    def choose_demo_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn ảnh hoặc video demo",
            SAMPLE_VIDEO_DIR,
            "Media Files (*.jpg *.jpeg *.png *.bmp *.webp *.mp4 *.avi *.mov *.mkv *.wmv)",
        )

        if not file_path:
            return

        self.stop_video_demo(show_message=False)
        self.clear_pending_report()
        self.lbl_analysis_info.setText("Thông tin phân tích: Chưa có dữ liệu")
        self.lbl_alert.setText("Trạng thái: Đã chọn file, bấm Start để chạy")

        self.media_path = file_path
        self.video_path = file_path

        ext = Path(file_path).suffix.lower()
        self.media_type = "video" if ext in VIDEO_EXTS else "image"
        self.is_video_paused = False
        self.update_video_controls_visibility()
        self.update_play_pause_button_text()
        self.set_video_overlay_info(self.build_video_overlay_info())

        self.auto_find_gps_csv_for_media()

        if self.gps_csv_path:
            self.use_current_location = False
            self.current_lat = None
            self.current_lng = None
            self.btn_get_current_location.setEnabled(False)

            self.load_gps_csv(self.gps_csv_path)

        else:
            self.gps_points = []
            self.gps_timestamps = []
            self.gps_service.clear()

            self.use_current_location = False
            self.current_lat = None
            self.current_lng = None

            self.btn_get_current_location.setEnabled(True)

            expected_csv = Path(file_path).with_name(Path(file_path).stem + "_gps.csv")
            if self.show_need_current_location_dialog(expected_csv):
                self.get_current_location()

        self.update_demo_status()

    def choose_gps_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn file GPS CSV",
            os.path.dirname(self.video_path) if self.video_path else BASE_DIR,
            "CSV Files (*.csv)",
        )

        if not file_path:
            return

        self.gps_csv_path = file_path
        self.load_gps_csv(file_path)
        self.update_demo_status()

    def get_current_location(self):
        self.lbl_current_gps.setText("GPS: Đang lấy vị trí hiện tại...")

        self.gps_source = QGeoPositionInfoSource.createDefaultSource(self)

        if self.gps_source is None:
            self.use_current_location = False
            self.current_lat = None
            self.current_lng = None

            self.lbl_current_gps.setText(
                "GPS: Không tìm thấy nguồn định vị trên thiết bị."
            )

            QMessageBox.warning(
                self,
                "Không lấy được vị trí",
                "Thiết bị không hỗ trợ định vị hoặc chưa bật Location."
            )
            return

        self.gps_source.positionUpdated.connect(self.on_position_updated)
        self.gps_source.updateTimeout.connect(self.on_position_timeout)

        self.gps_source.requestUpdate(10000)

    def on_position_updated(self, position):
        coord = position.coordinate()

        self.current_lat = coord.latitude()
        self.current_lng = coord.longitude()
        self.use_current_location = True

        self.current_road_name = self.get_road_name_from_coordinates(
            self.current_lat,
            self.current_lng
        )
        
        self.lbl_current_gps.setText(
            f"GPS: Đang dùng vị trí hiện tại\n"
            f"Tọa độ: {self.current_lat:.6f}, {self.current_lng:.6f}"
        )

        self.lbl_alert.setText(
            f"Đã lấy vị trí hiện tại: {self.current_lat:.6f}, {self.current_lng:.6f}"
        )

        if self.is_map_loaded:
            self.web_view.page().runJavaScript(
                f"updateVehicle("
                f"{self.current_lat}, "
                f"{self.current_lng}, "
                f"`Vị trí hiện tại`, "
                f"`Vị trí hiện tại của thiết bị`"
                f");"
            )

        if self.pending_set_route_point_from_gps:
            point_key = self.pending_set_route_point_from_gps
            self.pending_set_route_point_from_gps = None
            self.pending_set_route_start_from_gps = False
            self.set_route_point_to_current_location(point_key)
        elif self.pending_set_route_start_from_gps:
            self.pending_set_route_start_from_gps = False
            self.set_route_start_to_current_location()

        self.update_demo_status()

    def on_position_timeout(self):
        self.pending_set_route_point_from_gps = None
        self.pending_set_route_start_from_gps = False
        self.use_current_location = False
        self.current_lat = None
        self.current_lng = None

        self.lbl_current_gps.setText(
            "GPS: Không lấy được vị trí hiện tại."
        )

        QMessageBox.warning(
            self,
            "Không lấy được vị trí",
            "Không lấy được vị trí hiện tại.\n"
            "Hãy kiểm tra máy đã bật Location chưa."
        )

    def choose_model_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn model YOLO .pt",
            BASE_DIR,
            "YOLO model (*.pt)",
        )

        if not file_path:
            return

        self.model_path = file_path
        self.analysis_service.set_model_path(file_path)
        self.update_demo_status()

    def auto_find_gps_csv_for_media(self):
        if not self.media_path:
            return

        media = Path(self.media_path)
        candidate = media.with_name(media.stem + "_gps.csv")
        self.gps_csv_path = str(candidate) if candidate.exists() else None

    # def update_demo_status(self):
    #     video_text = os.path.basename(self.media_path) if self.media_path else "chưa chọn"
    #     gps_text = os.path.basename(self.gps_csv_path) if self.gps_csv_path else "chưa tìm thấy"
    #     model_exists = os.path.exists(self.model_path)
    #     model_text = self.model_path if model_exists else f"CHƯA TÌM THẤY: {self.model_path}"

    #     self.lbl_demo_status.setText(
    #         f"Chọn File: {video_text}\n"
    #         f"GPS CSV: {gps_text}\n"
    #         f"Model cố định: {model_text}"
    #     )

    def update_demo_status(self):
        video_text = os.path.basename(self.media_path) if self.media_path else "chưa chọn"

        if self.gps_csv_path:
            gps_text = f"Đang dùng CSV: {os.path.basename(self.gps_csv_path)}"
        elif self.use_current_location and self.current_lat is not None and self.current_lng is not None:
            gps_text = f"Đang dùng vị trí hiện tại: {self.current_lat:.6f}, {self.current_lng:.6f}"
        else:
            gps_text = "chưa có GPS"

        model_exists = os.path.exists(self.model_path)
        model_text = self.model_path if model_exists else f"CHƯA TÌM THẤY: {self.model_path}"

        self.lbl_demo_status.setText(
            f"Chọn File: {video_text}\n"
            f"GPS: {gps_text}\n"
            f"Model cố định: {model_text}"
        )

    def load_gps_csv(self, csv_path):
        try:
            self.gps_points = self.gps_service.load_csv(csv_path)
            self.gps_timestamps = self.gps_service.gps_timestamps
            self.detected_potholes.clear()
            self.draw_route_on_map()
            QMessageBox.information(self, "GPS CSV", f"Đã load {len(self.gps_points)} điểm GPS.")
        except Exception as error:
            QMessageBox.critical(self, "Lỗi GPS CSV", f"Không thể đọc file GPS CSV.\n\nChi tiết lỗi:\n{error}")
            self.gps_points = []
            self.gps_timestamps = []
            self.gps_service.clear()

    def draw_route_on_map(self):
        if not self.is_map_loaded or not self.gps_points:
            return

        if len(self.gps_points) < 2:
            point = self.gps_points[0]
            self.web_view.page().runJavaScript(
                f"updateVehicle({point['latitude']}, {point['longitude']}, `Ảnh`, `{self.escape_js_text(point['road_name'])}`);"
            )
            return

        route_points = [[point["latitude"], point["longitude"]] for point in self.gps_points]
        route_json = self.escape_js_text(json.dumps(route_points))
        self.web_view.page().runJavaScript(f"setRoute(`{route_json}`);")

    def get_gps_by_time(self, current_time):
        return self.gps_service.get_by_time(current_time)

    def load_yolo_model_if_needed(self):
        try:
            self.analysis_service.load_model_if_needed()
            return True
        except Exception as error:
            QMessageBox.warning(self, "Lỗi model", str(error))
            return False

    # =========================
    # VIDEO / IMAGE PROCESSING
    # =========================

    def start_video_demo(self):
        if self.media_type == "image":
            if not self.media_path:
                QMessageBox.warning(self, "Thiếu ảnh", "Vui lòng chọn ảnh demo trước.")
                return

            if not self.choose_camera_setup():
                self.lbl_alert.setText("Trạng thái: Đã hủy chọn setup")
                return

            self.lbl_alert.setText("Trạng thái: Đang xử lý ảnh...")
            self.update_video_controls_visibility()
            self.update_play_pause_button_text()
            self.process_demo_image()
            return

        if not self.video_path:
            QMessageBox.warning(self, "Thiếu video", "Vui lòng chọn video demo trước.")
            return

        # if not self.gps_points:
        #     QMessageBox.warning(self, "Thiếu GPS CSV", "Vui lòng chọn hoặc tạo file GPS CSV tương ứng với video.")
        #     return
        if not self.gps_points and not self.use_current_location:
            if self.show_need_current_location_dialog():
                self.get_current_location()
            return
        
        if not self.choose_camera_setup():
            return

        self.clear_pending_report()
        self.stop_video_demo(show_message=False)
        self.cap = cv2.VideoCapture(self.video_path)

        if not self.cap.isOpened():
            QMessageBox.critical(self, "Lỗi video", "Không mở được video.")
            self.cap = None
            return

        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.fps <= 0:
            self.fps = 25

        self.frame_index = 0
        self.last_saved_pothole_time = -999
        self.last_saved_pothole_location = None
        self.video_frame_saved_count = 0
        self.detected_potholes.clear()
        self.analysis_service.reset_depth_cache()
        self.is_video_paused = False
        self.update_video_controls_visibility()
        self.update_play_pause_button_text()

        self.draw_route_on_map()

        if not self.load_yolo_model_if_needed():
            self.stop_video_demo(show_message=False)
            return

        self.start_video_timer()
        self.lbl_alert.setText("Trạng thái: Đang chạy video demo")

    def stop_video_demo(self, show_message=True):
        if self.video_timer.isActive():
            self.video_timer.stop()

        if self.cap is not None:
            self.cap.release()
            self.cap = None

        self.is_video_paused = False
        self.update_play_pause_button_text()

        if show_message:
            self.lbl_alert.setText("Trạng thái: Đã dừng video")

    def process_video_frame(self):
        if self.cap is None:
            return

        ret, frame = self.cap.read()
        if not ret:
            self.stop_video_demo(show_message=False)
            self.lbl_alert.setText("Trạng thái: Video đã chạy hết")
            self.update_play_pause_button_text()
            return

        self.frame_index += 1
        self.current_time = self.frame_index / self.fps
        
        if self.gps_points:
            self.current_lat, self.current_lng, self.current_road_name = self.get_gps_by_time(self.current_time)
        elif self.use_current_location:
            self.current_road_name = "Vị trí hiện tại của thiết bị"
        else:
            self.current_lat = None
            self.current_lng = None
            self.current_road_name = "Chưa có GPS"        
        time_text = format_video_time(self.current_time)
        self.update_current_gps_ui(time_text)

        try:
            analysis = self.analysis_service.analyze_frame(
                frame=frame,
                setup_name=self.current_setup_name,
                frame_index=self.frame_index,
                use_depth_cache=True,
            )
        except Exception as error:
            self.lbl_alert.setText(f"Lỗi detect YOLO: {error}")
            self.show_frame_on_label(frame)
            return

        annotated_frame = analysis["annotated_frame"]
        self.current_pothole_area_m2 = analysis["area_m2"]

        if analysis.get("error"):
            self.lbl_alert.setText(analysis["error"])

        if analysis["depth_info"] is not None:
            self.update_analysis_info(analysis["depth_info"])

        # if analysis["has_pothole"]:
        #     self.handle_detected_pothole(annotated_frame, analysis["confidence"])
        if analysis["has_pothole"]:
            self.handle_detected_pothole(
                original_frame=frame,
                detected_frame=annotated_frame,
                confidence=analysis["confidence"]
            )
            
        self.show_frame_on_label(annotated_frame)

    def update_current_gps_ui(self, time_text):
        if self.current_lat is None or self.current_lng is None:
            return

        info_text = self.build_video_overlay_info(time_text=time_text)
        self.lbl_current_gps.setText(info_text)
        self.set_video_overlay_info(info_text)

        safe_road_name = self.escape_js_text(self.current_road_name)

        self.web_view.page().runJavaScript(
            f"updateVehicle("
            f"{self.current_lat}, "
            f"{self.current_lng}, "
            f"`{time_text}`, "
            f"`{safe_road_name}`"
            f");"
        )

    def process_demo_image(self):
        self.clear_pending_report()
        if not self.media_path:
            QMessageBox.warning(self, "Thiếu ảnh", "Vui lòng chọn ảnh demo trước.")
            return

        if not self.current_setup_name:
            QMessageBox.warning(self, "Thiếu setup", "Vui lòng chọn setup camera trước khi chạy.")
            return

        if not self.load_yolo_model_if_needed():
            self.lbl_alert.setText("Trạng thái: Không load được model YOLO")
            return

        frame = cv2.imread(self.media_path)
        if frame is None:
            QMessageBox.critical(self, "Lỗi ảnh", "Không đọc được ảnh.")
            self.lbl_alert.setText("Trạng thái: Không đọc được ảnh")
            return

        # self.current_time = 0
        # self.current_lat, self.current_lng, self.current_road_name = self.get_gps_by_time(0)
        # self.update_image_gps_ui()

        self.current_time = 0

        if self.gps_points:
            self.current_lat, self.current_lng, self.current_road_name = self.get_gps_by_time(0)
        elif self.use_current_location:
            self.current_road_name = "Vị trí hiện tại của thiết bị"
        else:
            self.current_lat = None
            self.current_lng = None
            self.current_road_name = "Chưa có GPS"

        self.update_image_gps_ui()

        try:
            analysis = self.analysis_service.analyze_frame(
                frame=frame,
                setup_name=self.current_setup_name,
                frame_index=0,
                use_depth_cache=False,
            )
        except Exception as error:
            self.lbl_alert.setText(f"Lỗi xử lý ảnh: {error}")
            self.show_frame_on_label(frame)
            return

        annotated_frame = analysis["annotated_frame"]
        self.current_pothole_area_m2 = analysis["area_m2"]

        if analysis["has_pothole"]:
            if analysis["depth_info"] is not None:
                self.update_analysis_info(analysis["depth_info"])

            # self.handle_detected_pothole(annotated_frame, analysis["confidence"])
            self.handle_detected_pothole(
                original_frame=frame,
                detected_frame=annotated_frame,
                confidence=analysis["confidence"]
            )
            
            status_text = (
                f"Trạng thái: Đã xử lý ảnh | Setup: {self.current_setup_name} | "
                f"Diện tích: {analysis['area_m2']:.3f} m2"
            )
            if analysis.get("error"):
                status_text += f" | {analysis['error']}"
            self.lbl_alert.setText(status_text)
        else:
            self.clear_pending_report()
            self.lbl_alert.setText("Trạng thái: Không phát hiện ổ gà trong ảnh")

        self.show_frame_on_label(annotated_frame)

    def update_image_gps_ui(self):
        if self.current_lat is not None and self.current_lng is not None:
            info_text = self.build_video_overlay_info()
            self.lbl_current_gps.setText(info_text)
            self.set_video_overlay_info(info_text)

            safe_road_name = self.escape_js_text(self.current_road_name)
            self.web_view.page().runJavaScript(
                f"updateVehicle({self.current_lat}, {self.current_lng}, `Ảnh`, `{safe_road_name}`);"
            )
        else:
            info_text = "Chưa có GPS. Hãy bấm 'Lấy vị trí hiện tại'."
            self.lbl_current_gps.setText(info_text)
            self.set_video_overlay_info(info_text)

    def update_analysis_info(self, depth_info):
        self.current_depth_info = depth_info
        self.current_analysis_html = build_analysis_html(depth_info)
        self.lbl_analysis_info.setText(self.current_analysis_html)

    def build_saved_report_analysis_html(self, analysis_html=None, area_m2=None, setup_name=None):
        """Chuẩn hóa nội dung lưu vào cột analysis_html.

        analysis_html từ build_analysis_html(depth_info) đã có bố cục 2 cột
        nước/ánh sáng và độ sâu. Hàm này bổ sung thêm diện tích + setup vào
        chính cột analysis_html để khi mở lại marker/report vẫn hiện đủ dữ liệu.
        """
        base_html = str(analysis_html or self.current_analysis_html or "").strip()

        try:
            area_value = float(area_m2 if area_m2 is not None else self.current_pothole_area_m2 or 0)
        except Exception:
            area_value = 0.0

        setup_text = setup_name if setup_name is not None else self.current_setup_name
        safe_setup = html.escape(str(setup_text or "--"))

        area_html = f"""
            <div style='margin-top:8px;padding-top:8px;border-top:1px solid #86EFAC;'>
                <b>THÔNG TIN DIỆN TÍCH</b><br>
                <b>Diện tích ước lượng:</b> {area_value:.3f} m²<br>
                <b>Setup camera:</b> {safe_setup}
            </div>
        """

        if not base_html:
            base_html = "Chưa có thông tin ánh sáng / nước / độ sâu trong database."

        if "THÔNG TIN DIỆN TÍCH" in base_html:
            return base_html

        return f"{base_html}{area_html}"

    def make_path_cache_keys(self, path):
        """Tạo nhiều biến thể key cho đường dẫn ảnh để tránh lệch \\ và /."""
        if not path:
            return []

        raw = str(path).strip()
        if not raw:
            return []

        keys = {raw, raw.replace("\\", "/"), raw.replace("/", "\\")}

        for candidate in list(keys):
            try:
                keys.add(os.path.normcase(os.path.abspath(candidate)))
            except Exception:
                pass
            try:
                keys.add(os.path.normcase(candidate))
            except Exception:
                pass

        return [key for key in keys if key]

    def cache_report_preview_detail(self, detail):
        """Lưu cache thông tin report theo mọi đường dẫn ảnh liên quan."""
        if not detail:
            return

        cached = dict(detail)
        image_fields = [
            "image_path",
            "display_image_path",
            "detected_image_path",
            "original_image_path",
        ]

        for field in image_fields:
            for key in self.make_path_cache_keys(cached.get(field)):
                self.report_preview_cache_by_image_path[key] = cached

    def get_cached_report_preview_detail(self, image_path):
        for key in self.make_path_cache_keys(image_path):
            detail = self.report_preview_cache_by_image_path.get(key)
            if detail:
                return dict(detail)
        return None

    def show_frame_on_label(self, frame):
        self.last_display_frame = frame.copy() if frame is not None else None
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)
        self.video_label.setPixmap(
            pixmap.scaled(
                self.video_label.width(),
                self.video_label.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )
        self.update_fullscreen_frame()

    # =========================
    # LƯU REPORT TỪ VIDEO/ẢNH DEMO
    # =========================
    def clear_pending_report(self):
        self.pending_report_data = None
        self.pending_report_frame = None
        self.pending_report_is_saved = False

        if hasattr(self, "btn_save_report"):
            self.btn_save_report.setEnabled(False)
            
    def can_save_new_pothole(self):
        if self.current_lat is None or self.current_lng is None:
            return False

        # Với ảnh: cho phép đi tiếp để kiểm tra trùng bằng GPS radius
        if self.media_type == "image":
            return True

        # Với video: vẫn chống lưu quá dày theo thời gian
        if self.current_time - self.last_saved_pothole_time < 2.5:
            return False

        return True
    
    def normalize_report_status(self, status):
        raw = str(status or "pending").strip().lower()
        raw_no_space = raw.replace(" ", "_").replace("-", "_")

        aliases = {
            "": "pending",
            "none": "pending",
            "null": "pending",
            "pending": "pending",
            "waiting": "waiting",
            "draft": "waiting",
            "chờ_duyệt": "pending",
            "cho_duyet": "pending",
            "chua_duyet": "pending",
            "chưa_duyệt": "pending",
            "approved": "approved",
            "da_duyet": "approved",
            "đã_duyệt": "approved",
            "processing": "processing",
            "in_progress": "processing",
            "dang_xu_ly": "processing",
            "đang_xử_lý": "processing",
            "resolved": "resolved",
            "done": "resolved",
            "handled": "resolved",
            "da_xu_ly": "resolved",
            "đã_xử_lý": "resolved",
            "need_more": "need_more",
            "need_supplement": "need_more",
            "supplement_required": "need_more",
            "can_bo_sung": "need_more",
            "cần_bổ_sung": "need_more",
            "invalid": "invalid",
            "rejected": "invalid",
            "khong_hop_le": "invalid",
            "không_hợp_lệ": "invalid",
        }

        if raw_no_space in aliases:
            return aliases[raw_no_space]
        if raw in REPORT_STATUS_INFO:
            return raw
        return "pending"

    def get_report_status_info(self, status):
        return REPORT_STATUS_INFO.get(
            self.normalize_report_status(status),
            REPORT_STATUS_INFO["pending"]
        )

    def get_report_status_label(self, status):
        return self.get_report_status_info(status)["label"]

    def get_report_status_badge_html(self, status):
        info = self.get_report_status_info(status)
        return (
            f"<span style='background:{info['bg_color']};color:{info['text_color']};"
            f"border:1px solid {info['border_color']};padding:2px 7px;"
            f"border-radius:999px;font-weight:800'>{html.escape(info['label'])}</span>"
        )

    def get_report_marker_color(self, status):
        return self.get_report_status_info(status)["marker_color"]

    def get_media_source_name(self, path_or_name):
        """Lấy tên file gốc để hiển thị ở marker, không kèm chữ Video/Ảnh."""
        if not path_or_name:
            return "--"
        return os.path.basename(str(path_or_name).strip()) or "--"

    def is_video_source(self, source_name):
        return Path(source_name or "").suffix.lower() in VIDEO_EXTS

    def clean_report_road_name(self, address):
        """Tách riêng tên đường khỏi chuỗi address cũ trong database."""
        text = str(address or "--").strip()

        if text.startswith("Tuyến đường:"):
            text = text[len("Tuyến đường:"):].strip()

        for token in ("Nguồn:", "Thời điểm video:"):
            if token in text:
                text = text.split(token, 1)[0].strip()

        return text or "--"

    def extract_source_from_report_address(self, address, fallback_path=""):
        """Đọc tên file nguồn từ address cũ/mới. Ví dụ: Nguồn: Video pothole.jpg -> pothole.jpg."""
        text = str(address or "")
        source_name = ""

        if "Nguồn:" in text:
            after_source = text.split("Nguồn:", 1)[1].strip()
            if after_source.lower().startswith("video "):
                after_source = after_source[6:].strip()
            if "Thời điểm video:" in after_source:
                after_source = after_source.split("Thời điểm video:", 1)[0].strip()
            source_name = after_source.strip()

        if not source_name and fallback_path:
            source_name = self.get_media_source_name(fallback_path)

        return self.get_media_source_name(source_name)

    def extract_video_time_from_report_address(self, address, default_time=""):
        text = str(address or "")
        if "Thời điểm video:" not in text:
            return default_time
        return text.split("Thời điểm video:", 1)[1].strip().split()[0]

    def build_report_popup_html(
        self,
        title,
        address,
        created_at,
        image_count,
        status="pending",
        source_name="",
        time_text="",
        lat=None,
        lng=None,
        image_path="",
    ):
        """Tạo popup marker theo format thống nhất cho user/admin."""
        road_name = self.clean_report_road_name(address)
        source_name = self.extract_source_from_report_address(address, source_name)
        is_video = self.is_video_source(source_name)
        time_text = self.extract_video_time_from_report_address(address, time_text)

        status = self.normalize_report_status(status)
        status_badge = self.get_report_status_badge_html(status)

        rows = [
            f"<div style='font-weight:900;color:#2563EB;margin-bottom:7px;font-size:15px'>{html.escape(str(title))}</div>",
            f"<div><b>Trạng thái:</b> {status_badge}</div>",
            f"<div><b>Tuyến đường:</b> {html.escape(road_name)}</div>",
            f"<div><b>Nguồn:</b> {html.escape(source_name)}</div>",
        ]

        if is_video and time_text:
            rows.append(f"<div><b>Thời điểm video:</b> {html.escape(str(time_text))}</div>")

        rows.append(f"<div><b>Thời gian gửi:</b> {html.escape(str(created_at or '--'))}</div>")
        rows.append(f"<div><b>Số file:</b> {int(image_count or 0)}</div>")

        if lat is not None and lng is not None:
            rows.append(f"<div><b>Tọa độ:</b> {float(lat):.6f}, {float(lng):.6f}</div>")

        if image_path:
            rows.append(
                "<button class='view-user-report-image' "
                "style='margin-top:8px;background:#2563EB;color:white;border:none;"
                "border-radius:7px;padding:6px 10px;font-weight:800;cursor:pointer'>"
                "Xem ảnh</button>"
            )

        return "<div style='min-width:260px;line-height:1.45;font-size:13px;color:#111827'>" + "".join(rows) + "</div>"

    def add_temp_pothole_marker_to_map(self, lat, lng, road_name, source_name, time_text, confidence):
        popup_html = self.build_report_popup_html(
            title="Ổ gà vừa phát hiện",
            address=f"Tuyến đường: {road_name} Nguồn: {source_name}" + (
                f" Thời điểm video: {time_text}" if self.is_video_source(source_name) and time_text else ""
            ),
            created_at="Chưa gửi",
            image_count=1,
            status="waiting",
            source_name=source_name,
            time_text=time_text,
            lat=lat,
            lng=lng,
        )

        js = f"""
            (function() {{
                if (typeof L === 'undefined') return;
                const m = (typeof map !== 'undefined') ? map : window.map;
                if (!m) return;

                if (!window.userTempPotholeLayer) {{
                    window.userTempPotholeLayer = L.layerGroup().addTo(m);
                }}

                const marker = L.circleMarker([{float(lat)}, {float(lng)}], {{
                    radius: 9,
                    color: '#ffffff',
                    weight: 2,
                    fillColor: '#2563EB',
                    fillOpacity: 0.95
                }}).bindPopup({json.dumps(popup_html, ensure_ascii=False)});

                marker.addTo(window.userTempPotholeLayer);
                marker.openPopup();
            }})();
        """
        self.web_view.page().runJavaScript(js)

    def handle_detected_pothole(self, original_frame, detected_frame, confidence=1.0):
        if not self.can_save_new_pothole():
            return

        if self.current_lat is None or self.current_lng is None:
            self.lbl_alert.setText(
                "Phát hiện ổ gà nhưng chưa có GPS, chưa thể tạo báo cáo."
            )
            return

        self.video_frame_saved_count += 1
        time_text = format_video_time(self.current_time)

        self.pending_original_frame = original_frame.copy()
        self.pending_detected_frame = detected_frame.copy()

        # Lưu bản HTML đầy đủ vào pending data để khi bấm Báo cáo,
        # cột analysis_html trong database có đủ 2 cột nước/ánh sáng, độ sâu,
        # kèm diện tích và setup camera.
        saved_analysis_html = self.build_saved_report_analysis_html(
            analysis_html=self.current_analysis_html,
            area_m2=self.current_pothole_area_m2,
            setup_name=self.current_setup_name,
        )

        self.pending_report_data = {
            "latitude": self.current_lat,
            "longitude": self.current_lng,
            "confidence": confidence,
            "frame_time": self.current_time,
            "time_text": time_text,
            "video_path": self.video_path,
            "road_name": self.current_road_name,
            "analysis_html": saved_analysis_html,
            "area_m2": self.current_pothole_area_m2,
            "setup_name": self.current_setup_name,
        }

        self.pending_report_is_saved = False

        if hasattr(self, "btn_save_report"):
            self.btn_save_report.setEnabled(True)

        self.last_saved_pothole_time = self.current_time
        self.last_saved_pothole_location = (
            self.current_lat,
            self.current_lng
        )

        self.detected_potholes.append(
            (self.current_lat, self.current_lng)
        )

        source_name = self.get_media_source_name(self.media_path or self.video_path)
        marker_time_text = time_text if self.is_video_source(source_name) else ""

        # Marker tạm, chưa lưu DB.
        self.add_temp_pothole_marker_to_map(
            lat=self.current_lat,
            lng=self.current_lng,
            road_name=self.current_road_name,
            source_name=source_name,
            time_text=marker_time_text,
            confidence=confidence,
        )

        self.play_alert_sound()

        self.lbl_alert.setText(
            f"Đã phát hiện ổ gà tại {time_text} | "
            f"GPS {self.current_lat:.6f}, {self.current_lng:.6f} | "
            f"Confidence {confidence:.2f}. "
            f"Diện tích: {self.current_pothole_area_m2:.3f} m². "
            # f"Bấm nút 'Báo cáo' để gửi cho admin."
        )
    
    def find_nearby_pothole_report(self, lat, lng, radius_m=2):
        reports = self.report_repository.get_all_report_locations()

        nearest_report = None
        nearest_distance = None

        for report in reports:
            old_lat = report.get("latitude")
            old_lng = report.get("longitude")

            if old_lat is None or old_lng is None:
                continue

            distance = haversine(
                lat,
                lng,
                old_lat,
                old_lng
            )

            if distance <= radius_m:
                if nearest_distance is None or distance < nearest_distance:
                    nearest_distance = distance
                    nearest_report = report

        return nearest_report, nearest_distance
    
    def save_report_frame_to_file(self, frame, suffix):
        report_dir = Path(DATABASE_PATH).parent / "reported_frames"
        report_dir.mkdir(parents=True, exist_ok=True)

        media_stem = Path(self.media_path or "media").stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        file_path = report_dir / f"{media_stem}_{timestamp}_{suffix}.jpg"

        cv2.imwrite(str(file_path), frame)

        return str(file_path)
    
    def mark_pothole_at_current_location(self):
        """Dùng cho demo khi chưa có model, hoặc muốn đánh dấu thủ công tại vị trí xe hiện tại."""
        if self.current_lat is None or self.current_lng is None:
            QMessageBox.warning(self, "Chưa có vị trí xe", "Hãy chạy video demo trước khi đánh dấu ổ gà.")
            return

        blank_frame = None
        if self.cap is not None:
            pos = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, pos - 1))
            ret, frame = self.cap.read()
            if ret:
                blank_frame = frame
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, pos)

        if blank_frame is None:
            import numpy as np
            blank_frame = 255 * np.ones((480, 640, 3), dtype="uint8")

        self.handle_detected_pothole(blank_frame, confidence=1.0)
        
    def get_road_name_from_coordinates(self, lat, lng):
        try:
            data = self.geocoding_service.reverse(lat, lng)

            address = data.get("address", {})
            road_name = (
                address.get("road")
                or address.get("pedestrian")
                or address.get("residential")
                or address.get("suburb")
                or address.get("neighbourhood")
            )

            display_name = data.get("display_name", "")

            if road_name:
                return road_name

            if display_name:
                return display_name.split(",")[0].strip()

            return f"Tọa độ {lat:.6f}, {lng:.6f}"

        except Exception as error:
            print("Lỗi reverse geocoding:", error)
            return f"Tọa độ {lat:.6f}, {lng:.6f}"

    def play_alert_sound(self):
        current_time = time.time()

        if current_time - self.last_alert_sound_time >= self.alert_sound_cooldown:
            if winsound is not None:
                winsound.Beep(1200, 300)
            self.last_alert_sound_time = current_time

    # =========================
    # BÁO CÁO THỦ CÔNG CŨ
    # =========================

    def choose_images(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn ảnh hoặc video ổ gà",
            "",
            "Images/Videos (*.jpg *.jpeg *.png *.bmp *.webp *.mp4 *.avi *.mov *.mkv *.wmv)",
        )

        if not file_paths:
            return

        valid_paths = [path for path in file_paths if path.lower().endswith(MEDIA_EXTS)]
        if not valid_paths:
            QMessageBox.warning(self, "File không hợp lệ", "Vui lòng chọn ảnh hoặc video đúng định dạng.")
            return

        self.selected_image_paths = valid_paths
        self.selected_image_list.clear()
        for path in valid_paths:
            self.selected_image_list.addItem(os.path.basename(path))
        self.lbl_selected_images.setText(f"Đã chọn {len(valid_paths)} file ảnh/video")

    def save_report(self):
        if self.pending_report_is_saved:
            self.show_report_success_dialog(
                "Đã gửi báo cáo",
                "Báo cáo này đã được gửi trước đó.",
                "Bạn không cần gửi lại cùng một dữ liệu báo cáo."
            )
            return

        if (
            not self.pending_report_data
            or self.pending_original_frame is None
            or self.pending_detected_frame is None
        ):
            QMessageBox.warning(
                self,
                "Chưa có dữ liệu báo cáo",
                "Vui lòng bấm 'Chạy' và phát hiện ổ gà trước khi bấm 'Báo cáo'."
            )
            return

        report = self.pending_report_data

        lat = report["latitude"]
        lng = report["longitude"]
        confidence = report["confidence"]
        frame_time = report["frame_time"]
        video_path = report["video_path"]
        road_name = report["road_name"]
        analysis_html = report["analysis_html"]
        area_m2 = report["area_m2"]
        setup_name = report["setup_name"]

        try:
            original_image_path = self.save_report_frame_to_file(
                self.pending_original_frame,
                "original"
            )

            detected_image_path = self.save_report_frame_to_file(
                self.pending_detected_frame,
                "detected"
            )

            nearby_report, distance = self.find_nearby_pothole_report(
                lat,
                lng,
                radius_m=2
            )

            if nearby_report is not None:
                old_report_id = nearby_report["id"]

                self.add_report_image_detail(
                    report_id=old_report_id,
                    original_image_path=original_image_path,
                    detected_image_path=detected_image_path,
                    analysis_html=analysis_html,
                    area_m2=area_m2,
                    setup_name=setup_name
                )

                self.report_repository.increase_image_count(old_report_id)

                self.pending_report_is_saved = True
                self.pending_report_data = None
                self.pending_original_frame = None
                self.pending_detected_frame = None

                if hasattr(self, "btn_save_report"):
                    self.btn_save_report.setEnabled(False)

                self.show_report_success_dialog(
                    "Đã thêm ảnh vào báo cáo có sẵn",
                    "Ổ gà đã tồn tại gần vị trí này nên hệ thống không tạo báo cáo mới.",
                    f"Đã thêm ảnh vào báo cáo #{old_report_id}."
                )
                return

            report_id, created_at = self.create_report_with_detail(
                latitude=lat,
                longitude=lng,
                confidence=confidence,
                frame_time=frame_time,
                original_image_path=original_image_path,
                detected_image_path=detected_image_path,
                video_path=video_path,
                road_name=road_name,
                analysis_html=analysis_html,
                area_m2=area_m2,
                setup_name=setup_name,
                reporter_user_id=self.current_user.get("id"),
            )

            source_name = os.path.basename(video_path)
            marker_address = f"Tuyến đường: {road_name} Nguồn: {source_name}"
            if Path(source_name).suffix.lower() in VIDEO_EXTS:
                marker_address += f" Thời điểm video: {format_video_time(frame_time)}"

            self.add_report_marker_to_map(
                lat,
                lng,
                marker_address,
                created_at,
                1,
                detected_image_path,
                analysis_html,
                "pending",
                report_id=report_id,
                area_m2=area_m2,
                setup_name=setup_name,
                original_image_path=original_image_path,
                detected_image_path=detected_image_path,
            )

            self.report_list.insertItem(
                0,
                f"[Chưa duyệt] #{report_id} | {created_at} | {road_name} | Nguồn: {source_name} | 1 ảnh"
            )

            self.pending_report_is_saved = True
            self.pending_report_data = None
            self.pending_original_frame = None
            self.pending_detected_frame = None

            if hasattr(self, "btn_save_report"):
                self.btn_save_report.setEnabled(False)

            self.lbl_alert.setText(
                f"Đã gửi báo cáo cho admin | "
                f"GPS {lat:.6f}, {lng:.6f} | Confidence {confidence:.2f}"
            )

            self.show_report_success_dialog(
                "Gửi báo cáo thành công",
                "Báo cáo ổ gà đã được lưu vào database và gửi cho admin.",
                f"Tuyến đường: {road_name}\n"
                f"GPS: {lat:.6f}, {lng:.6f}\n"
                f"Confidence: {confidence:.2f} | Diện tích: {area_m2:.3f} m²"
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Lỗi gửi báo cáo",
                f"Không thể gửi báo cáo.\n\nChi tiết lỗi:\n{error}"
            )

    def load_existing_reports(self, silent=False):
        if not os.path.exists(DATABASE_PATH):
            return

        # Khi app user đang mở song song với app admin, admin có thể đổi trạng thái
        # trực tiếp trong SQLite. Vì vậy mỗi lần đọc lại cần xóa marker/list cũ
        # trước, nếu không sẽ bị trùng marker hoặc vẫn thấy trạng thái cũ.
        if hasattr(self, "report_list"):
            self.report_list.clear()
        self.pending_markers.clear()
        self.report_preview_cache_by_image_path.clear()
        self.clear_user_report_markers_on_map()

        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(pothole_report_images)")
            image_columns = [column[1] for column in cursor.fetchall()]

            image_path_expr = "COALESCE(i.image_path, '')" if "image_path" in image_columns else "''"
            detected_path_expr = "COALESCE(i.detected_image_path, '')" if "detected_image_path" in image_columns else "''"
            display_image_expr = f"COALESCE(NULLIF({detected_path_expr}, ''), NULLIF({image_path_expr}, ''), '')"
            image_analysis_expr = "COALESCE(i.analysis_html, '')" if "analysis_html" in image_columns else "''"
            area_expr = "COALESCE(i.area_m2, 0)" if "area_m2" in image_columns else "0"
            setup_expr = "COALESCE(i.setup_name, '')" if "setup_name" in image_columns else "''"

            cursor.execute(f"""
                SELECT 
                    r.id,
                    r.address,
                    r.latitude,
                    r.longitude,
                    r.image_count,
                    r.created_at,
                    COALESCE(r.status, 'pending') AS status,
                    {display_image_expr} AS image_path,
                    {image_path_expr} AS original_image_path,
                    {detected_path_expr} AS detected_image_path,
                    COALESCE(NULLIF({image_analysis_expr}, ''), r.analysis_html, '') AS analysis_html,
                    {area_expr} AS area_m2,
                    {setup_expr} AS setup_name
                FROM pothole_reports r
                LEFT JOIN pothole_report_images i
                    ON r.id = i.report_id
                GROUP BY r.id
                ORDER BY r.id DESC
            """)

            rows = cursor.fetchall()
            conn.close()

            for (
                report_id,
                address,
                lat,
                lng,
                image_count,
                created_at,
                status,
                image_path,
                original_image_path,
                detected_image_path,
                analysis_html,
                area_m2,
                setup_name,
            ) in rows:
                status = self.normalize_report_status(status)
                status_text = self.get_report_status_label(status)
                road_name = self.clean_report_road_name(address)
                source_name = self.extract_source_from_report_address(address, image_path)

                self.report_list.addItem(
                    f"[{status_text}] #{report_id} | {created_at} | {road_name} | Nguồn: {source_name} | {image_count} ảnh"
                )

                marker_data = {
                    "report_id": report_id,
                    "lat": lat,
                    "lng": lng,
                    "address": address,
                    "created_at": created_at,
                    "image_count": image_count,
                    "image_path": image_path,
                    "original_image_path": original_image_path or "",
                    "detected_image_path": detected_image_path or "",
                    "display_image_path": image_path or detected_image_path or original_image_path or "",
                    "analysis_html": analysis_html or "",
                    "area_m2": float(area_m2 or 0),
                    "setup_name": setup_name or "",
                    "status": status or "pending",
                }

                self.cache_report_preview_detail(marker_data)

                if self.is_map_loaded:
                    self.add_report_marker_to_map(
                        lat,
                        lng,
                        address,
                        created_at,
                        image_count,
                        image_path,
                        analysis_html,
                        status or "pending",
                        report_id=report_id,
                        area_m2=area_m2,
                        setup_name=setup_name,
                        original_image_path=original_image_path,
                        detected_image_path=detected_image_path,
                    )
                else:
                    self.pending_markers.append(marker_data)

        except Exception as error:
            if not silent:
                QMessageBox.warning(
                    self,
                    "Lỗi tải dữ liệu cũ",
                    f"Không thể tải danh sách báo cáo cũ.\n\nChi tiết lỗi:\n{error}"
                )
    
    def add_report_marker_to_map(
        self,
        lat,
        lng,
        address,
        created_at,
        image_count,
        image_path="",
        analysis_html="",
        status="pending",
        report_id=None,
        area_m2=0,
        setup_name="",
        original_image_path="",
        detected_image_path="",
    ):
        source_name = self.extract_source_from_report_address(address, image_path)
        self.cache_report_preview_detail({
            "id": report_id,
            "address": address or "--",
            "latitude": lat,
            "longitude": lng,
            "image_count": image_count or 0,
            "created_at": created_at or "--",
            "status": self.normalize_report_status(status),
            "image_path": image_path or detected_image_path or original_image_path or "",
            "original_image_path": original_image_path or "",
            "detected_image_path": detected_image_path or "",
            "display_image_path": image_path or detected_image_path or original_image_path or "",
            "analysis_html": analysis_html or "",
            "area_m2": float(area_m2 or 0),
            "setup_name": setup_name or "",
        })
        title = "Báo cáo thủ công"
        popup_html = self.build_report_popup_html(
            title=title,
            address=address,
            created_at=created_at,
            image_count=image_count,
            status=status,
            source_name=source_name,
            lat=lat,
            lng=lng,
            image_path=image_path,
        )

        popup_html_json = json.dumps(popup_html, ensure_ascii=False)
        image_path_json = json.dumps(image_path or "", ensure_ascii=False)
        marker_color = self.get_report_marker_color(status)

        js_code = f"""
            (function() {{
                if (typeof L === 'undefined') return;
                const m = (typeof map !== 'undefined') ? map : window.map;
                if (!m) return;

                if (!window.userReportLayer) {{
                    window.userReportLayer = L.layerGroup().addTo(m);
                }}

                if (!window.openUserReportImage) {{
                    window.openUserReportImage = function(path) {{
                        function callBackend() {{
                            if (window.backend && window.backend.showReportImage) {{
                                window.backend.showReportImage(path);
                                return true;
                            }}
                            if (window.showReportImage) {{
                                window.showReportImage(path);
                                return true;
                            }}
                            return false;
                        }}

                        if (callBackend()) return;

                        if (typeof QWebChannel !== 'undefined' && window.qt && window.qt.webChannelTransport) {{
                            new QWebChannel(window.qt.webChannelTransport, function(channel) {{
                                window.backend = channel.objects.backend;
                                callBackend();
                            }});
                        }}
                    }};
                }}

                const marker = L.circleMarker([{float(lat)}, {float(lng)}], {{
                    radius: 9,
                    color: '#ffffff',
                    weight: 2,
                    fillColor: '{marker_color}',
                    fillOpacity: 0.95
                }}).bindPopup({popup_html_json});

                marker.on('popupopen', function(event) {{
                    const btn = event.popup.getElement().querySelector('.view-user-report-image');
                    if (btn) {{
                        const imagePath = {image_path_json};
                        btn.onclick = function() {{ window.openUserReportImage(imagePath); }};
                    }}
                }});

                marker.addTo(window.userReportLayer);
            }})();
        """
        self.web_view.page().runJavaScript(js_code)
        
    def escape_js_text(self, text):
        if text is None:
            return ""
        return str(text).replace("`", "'").replace("\\", "\\\\")


    # =========================
    # ĐIỀU KHIỂN VIDEO DEMO / TOÀN MÀN HÌNH
    # =========================

    def get_video_timer_interval(self):
        """Tính interval theo FPS và tốc độ phát hiện tại."""
        fps = self.fps if self.fps and self.fps > 0 else 25
        speed = self.video_playback_speed if self.video_playback_speed > 0 else 1.0
        return max(5, int(1000 / (fps * speed)))

    def start_video_timer(self):
        if self.cap is None:
            return

        self.video_timer.start(self.get_video_timer_interval())
        self.is_video_paused = False
        self.update_play_pause_button_text()

    def toggle_video_play_pause(self):
        """Nút dừng/phát trong thanh điều khiển video."""
        if self.media_type != "video":
            return

        if self.cap is None:
            self.replay_video()
            return

        if self.video_timer.isActive():
            self.video_timer.stop()
            self.is_video_paused = True
            self.lbl_alert.setText("Trạng thái: Đã tạm dừng video")
        else:
            self.start_video_timer()
            self.lbl_alert.setText("Trạng thái: Đang phát video")

        self.update_play_pause_button_text()

    def replay_video(self):
        """Phát lại video từ đầu, giữ setup camera hiện tại nếu có."""
        if self.media_type != "video":
            return

        if not self.video_path:
            QMessageBox.warning(self, "Chưa có video", "Vui lòng chọn video trước.")
            return

        if self.cap is None:
            self.cap = cv2.VideoCapture(self.video_path)
            if not self.cap.isOpened():
                QMessageBox.critical(self, "Lỗi video", "Không mở được video để phát lại.")
                self.cap = None
                return

            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            if self.fps <= 0:
                self.fps = 25
        else:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        self.frame_index = 0
        self.current_time = 0
        self.is_video_paused = False
        self.analysis_service.reset_depth_cache()
        self.start_video_timer()
        self.lbl_alert.setText("Trạng thái: Đã phát lại video từ đầu")

    def change_video_speed(self, speed_text):
        """Thay đổi tốc độ phát video."""
        try:
            self.video_playback_speed = float(str(speed_text).replace("x", ""))
        except Exception:
            self.video_playback_speed = 1.0

        if self.video_timer.isActive() and self.cap is not None:
            self.video_timer.start(self.get_video_timer_interval())

        if self.fullscreen_speed_combo is not None:
            if self.fullscreen_speed_combo.currentText() != speed_text:
                self.fullscreen_speed_combo.blockSignals(True)
                self.fullscreen_speed_combo.setCurrentText(speed_text)
                self.fullscreen_speed_combo.blockSignals(False)

    def toggle_fullscreen_video(self):
        if self.fullscreen_dialog is None:
            self.open_fullscreen_video()
        else:
            self.close_fullscreen_video()

    def open_fullscreen_video(self):
        """Mở khung video toàn màn hình."""
        if self.fullscreen_dialog is not None:
            self.fullscreen_dialog.raise_()
            self.fullscreen_dialog.activateWindow()
            return

        self.fullscreen_dialog = QDialog(self)
        self.fullscreen_dialog.setWindowTitle("Video demo toàn màn hình")
        self.fullscreen_dialog.setStyleSheet("""
            QDialog {
                background-color: #020617;
            }
            QLabel#fullscreenVideoLabel {
                background-color: #020617;
                color: #e5e7eb;
                font-size: 18px;
                font-weight: 900;
            }
            QFrame#fullscreenControlBar {
                background-color: rgba(15, 23, 42, 235);
                border: none;
            }
            QLabel#fullscreenInfoLabel {
                color: #e5e7eb;
                font-size: 15px;
                font-weight: 800;
                background: transparent;
                padding: 0px 12px;
            }
            QLabel#fullscreenSpeedLabel {
                color: #f8fafc;
                font-size: 14px;
                font-weight: 900;
                background: transparent;
            }
            QPushButton#fullscreenControlButton {
                background-color: #1e293b;
                color: white;
                border: 1px solid #475569;
                border-radius: 18px;
                padding: 9px 13px;
                font-size: 20px;
                font-weight: 900;
                min-width: 48px;
                min-height: 40px;
            }
            QPushButton#fullscreenControlButton:hover {
                background-color: #334155;
            }
            QComboBox#fullscreenSpeedCombo {
                background-color: #1e293b;
                color: #ffffff;
                border: 1px solid #475569;
                border-radius: 9px;
                padding: 8px 12px;
                font-size: 14px;
                font-weight: 900;
                min-width: 100px;
                min-height: 36px;
            }
        """)

        layout = QVBoxLayout(self.fullscreen_dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.fullscreen_video_label = QLabel("Chưa có hình ảnh")
        self.fullscreen_video_label.setObjectName("fullscreenVideoLabel")
        self.fullscreen_video_label.setAlignment(Qt.AlignCenter)
        self.fullscreen_video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.fullscreen_control_bar = QFrame()
        self.fullscreen_control_bar.setObjectName("fullscreenControlBar")
        self.fullscreen_control_bar.setFixedHeight(72)

        control_layout = QHBoxLayout(self.fullscreen_control_bar)
        control_layout.setContentsMargins(16, 10, 16, 10)
        control_layout.setSpacing(12)

        self.fullscreen_btn_play_pause = QPushButton("▶")
        self.fullscreen_btn_play_pause.setObjectName("fullscreenControlButton")
        self.fullscreen_btn_play_pause.setToolTip("Dừng / phát tiếp video")
        self.fullscreen_btn_play_pause.clicked.connect(self.toggle_video_play_pause)

        self.fullscreen_btn_replay = QPushButton("↻")
        self.fullscreen_btn_replay.setObjectName("fullscreenControlButton")
        self.fullscreen_btn_replay.setToolTip("Phát lại từ đầu")
        self.fullscreen_btn_replay.clicked.connect(self.replay_video)

        self.fullscreen_speed_caption = QLabel("Tốc độ phát")
        self.fullscreen_speed_caption.setObjectName("fullscreenSpeedLabel")

        self.fullscreen_speed_combo = QComboBox()
        self.fullscreen_speed_combo.setObjectName("fullscreenSpeedCombo")
        self.fullscreen_speed_combo.addItems(["0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"])
        self.fullscreen_speed_combo.setCurrentText(f"{self.video_playback_speed:.1f}x")
        self.fullscreen_speed_combo.currentTextChanged.connect(self.change_video_speed)

        self.fullscreen_info_label = QLabel(self.build_video_overlay_info())
        self.fullscreen_info_label.setObjectName("fullscreenInfoLabel")
        self.fullscreen_info_label.setWordWrap(True)
        self.fullscreen_info_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.fullscreen_info_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.fullscreen_btn_exit = QPushButton("↙")
        self.fullscreen_btn_exit.setObjectName("fullscreenControlButton")
        self.fullscreen_btn_exit.setToolTip("Thoát toàn màn hình")
        self.fullscreen_btn_exit.clicked.connect(self.close_fullscreen_video)

        control_layout.addWidget(self.fullscreen_btn_play_pause)
        control_layout.addWidget(self.fullscreen_btn_replay)
        control_layout.addWidget(self.fullscreen_speed_caption)
        control_layout.addWidget(self.fullscreen_speed_combo)
        control_layout.addStretch(1)
        control_layout.addWidget(self.fullscreen_info_label, 2)
        control_layout.addWidget(self.fullscreen_btn_exit)

        layout.addWidget(self.fullscreen_video_label, 1)
        layout.addWidget(self.fullscreen_control_bar)

        self.fullscreen_dialog.finished.connect(self.on_fullscreen_closed)

        self.update_video_controls_visibility()
        self.update_play_pause_button_text()
        self.update_fullscreen_frame()
        self.fullscreen_dialog.showFullScreen()

    def close_fullscreen_video(self):
        if self.fullscreen_dialog is not None:
            self.fullscreen_dialog.close()

    def on_fullscreen_closed(self):
        self.fullscreen_dialog = None
        self.fullscreen_video_label = None
        self.fullscreen_info_label = None
        self.fullscreen_control_bar = None
        self.fullscreen_btn_play_pause = None
        self.fullscreen_btn_replay = None
        self.fullscreen_speed_caption = None
        self.fullscreen_speed_combo = None
        self.fullscreen_btn_exit = None
        self.update_video_controls_visibility()

    def update_fullscreen_frame(self):
        if self.fullscreen_video_label is None or self.last_display_frame is None:
            return

        rgb_frame = cv2.cvtColor(self.last_display_frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)

        self.fullscreen_video_label.setPixmap(
            pixmap.scaled(
                self.fullscreen_video_label.width(),
                self.fullscreen_video_label.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def update_play_pause_button_text(self):
        text = "⏸" if self.video_timer.isActive() and self.media_type == "video" else "▶"

        if hasattr(self, "btn_video_play_pause"):
            self.btn_video_play_pause.setText(text)

        if self.fullscreen_btn_play_pause is not None:
            self.fullscreen_btn_play_pause.setText(text)

    def update_video_controls_visibility(self):
        """
        Ảnh: chỉ hiện nút toàn màn hình / thoát toàn màn hình + thông tin vị trí.
        Video: hiện dừng/phát, phát lại, tốc độ, toàn màn hình + thời điểm/tọa độ.
        """
        is_video = self.media_type == "video"

        for name in ["btn_video_play_pause", "btn_video_replay", "lbl_speed_caption", "cmb_video_speed"]:
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setVisible(is_video)

        if hasattr(self, "btn_video_fullscreen"):
            self.btn_video_fullscreen.setText("↙" if self.fullscreen_dialog is not None else "⛶")
            self.btn_video_fullscreen.setToolTip(
                "Thoát toàn màn hình" if self.fullscreen_dialog is not None else "Toàn màn hình"
            )

        fullscreen_video_controls = [
            self.fullscreen_btn_play_pause,
            self.fullscreen_btn_replay,
            self.fullscreen_speed_caption,
            self.fullscreen_speed_combo,
        ]

        for widget in fullscreen_video_controls:
            if widget is not None:
                widget.setVisible(is_video)

        if self.fullscreen_btn_exit is not None:
            self.fullscreen_btn_exit.setText("↙")

    def build_video_overlay_info(self, time_text=None):
        road_name = self.current_road_name or "Chưa xác định"

        if self.current_lat is not None and self.current_lng is not None:
            gps_text = f"GPS: {self.current_lat:.6f}, {self.current_lng:.6f}"
        else:
            gps_text = "GPS: Chưa có"

        if self.media_type == "image":
            return f"{road_name} | {gps_text}"

        if time_text is None:
            time_text = format_video_time(self.current_time or 0)

        return f"Thời điểm video: {time_text} | {road_name}"

    def set_video_overlay_info(self, text):
        if hasattr(self, "lbl_video_overlay_info"):
            self.lbl_video_overlay_info.setText(text)

        if self.fullscreen_info_label is not None:
            self.fullscreen_info_label.setText(text)

    def closeEvent(self, event):
        self.stop_video_demo(show_message=False)
        if self.fullscreen_dialog is not None:
            self.fullscreen_dialog.close()
        super().closeEvent(event)

    def show_report_detail_on_left_panel(self, report):
        """Hiển thị ảnh sau phát hiện và toàn bộ thông tin phân tích DB ở khung bên trái."""
        if not report:
            return

        detail = None
        report_id = report.get("id")
        image_path = report.get("image_path") or report.get("detected_image_path") or report.get("original_image_path") or ""

        if report_id is not None:
            detail = self.get_report_detail_from_database(report_id=report_id)
        if detail is None and image_path:
            detail = self.get_report_detail_from_database(image_path=image_path)

        if detail is None:
            detail = dict(report)
            detail.setdefault("display_image_path", image_path)

        display_image_path = (
            detail.get("display_image_path")
            or detail.get("detected_image_path")
            or detail.get("image_path")
            or detail.get("original_image_path")
            or image_path
        )

        if display_image_path and os.path.exists(display_image_path):
            frame = cv2.imread(display_image_path)
            if frame is not None:
                self.show_frame_on_label(frame)
            else:
                self.lbl_alert.setText("Không đọc được ảnh báo cáo đã phát hiện.")
        elif display_image_path:
            self.lbl_alert.setText(f"Không tìm thấy ảnh báo cáo: {display_image_path}")

        analysis_html = detail.get("analysis_html") or report.get("analysis_html") or ""
        area_m2 = detail.get("area_m2", report.get("area_m2", 0))
        setup_name = detail.get("setup_name", report.get("setup_name", ""))

        self.current_analysis_html = analysis_html or ""
        self.lbl_analysis_info.setText(
            self.build_report_analysis_html_from_database(
                analysis_html=analysis_html,
                area_m2=area_m2,
                setup_name=setup_name,
            )
        )

        address = detail.get("address") or report.get("address") or "--"
        road_name = self.clean_report_road_name(address)
        source_name = self.extract_source_from_report_address(address, display_image_path)
        status_text = self.get_report_status_label(detail.get("status") or report.get("status"))

        self.lbl_alert.setText(
            f"Đang xem ảnh báo cáo đã phát hiện: {os.path.basename(display_image_path or source_name)} | "
            f"{road_name} | Trạng thái: {status_text}"
        )

    def build_report_analysis_html_from_database(self, analysis_html="", area_m2=0, setup_name=""):
        """Ghép HTML phân tích đã lưu trong DB với diện tích/setup để hiển thị cho user."""
        safe_setup = html.escape(str(setup_name or "--"))

        try:
            area_value = float(area_m2 or 0)
        except Exception:
            area_value = 0.0

        area_html = f"""
            <div style='margin-top:8px;padding-top:8px;border-top:1px solid #86EFAC;'>
                <b>THÔNG TIN DIỆN TÍCH</b><br>
                <b>Diện tích ước lượng:</b> {area_value:.3f} m²<br>
                <b>Setup camera:</b> {safe_setup}
            </div>
        """

        if analysis_html:
            body_html = str(analysis_html)
            if "THÔNG TIN DIỆN TÍCH" not in body_html:
                body_html += area_html
            return f"""
                <div style='color:#064E3B;font-size:13px;font-weight:600;line-height:1.45;'>
                    {body_html}
                </div>
            """

        return f"""
            <div style='color:#064E3B;font-size:13px;font-weight:600;line-height:1.45;'>
                Chưa có thông tin ánh sáng / nước / độ sâu trong database.
                {area_html}
            </div>
        """

    def get_report_detail_from_database(self, report_id=None, image_path=None):
        """Lấy chi tiết ảnh báo cáo từ DB. Ưu tiên detected_image_path để hiển thị ảnh sau phát hiện."""
        if not os.path.exists(DATABASE_PATH):
            return None

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        try:
            cursor.execute("PRAGMA table_info(pothole_reports)")
            report_columns = [column[1] for column in cursor.fetchall()]

            cursor.execute("PRAGMA table_info(pothole_report_images)")
            image_columns = [column[1] for column in cursor.fetchall()]

            status_expr = "COALESCE(r.status, 'pending')" if "status" in report_columns else "'pending'"
            report_analysis_expr = "COALESCE(r.analysis_html, '')" if "analysis_html" in report_columns else "''"
            image_analysis_expr = "COALESCE(i.analysis_html, '')" if "analysis_html" in image_columns else "''"
            analysis_expr = f"COALESCE(NULLIF({image_analysis_expr}, ''), {report_analysis_expr}, '')"

            original_image_expr = "COALESCE(i.image_path, '')" if "image_path" in image_columns else "''"
            detected_image_expr = "COALESCE(i.detected_image_path, '')" if "detected_image_path" in image_columns else "''"
            display_image_expr = f"COALESCE(NULLIF({detected_image_expr}, ''), NULLIF({original_image_expr}, ''), '')"
            area_expr = "COALESCE(i.area_m2, 0)" if "area_m2" in image_columns else "0"
            setup_expr = "COALESCE(i.setup_name, '')" if "setup_name" in image_columns else "''"

            where_parts = []
            params = []

            if report_id is not None:
                where_parts.append("r.id = ?")
                params.append(report_id)

            if image_path:
                image_match_parts = []
                if "image_path" in image_columns:
                    image_match_parts.append("i.image_path = ?")
                    params.append(image_path)
                if "detected_image_path" in image_columns:
                    image_match_parts.append("i.detected_image_path = ?")
                    params.append(image_path)
                if image_match_parts:
                    where_parts.append("(" + " OR ".join(image_match_parts) + ")")

            if not where_parts:
                return None

            cursor.execute(f"""
                SELECT
                    r.id,
                    r.address,
                    r.latitude,
                    r.longitude,
                    COALESCE(r.image_count, 0) AS image_count,
                    COALESCE(r.created_at, '') AS created_at,
                    {status_expr} AS status,
                    {original_image_expr} AS original_image_path,
                    {detected_image_expr} AS detected_image_path,
                    {display_image_expr} AS display_image_path,
                    {analysis_expr} AS analysis_html,
                    {area_expr} AS area_m2,
                    {setup_expr} AS setup_name
                FROM pothole_reports r
                LEFT JOIN pothole_report_images i
                    ON r.id = i.report_id
                WHERE {" OR ".join(where_parts)}
                ORDER BY i.id ASC
                LIMIT 1
            """, params)

            row = cursor.fetchone()
            if not row:
                return None

            (
                db_report_id,
                address,
                lat,
                lng,
                image_count,
                created_at,
                status,
                original_image_path,
                detected_image_path,
                display_image_path,
                analysis_html,
                area_m2,
                setup_name,
            ) = row

            detail = {
                "id": db_report_id,
                "address": address or "--",
                "latitude": lat,
                "longitude": lng,
                "image_count": image_count or 0,
                "created_at": created_at or "--",
                "status": self.normalize_report_status(status),
                "image_path": display_image_path or original_image_path or detected_image_path or "",
                "original_image_path": original_image_path or "",
                "detected_image_path": detected_image_path or "",
                "display_image_path": display_image_path or detected_image_path or original_image_path or "",
                "analysis_html": analysis_html or "",
                "area_m2": float(area_m2 or 0),
                "setup_name": setup_name or "",
            }
            self.cache_report_preview_detail(detail)
            return detail

        finally:
            conn.close()

    def show_report_image_from_map(self, image_path):
        if not image_path:
            self.lbl_alert.setText("Không có đường dẫn ảnh cho báo cáo này")
            return

        cached_detail = self.get_cached_report_preview_detail(image_path)
        if cached_detail is not None:
            self.show_report_detail_on_left_panel(cached_detail)
            return

        self.show_report_detail_on_left_panel({"image_path": image_path})
        
    def create_report_with_detail(
        self,
        latitude,
        longitude,
        confidence,
        frame_time,
        original_image_path,
        detected_image_path,
        video_path,
        road_name,
        analysis_html,
        area_m2,
        setup_name,
        reporter_user_id=None,
    ):
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        source_name = os.path.basename(video_path)
        is_video = Path(source_name).suffix.lower() in VIDEO_EXTS

        address = f"Tuyến đường: {road_name} Nguồn: {source_name}"
        if is_video:
            address += f" Thời điểm video: {format_video_time(frame_time)}"

        analysis_html = self.build_saved_report_analysis_html(
            analysis_html=analysis_html,
            area_m2=area_m2,
            setup_name=setup_name,
        )

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO pothole_reports (
                address,
                latitude,
                longitude,
                image_count,
                created_at,
                status,
                analysis_html,
                reporter_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            address,
            latitude,
            longitude,
            1,
            created_at,
            "pending",
            analysis_html,
            reporter_user_id,
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
            setup_name
        ))
        if analysis_html:
            cursor.execute("""
                UPDATE pothole_reports
                SET analysis_html = ?
                WHERE id = ?
            """, (analysis_html, report_id))

        conn.commit()
        conn.close()

        self.cache_report_preview_detail({
            "id": report_id,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "image_count": 1,
            "created_at": created_at,
            "status": "pending",
            "image_path": detected_image_path or original_image_path or "",
            "original_image_path": original_image_path or "",
            "detected_image_path": detected_image_path or "",
            "display_image_path": detected_image_path or original_image_path or "",
            "analysis_html": analysis_html or "",
            "area_m2": float(area_m2 or 0),
            "setup_name": setup_name or "",
        })

        return report_id, created_at


    def add_report_image_detail(
        self,
        report_id,
        original_image_path,
        detected_image_path,
        analysis_html,
        area_m2,
        setup_name
    ):
        analysis_html = self.build_saved_report_analysis_html(
            analysis_html=analysis_html,
            area_m2=area_m2,
            setup_name=setup_name,
        )

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

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
            setup_name
        ))

        if analysis_html:
            cursor.execute("""
                UPDATE pothole_reports
                SET analysis_html = ?
                WHERE id = ?
            """, (analysis_html, report_id))

        conn.commit()
        conn.close()