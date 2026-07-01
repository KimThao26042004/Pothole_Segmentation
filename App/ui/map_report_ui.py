import os

from PyQt5.QtCore import QUrl, QSize, Qt, QObject, pyqtSlot
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QMessageBox,
    QListWidget,
    QFrame,
    QStyle,
    QGroupBox,
    QSizePolicy,
    QSpacerItem,
    QComboBox,
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel


class RoutePickBridge(QObject):
    """Bridge riêng để JavaScript trên bản đồ gửi tọa độ user click về Python."""

    def __init__(self, window):
        super().__init__()
        self.window = window

    @pyqtSlot(float, float)
    def chooseRoutePoint(self, lat, lng):
        if hasattr(self.window, "on_route_map_point_selected"):
            self.window.on_route_map_point_selected(float(lat), float(lng))


def apply_map_report_style(window):
    window.setStyleSheet("""
        QMainWindow {
            background-color: #eef3f8;
        }

        QWidget {
            font-family: Arial, Helvetica, sans-serif;
            font-size: 14px;
            color: #111827;
        }

        QFrame#leftCard, QFrame#mapCard, QFrame#headerCard, QFrame#searchHeaderCard, QFrame#routeCard {
            background-color: #ffffff;
            border: 1px solid #dbe4ef;
            border-radius: 22px;
        }

        QLabel#titleLabel {
            font-size: 30px;
            font-weight: 900;
            color: #0f172a;
            letter-spacing: -0.5px;
        }

        QLabel#descLabel {
            font-size: 14px;
            color: #475569;
            line-height: 1.45;
        }

        QLabel#searchCaption {
            font-size: 16px;
            font-weight: 900;
            color: #0f172a;
        }

        QLabel#sectionLabel {
            font-size: 16px;
            font-weight: 800;
            color: #0f172a;
            margin-top: 2px;
        }

        QLabel#infoLabel {
            font-size: 13px;
            color: #334155;
            padding: 2px 0px;
        }

        QLabel#gpsBadge {
            background-color: #f8fafc;
            border: 1px solid #dbe4ef;
            border-radius: 14px;
            padding: 10px 12px;
            color: #1e293b;
            font-size: 13px;
            line-height: 1.35;
        }

        QLabel#alertLabel {
            background-color: #ecfdf5;
            border: 1px solid #86efac;
            color: #166534;
            border-radius: 14px;
            padding: 11px 12px;
            font-size: 14px;
            font-weight: 800;
        }

        QLabel#videoLabel {
            background-color: #0f172a;
            color: #e5e7eb;
            border: 1px solid #1e293b;
            border-radius: 18px;
            font-size: 16px;
            font-weight: 800;
        }

        QFrame#videoContainer {
            background-color: #0f172a;
            border: 1px solid #1e293b;
            border-radius: 18px;
        }

        QFrame#videoControlBar {
            background-color: rgba(15, 23, 42, 235);
            border: none;
            border-bottom-left-radius: 18px;
            border-bottom-right-radius: 18px;
        }

        QLabel#videoOverlayInfo {
            background: transparent;
            color: #e5e7eb;
            font-size: 13px;
            font-weight: 700;
            padding: 0px 8px;
        }

        QLabel#speedLabel {
            background: transparent;
            color: #f8fafc;
            font-size: 13px;
            font-weight: 900;
            padding-left: 8px;
        }

        QPushButton#videoControlButton {
            background-color: #1e293b;
            color: white;
            border: 1px solid #334155;
            border-radius: 16px;
            padding: 7px 10px;
            font-size: 18px;
            font-weight: 900;
            min-width: 42px;
            min-height: 34px;
        }
        QPushButton#videoControlButton:hover { background-color: #334155; }
        QPushButton#videoControlButton:pressed { background-color: #0f172a; }

        QComboBox#speedCombo {
            background-color: #1e293b;
            color: #ffffff;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 7px 10px;
            font-size: 13px;
            font-weight: 900;
            min-width: 92px;
            min-height: 32px;
        }
        QComboBox#speedCombo::drop-down {
            border: none;
            width: 22px;
        }

        QGroupBox {
            border: 1px solid #dbe4ef;
            border-radius: 16px;
            margin-top: 12px;
            padding: 13px;
            font-weight: 900;
            color: #0f172a;
            background-color: #ffffff;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            left: 14px;
            padding: 0 7px;
            background-color: #ffffff;
        }

        QLineEdit {
            background-color: #ffffff;
            border: 1px solid #cbd5e1;
            border-radius: 12px;
            padding: 9px 11px;
            font-size: 14px;
            min-height: 26px;
        }

        QLineEdit:focus {
            border: 2px solid #2563eb;
        }

        QPushButton {
            border-radius: 14px;
            padding: 10px 14px;
            font-size: 15px;
            font-weight: 900;
            min-height: 38px;
        }

        QLabel#routeTitleLabel {
            font-size: 15px;
            font-weight: 900;
            color: #0f172a;
        }

        QLabel#routeResultLabel {
            background-color: #f8fafc;
            border: 1px solid #dbe4ef;
            border-radius: 12px;
            padding: 8px 10px;
            color: #334155;
            font-size: 13px;
            font-weight: 700;
        }

        QPushButton#routeButton {
            background-color: #2563eb;
            color: white;
            border: 1px solid #1d4ed8;
        }
        QPushButton#routeButton:hover { background-color: #1d4ed8; }

        QPushButton#clearRouteButton {
            background-color: #ffffff;
            color: #334155;
            border: 1px solid #cbd5e1;
        }
        QPushButton#clearRouteButton:hover { background-color: #f8fafc; }

        QLineEdit#routePointInput {
            min-height: 30px;
            padding-left: 12px;
            padding-right: 12px;
            font-weight: 700;
        }

        QFrame#routePickerPanel {
            background-color: #ffffff;
            border: 1px solid #dbe4ef;
            border-radius: 14px;
        }

        QLabel#routePickerHint {
            color: #64748b;
            font-size: 12px;
            font-weight: 700;
            padding: 8px 10px 0px 10px;
        }

        QListWidget#routePickerList {
            background-color: #ffffff;
            border: none;
            border-radius: 12px;
            padding: 4px;
            font-size: 13px;
            color: #0f172a;
        }
        QListWidget#routePickerList::item {
            padding: 9px 10px;
            border-radius: 10px;
            border-bottom: 1px solid #f1f5f9;
        }
        QListWidget#routePickerList::item:hover {
            background-color: #eff6ff;
        }
        QListWidget#routePickerList::item:selected {
            background-color: #dbeafe;
            color: #0f172a;
        }

        QPushButton#primaryButton {
            background-color: #2563eb;
            color: white;
            border: 1px solid #1d4ed8;
        }
        QPushButton#primaryButton:hover { background-color: #1d4ed8; }

        QPushButton#stopButton {
            background-color: #ffffff;
            color: #991b1b;
            border: 1px solid #fecaca;
        }
        QPushButton#stopButton:hover { background-color: #fef2f2; }

        QPushButton#secondaryButton, QPushButton#chooseImageButton, QPushButton#searchButton {
            background-color: #ffffff;
            border: 1px solid #cbd5e1;
            color: #0f172a;
        }
        QPushButton#secondaryButton:hover, QPushButton#chooseImageButton:hover, QPushButton#searchButton:hover {
            background-color: #f8fafc;
            border: 1px solid #94a3b8;
        }

        QPushButton#saveButton {
            background-color: #16a34a;
            color: white;
            border: 1px solid #15803d;
        }
        QPushButton#saveButton:hover { background-color: #15803d; }

        QListWidget {
            background-color: #ffffff;
            border: 1px solid #cbd5e1;
            border-radius: 12px;
            padding: 6px;
            font-size: 13px;
        }
    """)


