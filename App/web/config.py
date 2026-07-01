"""
Cấu hình riêng cho web Gradio.

Sau khi refactor, các file web nằm trong package `web/`.
File này tập trung toàn bộ cấu hình đường dẫn, setup camera và thông số xử lý video
để các file khác không phải khai báo lặp lại.
"""

from pathlib import Path


# ============================================================
# 1. ĐƯỜNG DẪN
# ============================================================

# App/
APP_DIR = Path(__file__).resolve().parent.parent

# App/web/
WEB_DIR = Path(__file__).resolve().parent

# Thư mục mới sau refactor.
WEB_OUTPUT_DIR = WEB_DIR / "outputs"
WEB_IMAGE_OUTPUT_DIR = WEB_OUTPUT_DIR / "images"
WEB_VIDEO_OUTPUT_DIR = WEB_OUTPUT_DIR / "videos"
WEB_TEMP_DIR = WEB_OUTPUT_DIR / "temp"
WEB_GPS_DIR = WEB_DIR / "gps_csv"

# Thư mục cũ để không mất chức năng tìm GPS/output nếu project của bạn đang dùng.
# Có thể xóa sau khi bạn đã chuyển dữ liệu sang web/gps_csv và web/outputs.
LEGACY_WEB_GPS_DIR = APP_DIR / "web_gps_csv"
LEGACY_WEB_OUTPUT_DIR = APP_DIR / "web_outputs"


RUNTIME_DIRS = [
    WEB_OUTPUT_DIR,
    WEB_IMAGE_OUTPUT_DIR,
    WEB_VIDEO_OUTPUT_DIR,
    WEB_TEMP_DIR,
    WEB_GPS_DIR,
]

for folder in RUNTIME_DIRS:
    folder.mkdir(parents=True, exist_ok=True)


# ============================================================
# 2. SETUP CAMERA / HOMOGRAPHY
# ============================================================

CAMERA_SETUPS = {
    "Setup 1 - No Zoom": "setup1_nozoom",
    "Setup 1 - Zoom": "setup1_zoom",
    "Setup 2 - No Zoom": "setup2_nozoom",
    "Setup 2 - Zoom": "setup2_zoom",
    "Setup 3 - No Zoom": "setup3_nozoom",
}

DEFAULT_SETUP_DISPLAY_NAME = "Setup 2 - No Zoom"


# ============================================================
# 3. CẤU HÌNH VIDEO / REALTIME
# ============================================================

VIDEO_FRAME_STEP = 5
MAX_VIDEO_SECONDS = 30

WEBRTC_ANALYZE_EVERY = 3
WEBRTC_MAX_WIDTH = 640


# ============================================================
# 4. CẤU HÌNH MAP / GPS
# ============================================================

DEFAULT_MAP_CENTER = [10.762622, 106.660172]
SAME_POTHOLE_RADIUS_M = 2.0

# Khi tìm GPS sidecar, hệ thống sẽ tìm ở cả thư mục mới và thư mục cũ.
GPS_SEARCH_DIRS = [
    WEB_GPS_DIR,
    LEGACY_WEB_GPS_DIR,
    APP_DIR,
]
