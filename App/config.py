import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model", "PotHoleYolo12.pt")
LOGO_PATH = os.path.join(BASE_DIR, "img", "logo.jpg")

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".wmv")
VALID_OUTPUT_EXTS = IMAGE_EXTS + VIDEO_EXTS
