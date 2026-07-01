import os
import shutil
from datetime import datetime
from pathlib import Path

import cv2

from app_settings import DETECTED_FRAME_DIR, REPORTED_IMAGE_DIR


class MediaService:
    """Lưu frame detect và copy ảnh báo cáo thủ công."""

    def save_detected_frame(self, frame, video_path, frame_count):
        os.makedirs(DETECTED_FRAME_DIR, exist_ok=True)
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_stem = Path(video_path).stem if video_path else "video"
        filename = f"{video_stem}_pothole_{now}_{frame_count}.jpg"
        image_path = os.path.join(DETECTED_FRAME_DIR, filename)
        cv2.imwrite(image_path, frame)
        return image_path

    def copy_manual_report_images(self, report_id, image_paths):
        os.makedirs(REPORTED_IMAGE_DIR, exist_ok=True)
        file_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        copied_paths = []

        for index, image_path in enumerate(image_paths, start=1):
            original_file_name = os.path.basename(image_path)
            _, ext = os.path.splitext(original_file_name)
            new_image_name = f"report_{report_id}_pothole_{file_time}_{index}{ext}"
            new_image_path = os.path.join(REPORTED_IMAGE_DIR, new_image_name)
            shutil.copy2(image_path, new_image_path)
            copied_paths.append(new_image_path)

        return copied_paths
