import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MAP_HTML_PATH = os.path.join(BASE_DIR, "map_assets", "map.html")
DATABASE_DIR = os.path.join(BASE_DIR, "database")
DATABASE_PATH = os.path.join(DATABASE_DIR, "potholes.db")
REPORTED_IMAGE_DIR = os.path.join(BASE_DIR, "reported_images")
DETECTED_FRAME_DIR = os.path.join(BASE_DIR, "detected_frames")
MODEL_PATH = os.path.join(BASE_DIR, "model", "PotHoleYolo12.pt")
HOMOGRAPHY_DIR = os.path.join(BASE_DIR, "homography")
SAMPLE_VIDEO_DIR = os.path.join(BASE_DIR, "samples_videos")

MEDIA_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".mp4", ".avi", ".mov", ".mkv", ".wmv")
VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".wmv")