def setup_map_report_ui(window, map_html_path, bridge_class):
    main_widget = QWidget()
    root_layout = QVBoxLayout(main_widget)
    root_layout.setContentsMargins(14, 14, 14, 14)
    root_layout.setSpacing(12)

    # =========================
    # TOP HEADER: Title + Search on the map side
    # =========================
    # header_layout = QHBoxLayout()
    # header_layout.setSpacing(14)

    # header_left = QFrame()
    # header_left.setObjectName("headerCard")
    # header_left_layout = QVBoxLayout(header_left)
    # header_left_layout.setContentsMargins(18, 10, 18, 10)
    # header_left_layout.setSpacing(2)

    # title = QLabel("Báo cáo & định vị ổ gà")
    # title.setObjectName("titleLabel")

    # description = QLabel(
    #     "Video demo được đồng bộ với GPS CSV theo tên video. Khi phát hiện ổ gà, hệ thống đánh dấu đỏ vị trí tương ứng trên tuyến đường."
    # )
    # description.setObjectName("descLabel")
    # description.setWordWrap(True)

    # header_left_layout.addWidget(title)
    # header_left_layout.addWidget(description)

    header_right = QFrame()
    header_right.setObjectName("searchHeaderCard")
    header_right_layout = QHBoxLayout(header_right)
    header_right_layout.setContentsMargins(18, 10, 18, 10)
    header_right_layout.setSpacing(10)

    search_caption = QLabel("Tìm tuyến đường")
    search_caption.setObjectName("searchCaption")
    search_caption.setFixedWidth(170)

    window.txt_search = QLineEdit()
    window.txt_search.setPlaceholderText("Nhập tên đường hoặc địa chỉ")

    window.btn_search = QPushButton()
    window.btn_search.setObjectName("searchButton")
    window.btn_search.setToolTip("Tìm kiếm địa chỉ")
    window.btn_search.setIcon(window.style().standardIcon(QStyle.SP_FileDialogContentsView))
    window.btn_search.setIconSize(QSize(20, 20))
    window.btn_search.clicked.connect(window.search_location_by_button)
    window.btn_search.setFixedWidth(52)

    header_right_layout.addWidget(search_caption)
    header_right_layout.addWidget(window.txt_search, 1)
    header_right_layout.addWidget(window.btn_search)

    # =========================
    # ROUTE SEARCH: điểm đầu / điểm cuối + lọc ổ gà gần tuyến
    # =========================
    route_card = QFrame()
    route_card.setObjectName("routeCard")
    route_card_layout = QVBoxLayout(route_card)
    route_card_layout.setContentsMargins(16, 12, 16, 12)
    route_card_layout.setSpacing(8)

    route_title = QLabel("Tra cứu ổ gà theo lộ trình")
    route_title.setObjectName("routeTitleLabel")
    route_card_layout.addWidget(route_title)

    route_input_row = QHBoxLayout()
    route_input_row.setSpacing(8)

    window.txt_route_start = QLineEdit()
    window.txt_route_start.setObjectName("routePointInput")
    window.txt_route_start.setPlaceholderText("Chọn điểm bắt đầu hoặc nhập địa chỉ")

    window.txt_route_end = QLineEdit()
    window.txt_route_end.setObjectName("routePointInput")
    window.txt_route_end.setPlaceholderText("Chọn điểm đến")

    route_input_row.addWidget(window.txt_route_start, 1)
    route_input_row.addWidget(window.txt_route_end, 1)
    route_card_layout.addLayout(route_input_row)

    window.route_picker_panel = QFrame()
    window.route_picker_panel.setObjectName("routePickerPanel")
    window.route_picker_panel.setVisible(False)

    route_picker_layout = QVBoxLayout(window.route_picker_panel)
    route_picker_layout.setContentsMargins(8, 6, 8, 8)
    route_picker_layout.setSpacing(4)

    window.lbl_route_picker_hint = QLabel(
        "Chọn Vị trí hiện tại, địa điểm đã tra gần đây hoặc bấm trực tiếp lên bản đồ để lấy điểm."
    )
    window.lbl_route_picker_hint.setObjectName("routePickerHint")
    window.lbl_route_picker_hint.setWordWrap(True)

    window.route_picker_list = QListWidget()
    window.route_picker_list.setObjectName("routePickerList")
    window.route_picker_list.setMaximumHeight(150)
    window.route_picker_list.itemClicked.connect(window.on_route_picker_item_clicked)

    route_picker_layout.addWidget(window.lbl_route_picker_hint)
    route_picker_layout.addWidget(window.route_picker_list)
    route_card_layout.addWidget(window.route_picker_panel)

    route_button_row = QHBoxLayout()
    route_button_row.setSpacing(8)

    window.btn_find_route_potholes = QPushButton("Tìm đường & lọc ổ gà")
    window.btn_find_route_potholes.setObjectName("routeButton")
    window.btn_find_route_potholes.clicked.connect(window.find_shortest_route_and_filter_potholes)

    window.btn_clear_route_potholes = QPushButton("Xóa tuyến")
    window.btn_clear_route_potholes.setObjectName("clearRouteButton")
    window.btn_clear_route_potholes.clicked.connect(window.clear_route_search)

    route_button_row.addWidget(window.btn_find_route_potholes, 1)
    route_button_row.addWidget(window.btn_clear_route_potholes, 0)
    route_card_layout.addLayout(route_button_row)

    window.lbl_route_result = QLabel("Nhập điểm đầu và điểm cuối để tìm tuyến ngắn nhất, sau đó hệ thống sẽ lọc các ổ gà nằm gần tuyến.")
    window.lbl_route_result.setObjectName("routeResultLabel")
    window.lbl_route_result.setWordWrap(True)
    route_card_layout.addWidget(window.lbl_route_result)

    window.route_result_list = QListWidget()
    window.route_result_list.setMaximumHeight(128)
    window.route_result_list.setVisible(False)
    window.route_result_list.itemClicked.connect(window.on_route_result_item_clicked)
    route_card_layout.addWidget(window.route_result_list)

    # header_layout.addStretch(1)
    # header_layout.addWidget(header_right, 1)
    # =========================
    # BODY: 50/50 layout
    # =========================
    body_layout = QHBoxLayout()
    body_layout.setSpacing(14)

    # =========================
    # LEFT HALF: Video + Controls + Manual report
    # =========================
    left_card = QFrame()
    left_card.setObjectName("leftCard")
    left_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    left_layout = QVBoxLayout(left_card)
    left_layout.setContentsMargins(18, 18, 18, 18)
    left_layout.setSpacing(10)

    # Demo group
    demo_group = QGroupBox("Hệ thống phát hiện ổ gà")
    demo_layout = QVBoxLayout(demo_group)
    demo_layout.setContentsMargins(14, 18, 14, 14)
    demo_layout.setSpacing(10)

    # =========================
    # Hàng nút điều khiển nằm trên video
    # =========================
    button_row = QHBoxLayout()
    button_row.setSpacing(10)

    window.btn_choose_video = QPushButton("Chọn ảnh/video")
    window.btn_choose_video.setObjectName("secondaryButton")
    window.btn_choose_video.clicked.connect(window.choose_demo_video)

    window.btn_get_current_location = QPushButton("Lấy vị trí hiện tại")
    window.btn_get_current_location.setObjectName("secondaryButton")
    window.btn_get_current_location.setEnabled(False)
    window.btn_get_current_location.clicked.connect(window.get_current_location)

    window.btn_start_demo = QPushButton("Chạy")
    window.btn_start_demo.setObjectName("primaryButton")
    window.btn_start_demo.clicked.connect(window.start_video_demo)

    window.btn_save_report = QPushButton("Báo cáo")
    window.btn_save_report.setObjectName("saveButton")
    window.btn_save_report.setEnabled(False)

    if hasattr(window, "save_report"):
        window.btn_save_report.clicked.connect(window.save_report)
    elif hasattr(window, "send_report_to_admin"):
        window.btn_save_report.clicked.connect(window.send_report_to_admin)
    else:
        window.btn_save_report.clicked.connect(
            lambda: QMessageBox.information(
                window,
                "Báo cáo",
                "Bạn cần gắn hàm xử lý gửi báo cáo cho admin."
            )
        )

    for btn in (
        window.btn_choose_video,
        window.btn_get_current_location,
        window.btn_start_demo,
        window.btn_save_report,
    ):
        btn.setMinimumHeight(48)
        btn.setMinimumWidth(130)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button_row.addWidget(btn, 1)

    demo_layout.addLayout(button_row)

    # =========================
    # Khung video + thanh điều khiển nằm dưới hàng nút
    # =========================
    window.video_container = QFrame()
    window.video_container.setObjectName("videoContainer")
    window.video_container.setMinimumHeight(340)
    window.video_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    video_container_layout = QVBoxLayout(window.video_container)
    video_container_layout.setContentsMargins(0, 0, 0, 0)
    video_container_layout.setSpacing(0)

    window.video_label = QLabel("Chưa chọn video")
    window.video_label.setObjectName("videoLabel")
    window.video_label.setAlignment(Qt.AlignCenter)
    window.video_label.setMinimumHeight(280)
    window.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    window.video_control_bar = QFrame()
    window.video_control_bar.setObjectName("videoControlBar")
    window.video_control_bar.setFixedHeight(64)

    video_control_layout = QHBoxLayout(window.video_control_bar)
    video_control_layout.setContentsMargins(14, 9, 14, 9)
    video_control_layout.setSpacing(10)

    window.btn_video_play_pause = QPushButton("▶")
    window.btn_video_play_pause.setObjectName("videoControlButton")
    window.btn_video_play_pause.setToolTip("Dừng / phát tiếp video")
    window.btn_video_play_pause.clicked.connect(window.toggle_video_play_pause)

    window.btn_video_replay = QPushButton("↻")
    window.btn_video_replay.setObjectName("videoControlButton")
    window.btn_video_replay.setToolTip("Phát lại từ đầu")
    window.btn_video_replay.clicked.connect(window.replay_video)

    window.lbl_speed_caption = QLabel("Tốc độ phát")
    window.lbl_speed_caption.setObjectName("speedLabel")

    window.cmb_video_speed = QComboBox()
    window.cmb_video_speed.setObjectName("speedCombo")
    window.cmb_video_speed.addItems(["0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"])
    window.cmb_video_speed.setCurrentText("1.0x")
    window.cmb_video_speed.currentTextChanged.connect(window.change_video_speed)

    window.lbl_video_overlay_info = QLabel("Chưa có thông tin vị trí")
    window.lbl_video_overlay_info.setObjectName("videoOverlayInfo")
    window.lbl_video_overlay_info.setWordWrap(True)
    window.lbl_video_overlay_info.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    window.lbl_video_overlay_info.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    window.btn_video_fullscreen = QPushButton("⛶")
    window.btn_video_fullscreen.setObjectName("videoControlButton")
    window.btn_video_fullscreen.setToolTip("Toàn màn hình")
    window.btn_video_fullscreen.clicked.connect(window.toggle_fullscreen_video)

    video_control_layout.addWidget(window.btn_video_play_pause)
    video_control_layout.addWidget(window.btn_video_replay)
    video_control_layout.addWidget(window.lbl_speed_caption)
    video_control_layout.addWidget(window.cmb_video_speed)
    video_control_layout.addStretch(1)
    video_control_layout.addWidget(window.lbl_video_overlay_info, 2)
    video_control_layout.addWidget(window.btn_video_fullscreen)

    video_container_layout.addWidget(window.video_label, 1)
    video_container_layout.addWidget(window.video_control_bar)

    window.lbl_demo_status = QLabel("")
    window.lbl_demo_status.hide()

    # Giữ label GPS cũ để tương thích code cũ, nhưng thông tin hiện nay được đưa lên thanh điều khiển video.
    window.lbl_current_gps = QLabel("Thời điểm video: --\nVị trí xe: --")
    window.lbl_current_gps.setObjectName("gpsBadge")
    window.lbl_current_gps.setWordWrap(True)
    window.lbl_current_gps.hide()

    window.lbl_analysis_info = QLabel("Thông tin phân tích: Chưa có dữ liệu")
    window.lbl_analysis_info.setWordWrap(True)
    window.lbl_analysis_info.setMinimumHeight(180)
    window.lbl_analysis_info.setStyleSheet("""
        QLabel {
            background-color: #F0FDF4;
            border: 1px solid #86EFAC;
            border-radius: 10px;
            padding: 10px;
            color: #064E3B;
            font-size: 12px;
            font-weight: 600;
        }
    """)

    window.lbl_alert = QLabel("Trạng thái: Chưa chạy demo")
    window.lbl_alert.setObjectName("alertLabel")
    window.lbl_alert.setWordWrap(True)

    demo_layout.addWidget(window.video_container, 1)
    demo_layout.addWidget(window.lbl_analysis_info)
    demo_layout.addWidget(window.lbl_alert)

    # =========================
    # Hidden widgets for old code compatibility
    # Không hiển thị phần báo cáo thủ công nữa
    # =========================

    window.lbl_selected_location = QLabel("")
    window.lbl_selected_location.hide()

    window.btn_choose_images = QPushButton("")
    window.btn_choose_images.hide()

    window.lbl_selected_images = QLabel("")
    window.lbl_selected_images.hide()

    window.selected_image_list = QListWidget()
    window.selected_image_list.hide()

    # window.btn_save_report = QPushButton("")
    # window.btn_save_report.hide()

    window.report_list = QListWidget()
    window.report_list.hide()

    # Chỉ hiển thị phần demo video, bỏ manual_group
    left_layout.addWidget(demo_group, 1)


    # =========================
    # RIGHT HALF: Map
    # =========================
    map_card = QFrame()
    map_card.setObjectName("mapCard")
    map_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    map_layout = QVBoxLayout(map_card)
    map_layout.setContentsMargins(8, 8, 8, 8)
    map_layout.setSpacing(0)

    window.web_view = QWebEngineView()
    window.web_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    window.channel = QWebChannel()
    window.bridge = bridge_class(window)
    window.channel.registerObject("backend", window.bridge)
    window.route_pick_bridge = RoutePickBridge(window)
    window.channel.registerObject("routeBackend", window.route_pick_bridge)
    window.web_view.page().setWebChannel(window.channel)
    window.web_view.loadFinished.connect(window.on_map_loaded)

    if not os.path.exists(map_html_path):
        QMessageBox.critical(
            window,
            "Thiếu file map.html",
            f"Không tìm thấy file bản đồ:\n{map_html_path}"
        )
    else:
        window.web_view.load(QUrl.fromLocalFile(map_html_path))

    map_layout.addWidget(window.web_view)

    # body_layout.addWidget(left_card, 1)
    # body_layout.addWidget(map_card, 1)

    # root_layout.addLayout(header_layout)
    # root_layout.addLayout(body_layout, 1)

    # window.setCentralWidget(main_widget)
    
    right_container = QWidget()
    right_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    right_layout = QVBoxLayout(right_container)
    right_layout.setContentsMargins(0, 0, 0, 0)
    right_layout.setSpacing(12)

    right_layout.addWidget(header_right)
    right_layout.addWidget(route_card)
    right_layout.addWidget(map_card, 1)

    body_layout.addWidget(left_card, 1)
    body_layout.addWidget(right_container, 1)

    root_layout.addLayout(body_layout, 1)

    window.setCentralWidget(main_widget)
