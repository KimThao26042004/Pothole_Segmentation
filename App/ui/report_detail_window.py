import os
import cv2
import sqlite3
import html

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget, QMessageBox, QTextEdit
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from utils.image_utils import cv2_to_qpixmap

from core.damage_analyzer import (
    evaluate_repair_priority_from_db,
    build_admin_damage_summary_html
)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_PATH = os.path.join(BASE_DIR, "database", "potholes.db")


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
}

REPORT_STATUS_TRANSITIONS = {
    "pending": ["approved", "need_more", "invalid"],
    "need_more": ["approved", "invalid"],
    "approved": ["processing"],
    "processing": ["resolved"],
    "resolved": [],
    "invalid": [],
}



class ReportDetailWindow(QDialog):
    def __init__(self, report_data, parent=None):
        super().__init__(parent)

        self.report_data = report_data
        self.report_id = report_data.get("id")
        self.image_paths = []
        self.first_analysis = None

        self.setWindowTitle(f"Chi tiết báo cáo #{self.report_id}")
        self.resize(1350, 820)

        self.init_ui()
        self.load_report_images()

    def init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #F7F7F7;
                font-family: "Segoe UI";
                color: #111827;
            }

            QLabel {
                background: transparent;
                font-size: 13px;
                color: #111827;
            }

            QFrame#card {
                background: white;
                border: 1px solid #D9D9D9;
                border-radius: 10px;
            }

            QFrame#imageFrame {
                background: #0F172A;
                border: 1px solid #CBD5E1;
                border-radius: 12px;
            }

            QFrame#infoBox {
                background: #F0FDF4;
                border: 1px solid #86EFAC;
                border-radius: 10px;
            }

            QFrame#adminBox {
                background: #EFF6FF;
                border: 1px solid #93C5FD;
                border-radius: 10px;
            }

            QTextEdit {
                background: white;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 8px;
                font-size: 13px;
            }

            QPushButton {
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: 800;
            }

            QPushButton:disabled {
                background-color: #E5E7EB;
                color: #94A3B8;
                border: 1px solid #CBD5E1;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel(f"CHI TIẾT BÁO CÁO #{self.report_id}")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: 900;
                color: #1F2937;
                padding: 8px;
            }
        """)
        root.addWidget(title)

        body = QHBoxLayout()
        body.setSpacing(12)

        # =========================
        # LEFT: ẢNH GỐC + THÔNG TIN CƠ BẢN
        # =========================
        left_card = QFrame()
        left_card.setObjectName("card")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)

        left_title = QLabel("ẢNH GỐC NGƯỜI DÂN GỬI")
        left_title.setStyleSheet("font-size: 16px; font-weight: 900;")
        left_layout.addWidget(left_title)

        self.original_image_label = QLabel("Chưa có ảnh gốc")
        self.original_image_label.setObjectName("imageLabel")
        self.original_image_label.setAlignment(Qt.AlignCenter)
        self.original_image_label.setMinimumHeight(300)
        self.original_image_label.setStyleSheet("""
            QLabel {
                background: #0F172A;
                color: white;
                border: 1px solid #1E293B;
                border-radius: 12px;
                font-size: 14px;
                font-weight: 700;
            }
        """)
        left_layout.addWidget(self.original_image_label, 1)

        self.basic_info_box = QFrame()
        self.basic_info_box.setObjectName("infoBox")
        basic_info_layout = QVBoxLayout(self.basic_info_box)
        basic_info_layout.setContentsMargins(14, 12, 14, 12)
        basic_info_layout.setSpacing(6)

        basic_title = QLabel("THÔNG TIN CƠ BẢN")
        basic_title.setStyleSheet("font-size: 15px; font-weight: 900; color: #064E3B;")
        basic_info_layout.addWidget(basic_title)

        self.basic_info_label = QLabel()
        self.basic_info_label.setWordWrap(True)
        self.basic_info_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                font-weight: 600;
                color: #064E3B;
                line-height: 1.45;
            }
        """)
        basic_info_layout.addWidget(self.basic_info_label)

        left_layout.addWidget(self.basic_info_box)

        self.status_action_box = QFrame()
        self.status_action_box.setStyleSheet("""
            QFrame {
                background: #F8FAFC;
                border: 1px solid #CBD5E1;
                border-radius: 10px;
            }
        """)
        status_action_layout = QVBoxLayout(self.status_action_box)
        status_action_layout.setContentsMargins(12, 10, 12, 12)
        status_action_layout.setSpacing(8)

        status_action_title = QLabel("CẬP NHẬT TRẠNG THÁI BÁO CÁO")
        status_action_title.setStyleSheet("""
            QLabel {
                color: #0F172A;
                font-size: 15px;
                font-weight: 900;
            }
        """)

        self.admin_status_label = QLabel()
        self.admin_status_label.setWordWrap(True)
        self.admin_status_label.setTextFormat(Qt.RichText)
        self.admin_status_label.setStyleSheet("""
            QLabel {
                color: #334155;
                font-size: 13px;
                font-weight: 700;
                padding: 2px 0px;
            }
        """)

        status_action_note = QLabel(
            "Luồng hợp lệ: Chờ duyệt → Đã duyệt → Đang xử lý → Đã xử lý; "
            "Cần bổ sung → Đã duyệt → Đang xử lý → Đã xử lý."
        )
        status_action_note.setWordWrap(True)
        status_action_note.setStyleSheet("""
            QLabel {
                color: #64748B;
                font-size: 11px;
                font-weight: 600;
            }
        """)

        status_button_grid = QGridLayout()
        status_button_grid.setSpacing(8)

        self.btn_status_approved = QPushButton("Đã duyệt")
        self.btn_status_need_more = QPushButton("Cần bổ sung")
        self.btn_status_processing = QPushButton("Đang xử lý")
        self.btn_status_resolved = QPushButton("Đã xử lý")
        self.btn_status_invalid = QPushButton("Không hợp lệ")

        self.status_action_buttons = {
            "approved": self.btn_status_approved,
            "need_more": self.btn_status_need_more,
            "processing": self.btn_status_processing,
            "resolved": self.btn_status_resolved,
            "invalid": self.btn_status_invalid,
        }

        for status_value, button in self.status_action_buttons.items():
            button.clicked.connect(lambda checked=False, value=status_value: self.update_report_status(value))
            button.setMinimumHeight(38)

        status_button_grid.addWidget(self.btn_status_approved, 0, 0)
        status_button_grid.addWidget(self.btn_status_need_more, 0, 1)
        status_button_grid.addWidget(self.btn_status_invalid, 0, 2)
        status_button_grid.addWidget(self.btn_status_processing, 1, 0)
        status_button_grid.addWidget(self.btn_status_resolved, 1, 1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        self.btn_close = QPushButton("Đóng")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #64748B;
                color: white;
                border: 1px solid #475569;
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 900;
            }
            QPushButton:hover { background-color: #475569; }
        """)
        self.btn_close.clicked.connect(self.close)
        close_row.addWidget(self.btn_close)

        status_action_layout.addWidget(status_action_title)
        status_action_layout.addWidget(self.admin_status_label)
        status_action_layout.addWidget(status_action_note)
        status_action_layout.addLayout(status_button_grid)
        status_action_layout.addLayout(close_row)

        left_layout.addWidget(self.status_action_box)
        
        # =========================
        # RIGHT: ẢNH DEMO + PHÂN TÍCH 
        # =========================
        right_card = QFrame()
        right_card.setObjectName("card")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(14, 14, 14, 14)
        right_layout.setSpacing(10)

        right_title = QLabel("ẢNH DEMO PHÁT HIỆN Ổ GÀ")
        right_title.setStyleSheet("font-size: 16px; font-weight: 900;")
        right_layout.addWidget(right_title)

        self.demo_image_label = QLabel("Chưa có ảnh demo")
        self.demo_image_label.setAlignment(Qt.AlignCenter)
        self.demo_image_label.setMinimumHeight(180)
        self.demo_image_label.setStyleSheet("""
            QLabel {
                background: #0F172A;
                color: white;
                border: 1px solid #1E293B;
                border-radius: 12px;
                font-size: 14px;
                font-weight: 700;
            }
        """)
        right_layout.addWidget(self.demo_image_label, 1)

        self.analysis_box = QFrame()
        self.analysis_box.setObjectName("infoBox")
        analysis_layout = QVBoxLayout(self.analysis_box)
        analysis_layout.setContentsMargins(14, 12, 14, 12)
        analysis_layout.setSpacing(6)

        analysis_title = QLabel("THÔNG TIN PHÂN TÍCH")
        analysis_title.setStyleSheet("font-size: 15px; font-weight: 900; color: #064E3B;")
        analysis_layout.addWidget(analysis_title)

        self.analysis_label = QLabel("Chưa có dữ liệu phân tích.")
        self.analysis_label.setWordWrap(True)
        self.analysis_label.setTextFormat(Qt.RichText)
        self.analysis_label.setOpenExternalLinks(False)
        self.analysis_label.setMinimumHeight(230)
        self.analysis_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                font-weight: 600;
                color: #064E3B;
                line-height: 1.45;
            }
        """)
        analysis_layout.addWidget(self.analysis_label)

        right_layout.addWidget(self.analysis_box)

        body.addWidget(left_card, 1)
        body.addWidget(right_card, 1)

        root.addLayout(body, 1)

        self.update_basic_info()
        self.update_admin_status()

    def normalize_report_status(self, status):
        raw = str(status or "pending").strip().lower()
        raw_no_space = raw.replace(" ", "_").replace("-", "_")

        aliases = {
            "": "pending",
            "none": "pending",
            "null": "pending",
            "pending": "pending",
            "waiting": "pending",
            "draft": "pending",
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
            f"border:1px solid {info['border_color']};padding:2px 8px;"
            f"border-radius:999px;font-weight:900'>"
            f"{html.escape(info['label'])}</span>"
        )

    def get_allowed_next_statuses(self, current_status):
        current_status = self.normalize_report_status(current_status)
        return REPORT_STATUS_TRANSITIONS.get(current_status, [])

    def get_status_button_style(self, status_value, enabled=True):
        info = REPORT_STATUS_INFO[status_value]
        if not enabled:
            return """
                QPushButton {
                    background-color: #E5E7EB;
                    color: #94A3B8;
                    border: 1px solid #CBD5E1;
                    border-radius: 8px;
                    padding: 8px 10px;
                    font-size: 12px;
                    font-weight: 800;
                }
            """

        return f"""
            QPushButton {{
                background-color: {info['bg_color']};
                color: {info['text_color']};
                border: 1px solid {info['border_color']};
                border-radius: 8px;
                padding: 8px 10px;
                font-size: 12px;
                font-weight: 900;
            }}
            QPushButton:hover {{
                background-color: #FFFFFF;
                border: 1px solid {info['marker_color']};
            }}
            QPushButton:pressed {{
                background-color: {info['bg_color']};
            }}
        """

    def update_status_action_buttons(self):
        current_status = self.normalize_report_status(self.report_data.get("status"))
        allowed_next_statuses = set(self.get_allowed_next_statuses(current_status))

        for status_value, button in self.status_action_buttons.items():
            enabled = status_value in allowed_next_statuses
            button.setEnabled(enabled)
            button.setStyleSheet(self.get_status_button_style(status_value, enabled=enabled))
            if enabled:
                button.setToolTip(
                    f"Chuyển sang trạng thái: {self.get_report_status_label(status_value)}"
                )
            else:
                button.setToolTip(
                    f"Không thể chuyển trực tiếp từ {self.get_report_status_label(current_status)} "
                    f"sang {self.get_report_status_label(status_value)}"
                )

    def update_basic_info(self):
        status = self.normalize_report_status(self.report_data.get("status"))
        status_badge = self.get_report_status_badge_html(status)

        road_name = self.report_data.get("road_name") or self.report_data.get("address", "--")
        source_name = self.report_data.get("source_name") or self.report_data.get("image_name") or os.path.basename(str(self.report_data.get("image_path") or "")) or "--"
        video_time = self.report_data.get("video_time")

        video_time_line = ""
        if source_name.lower().endswith((".mp4", ".avi", ".mov", ".mkv", ".wmv")) and video_time:
            video_time_line = f"<br><b>Thời điểm video:</b> {video_time}"

        text = (
            f"<b>Mã báo cáo:</b> #{self.report_data.get('id')}<br>"
            f"<b>Trạng thái:</b> {status_badge}<br>"
            f"<b>Tuyến đường:</b> {road_name}<br>"
            f"<b>Nguồn:</b> {source_name}"
            f"{video_time_line}<br>"
            f"<b>Tọa độ:</b> {self.report_data.get('latitude')}, {self.report_data.get('longitude')}<br>"
            f"<b>Số ảnh:</b> {self.report_data.get('image_count', '--')}<br>"
            f"<b>Thời gian gửi:</b> {self.report_data.get('created_at', '--')}"
        )

        self.basic_info_label.setText(text)

    def update_admin_status(self):
        status = self.normalize_report_status(self.report_data.get("status"))
        self.admin_status_label.setText(
            f"Trạng thái hiện tại: {self.get_report_status_badge_html(status)}"
        )
        self.update_status_action_buttons()

    def load_report_images(self):
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()

            # Kiểm tra bảng pothole_report_images đang có những cột nào
            cursor.execute("PRAGMA table_info(pothole_report_images)")
            image_columns = [col[1] for col in cursor.fetchall()]

            # Kiểm tra bảng pothole_reports đang có những cột nào
            cursor.execute("PRAGMA table_info(pothole_reports)")
            report_columns = [col[1] for col in cursor.fetchall()]

            # Bắt buộc phải có image_path
            image_path_expr = "i.image_path"

            # Những cột mới có thể chưa tồn tại ở database cũ
            detected_image_expr = (
                "COALESCE(i.detected_image_path, '')"
                if "detected_image_path" in image_columns
                else "''"
            )

            image_analysis_expr = (
                "i.analysis_html"
                if "analysis_html" in image_columns
                else "''"
            )

            report_analysis_expr = (
                "r.analysis_html"
                if "analysis_html" in report_columns
                else "''"
            )

            area_expr = (
                "COALESCE(i.area_m2, 0)"
                if "area_m2" in image_columns
                else "0"
            )

            setup_expr = (
                "COALESCE(i.setup_name, '')"
                if "setup_name" in image_columns
                else "''"
            )

            cursor.execute(f"""
                SELECT
                    {image_path_expr} AS original_image_path,
                    {detected_image_expr} AS detected_image_path,
                    COALESCE({image_analysis_expr}, {report_analysis_expr}, '') AS analysis_html,
                    {area_expr} AS area_m2,
                    {setup_expr} AS setup_name
                FROM pothole_report_images i
                LEFT JOIN pothole_reports r
                    ON r.id = i.report_id
                WHERE i.report_id = ?
                ORDER BY i.id ASC
            """, (self.report_id,))

            rows = cursor.fetchall()
            conn.close()

            if not rows:
                self.original_image_label.setText("Báo cáo này chưa có ảnh.")
                self.demo_image_label.setText("Không có ảnh demo.")
                self.analysis_label.setText("Chưa có thông tin phân tích.")
                return

            original_image_path = rows[0][0]
            detected_image_path = rows[0][1]
            analysis_html = rows[0][2]
            area_m2 = rows[0][3]
            setup_name = rows[0][4]

            # Tổng số ổ gà / số lần ghi nhận trong báo cáo này
            pothole_count = len(rows)

            # Tổng diện tích lấy từ database, không tính lại ảnh
            total_area_m2 = 0.0
            for row in rows:
                try:
                    total_area_m2 += float(row[3] or 0)
                except Exception:
                    pass

            damage_summary = evaluate_repair_priority_from_db(
                pothole_count=pothole_count,
                area_m2=total_area_m2,
                analysis_html=analysis_html
            )

            damage_summary_html = build_admin_damage_summary_html(damage_summary)

            # =========================
            # 1. Hiển thị ảnh gốc
            # =========================
            if original_image_path and os.path.exists(original_image_path):
                self.show_original_image(original_image_path)
            else:
                self.original_image_label.setText(
                    "Không tìm thấy ảnh gốc.\n"
                    "Có thể báo cáo này được lưu bằng phiên bản cũ."
                )

            # =========================
            # 2. Hiển thị ảnh demo phát hiện ổ gà
            # =========================
            if detected_image_path and os.path.exists(detected_image_path):
                self.show_demo_image(detected_image_path)
            else:
                # Fallback cho báo cáo cũ:
                # Nếu chưa có detected_image_path thì thử chạy lại detection từ ảnh gốc.
                if original_image_path and os.path.exists(original_image_path) and hasattr(self, "show_detection_demo"):
                    self.show_detection_demo(original_image_path)
                else:
                    self.demo_image_label.setText(
                        "Không tìm thấy ảnh demo phát hiện.\n"
                        "Cần gửi lại báo cáo bằng phiên bản mới."
                    )

            # =========================
            # 3. Hiển thị thông tin ánh sáng / nước / độ sâu
            # =========================
            if analysis_html:
                self.show_full_analysis_info(
                    analysis_html=analysis_html + damage_summary_html,
                    area_m2=total_area_m2,
                    setup_name=setup_name
                )
            else:
                self.analysis_label.setText(
                    "Báo cáo này chưa lưu thông tin ánh sáng / nước / độ sâu.\n"
                    "Hãy tạo lại báo cáo từ trang user bằng nút 'Báo cáo'."
                )

        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass

            self.original_image_label.setText("Lỗi tải ảnh gốc.")
            self.demo_image_label.setText("Lỗi tải ảnh demo.")
            self.analysis_label.setText(f"Lỗi tải thông tin phân tích: {e}")
            
    def show_demo_image(self, image_path):
        img = cv2.imread(image_path)

        if img is None:
            self.demo_image_label.setText("Không thể đọc ảnh demo.")
            return

        pix = cv2_to_qpixmap(img).scaled(
            620,
            380,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.demo_image_label.setPixmap(pix)
        self.demo_image_label.setText("")
        
    def show_original_image(self, image_path):
        img = cv2.imread(image_path)

        if img is None:
            self.original_image_label.setText("Không thể đọc ảnh gốc.")
            return

        pix = cv2_to_qpixmap(img).scaled(
            620, 380,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.original_image_label.setPixmap(pix)
        self.original_image_label.setText("")

    def show_detection_demo(self, image_path):
        img = cv2.imread(image_path)

        if img is None:
            self.demo_image_label.setText("Không thể đọc ảnh để phân tích.")
            return

        try:
            results = predict_image(image_path, conf=0.25, verbose=False)

            if not results:
                self.demo_image_label.setText("Không có kết quả phát hiện.")
                self.analysis_label.setText("Không có dữ liệu phân tích.")
                return

            result = results[0]
            plotted_img = result.plot()

            demo_pix = cv2_to_qpixmap(plotted_img).scaled(
                620, 380,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            self.demo_image_label.setPixmap(demo_pix)
            self.demo_image_label.setText("")

            self.update_analysis_info(result, img)

        except Exception as e:
            self.demo_image_label.setText(f"Lỗi tạo ảnh demo: {e}")
            self.analysis_label.setText(f"Lỗi phân tích: {e}")

    def update_analysis_info(self, result, orig_img):
        pothole_count = 0
        confidences = []

        if result.boxes is not None and len(result.boxes) > 0:
            pothole_count = len(result.boxes)
            for box in result.boxes:
                confidences.append(float(box.conf[0]))

        max_conf = max(confidences) if confidences else 0.0

        damage_percent = calculate_damage_percent(result, orig_img.shape)
        damage_level = classify_damage_level(damage_percent)
        repair_recommendation = get_repair_recommendation(damage_percent)

        if pothole_count > 0:
            status = "Có phát hiện ổ gà"
        else:
            status = "Không phát hiện ổ gà"

        text = (
            f"<b>Trạng thái phát hiện:</b> {status}<br>"
            f"<b>Số ổ gà:</b> {pothole_count}<br>"
            f"<b>Độ tin cậy cao nhất:</b> {max_conf:.2f}<br>"
            f"<b>Mức hư hỏng:</b> {damage_percent:.2f}%<br>"
            f"<b>Cấp độ:</b> {damage_level}<br>"
            f"<b>Khuyến nghị:</b> {repair_recommendation}"
        )

        self.analysis_label.setText(text)

    def update_report_status(self, status):
        current_status = self.normalize_report_status(self.report_data.get("status"))
        new_status = self.normalize_report_status(status)
        allowed_next_statuses = self.get_allowed_next_statuses(current_status)

        if new_status not in allowed_next_statuses:
            QMessageBox.warning(
                self,
                "Không đúng luồng trạng thái",
                f"Không thể chuyển từ '{self.get_report_status_label(current_status)}' "
                f"sang '{self.get_report_status_label(new_status)}'."
            )
            return

        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE pothole_reports
                SET status = ?
                WHERE id = ?
            """, (new_status, self.report_id))

            conn.commit()
            conn.close()

            self.report_data["status"] = new_status

            self.update_basic_info()
            self.update_admin_status()

            parent = self.parent()
            if parent is not None:
                if hasattr(parent, "current_report_id"):
                    parent.current_report_id = self.report_id
                if hasattr(parent, "current_report_status"):
                    parent.current_report_status = new_status
                if hasattr(parent, "selected_report_data") and parent.selected_report_data:
                    parent.selected_report_data["status"] = new_status

                # Nếu trang admin đang lọc theo trạng thái cũ, chuyển về Tất cả để báo cáo không biến mất khỏi danh sách.
                if hasattr(parent, "report_filter") and parent.report_filter not in ("all", new_status):
                    parent.report_filter = "all"
                    if hasattr(parent, "update_report_filter_button_styles"):
                        parent.update_report_filter_button_styles()

                if hasattr(parent, "load_citizen_reports"):
                    parent.load_citizen_reports()
                if hasattr(parent, "select_report_from_map"):
                    parent.select_report_from_map(self.report_id)

            QMessageBox.information(
                self,
                "Cập nhật trạng thái thành công",
                f"Báo cáo #{self.report_id} đã chuyển sang trạng thái: {self.get_report_status_label(new_status)}."
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Lỗi cập nhật trạng thái",
                f"Không thể cập nhật trạng thái báo cáo.\n\nChi tiết: {e}"
            )
            try:
                conn.close()
            except Exception:
                pass
            
    def show_full_analysis_info(self, analysis_html, area_m2=0, setup_name=""):
        if not analysis_html:
            self.analysis_label.setText(
                "Báo cáo này chưa lưu thông tin ánh sáng / nước / độ sâu."
            )
            return

        # extra_html = f"""
        #     <br>
        #     <b>Diện tích:</b> {float(area_m2):.3f} m²<br>
        #     <b>Setup:</b> {setup_name or '--'}
        # """

        self.analysis_label.setText(
            f"""
            <div style="
                color:#064E3B;
                font-size:13px;
                font-weight:600;
            ">
                {analysis_html}
            </div>
            """
        )