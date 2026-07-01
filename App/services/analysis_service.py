import os

from core.area_calculator import PotholeAreaCalculator
from core.pothole_depth_analyzer import PotholeDepthAnalyzer, get_first_yolo_mask
from app_settings import BASE_DIR, MODEL_PATH

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None


class PotholeAnalysisService:
    """Chạy YOLO, tính diện tích và phân tích độ sâu cho 1 frame/ảnh."""

    def __init__(self, model_path=MODEL_PATH, depth_interval=10):
        self.model_path = model_path
        self.model = None
        self.area_calculator = PotholeAreaCalculator(BASE_DIR)
        self.depth_analyzer = PotholeDepthAnalyzer()
        self.depth_interval = depth_interval
        self.last_depth_info = None
        self.last_pothole_mask = None

    def reset_depth_cache(self):
        self.last_depth_info = None
        self.last_pothole_mask = None

    def set_model_path(self, model_path):
        self.model_path = model_path
        self.model = None

    def load_model_if_needed(self):
        if self.model is not None:
            return True

        if YOLO is None:
            raise RuntimeError("Chưa cài ultralytics nên không thể tự detect bằng YOLO.")

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Không tìm thấy model YOLO: {self.model_path}")

        self.model = YOLO(self.model_path)
        return True

    def analyze_frame(self, frame, setup_name, frame_index=0, use_depth_cache=False):
        """
        Return dict:
        - has_pothole
        - annotated_frame
        - confidence
        - area_m2
        - area_pixel
        - depth_info
        - error
        """
        self.load_model_if_needed()

        result = self.model(frame, conf=0.5, verbose=False)[0]
        annotated_frame = result.plot()

        if result.boxes is None or len(result.boxes) == 0:
            return {
                "has_pothole": False,
                "annotated_frame": annotated_frame,
                "confidence": 0.0,
                "area_m2": 0.0,
                "area_pixel": 0,
                "depth_info": None,
                "error": None,
            }

        best_confidence = max(float(box.conf[0]) for box in result.boxes)

        area_m2 = 0.0
        area_pixel = 0
        area_error = None

        try:
            area_m2, area_pixel, _ = self.area_calculator.calculate_total_area_from_yolo_result(
                result=result,
                frame=frame,
                setup_name=setup_name
            )
        except Exception as error:
            area_error = f"Lỗi tính diện tích: {error}"

        depth_info = None
        pothole_mask = get_first_yolo_mask(result, frame.shape)

        if pothole_mask is not None:
            should_run_depth = True

            if use_depth_cache:
                should_run_depth = (
                    frame_index % self.depth_interval == 0
                    or self.last_depth_info is None
                )

            if should_run_depth:
                self.last_depth_info = self.depth_analyzer.analyze(frame, pothole_mask)
                self.last_pothole_mask = pothole_mask

            depth_info = self.last_depth_info

        return {
            "has_pothole": True,
            "annotated_frame": annotated_frame,
            "confidence": best_confidence,
            "area_m2": area_m2,
            "area_pixel": area_pixel,
            "depth_info": depth_info,
            "error": area_error,
        }
