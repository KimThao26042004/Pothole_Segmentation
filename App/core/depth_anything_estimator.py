import cv2
import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForDepthEstimation


class DepthAnythingEstimator:
    def __init__(self, model_name="depth-anything/Depth-Anything-V2-Small-hf"):
        self.model_name = model_name
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.processor = None
        self.model = None

    def load_model_if_needed(self):
        if self.processor is not None and self.model is not None:
            return

        self.processor = AutoImageProcessor.from_pretrained(self.model_name)
        self.model = AutoModelForDepthEstimation.from_pretrained(self.model_name)
        self.model.to(self.device)
        self.model.eval()

    def predict_depth_map(self, frame_bgr):
        """
        Trả về depth_map dạng float32, kích thước bằng ảnh gốc.
        Đây là relative depth map, không phải mét/cm thật.
        """
        self.load_model_if_needed()

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame_rgb)

        inputs = self.processor(images=image, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)
            predicted_depth = outputs.predicted_depth

        prediction = torch.nn.functional.interpolate(
            predicted_depth.unsqueeze(1),
            size=(frame_bgr.shape[0], frame_bgr.shape[1]),
            mode="bicubic",
            align_corners=False,
        )

        depth_map = prediction.squeeze().detach().cpu().numpy().astype(np.float32)
        return depth_map

    def normalize_depth(self, depth_map):
        d_min = float(np.min(depth_map))
        d_max = float(np.max(depth_map))

        if d_max - d_min < 1e-6:
            return np.zeros_like(depth_map, dtype=np.float32)

        return (depth_map - d_min) / (d_max - d_min)

    def estimate_water_pothole_depth(self, frame_bgr, pothole_mask, road_ring_mask):
        """
        Tính độ sâu tương đối cho ổ gà có nước bằng Depth Anything V2
        kết hợp thêm điểm viền tối và điểm tương phản.
        """

        if pothole_mask is None or np.count_nonzero(pothole_mask) == 0:
            return {
                "depth_status": "invalid_mask",
                "depth_level": "Không xác định",
                "depth_score": 0.0,
                "pothole_depth_mean": 0.0,
                "road_depth_mean": 0.0,
                "depth_method": "Depth Anything V2 Small",
                "depth_score_da": 0.0,
                "dark_rim_ratio": 0.0,
                "rim_score": 0.0,
                "contrast_score": 0.0,
                "pothole_brightness": 0.0,
                "road_brightness": 0.0,
            }

        if road_ring_mask is None or np.count_nonzero(road_ring_mask) == 0:
            return {
                "depth_status": "invalid_road_ring_mask",
                "depth_level": "Không xác định",
                "depth_score": 0.0,
                "pothole_depth_mean": 0.0,
                "road_depth_mean": 0.0,
                "depth_method": "Depth Anything V2 Small",
                "depth_score_da": 0.0,
                "dark_rim_ratio": 0.0,
                "rim_score": 0.0,
                "contrast_score": 0.0,
                "pothole_brightness": 0.0,
                "road_brightness": 0.0,
            }

        # =========================
        # 1. Depth Anything V2
        # =========================
        depth_map = self.predict_depth_map(frame_bgr)
        depth_norm = self.normalize_depth(depth_map)

        pothole_depth_pixels = depth_norm[pothole_mask > 0]
        road_depth_pixels = depth_norm[road_ring_mask > 0]

        if len(pothole_depth_pixels) == 0 or len(road_depth_pixels) == 0:
            return {
                "depth_status": "invalid_depth_region",
                "depth_level": "Không xác định",
                "depth_score": 0.0,
                "pothole_depth_mean": 0.0,
                "road_depth_mean": 0.0,
                "depth_method": "Depth Anything V2 Small",
                "depth_score_da": 0.0,
                "dark_rim_ratio": 0.0,
                "rim_score": 0.0,
                "contrast_score": 0.0,
                "pothole_brightness": 0.0,
                "road_brightness": 0.0,
            }

        pothole_depth_mean = float(np.mean(pothole_depth_pixels))
        road_depth_mean = float(np.mean(road_depth_pixels))

        depth_diff = abs(pothole_depth_mean - road_depth_mean)
        depth_score_da = depth_diff * 100.0

        # =========================
        # 2. Điểm viền tối quanh ổ gà
        # =========================
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        kernel = np.ones((15, 15), np.uint8)
        dilated = cv2.dilate(pothole_mask, kernel, iterations=1)
        rim_mask = cv2.subtract(dilated, pothole_mask)

        rim_pixels = gray[rim_mask > 0]

        if len(rim_pixels) > 0:
            dark_rim_ratio = np.count_nonzero(rim_pixels < 90) / len(rim_pixels)
        else:
            dark_rim_ratio = 0.0

        rim_score = dark_rim_ratio * 30.0

        # =========================
        # 3. Điểm tương phản ổ gà - mặt đường
        # =========================
        pothole_gray_pixels = gray[pothole_mask > 0]
        road_gray_pixels = gray[road_ring_mask > 0]

        if len(pothole_gray_pixels) > 0 and len(road_gray_pixels) > 0:
            pothole_brightness = float(np.mean(pothole_gray_pixels))
            road_brightness = float(np.mean(road_gray_pixels))
            contrast_score = abs(road_brightness - pothole_brightness) / 10.0
        else:
            pothole_brightness = 0.0
            road_brightness = 0.0
            contrast_score = 0.0

        # =========================
        # 4. Final depth score
        # =========================
        final_depth_score = depth_score_da + rim_score + contrast_score

        if final_depth_score < 6:
            level = "Nông"
        elif final_depth_score < 18:
            level = "Trung bình"
        else:
            level = "Sâu"

        return {
            "depth_status": "estimated_by_depth_anything_v2",
            "depth_level": level,
            "depth_score": float(final_depth_score),

            "pothole_depth_mean": float(pothole_depth_mean),
            "road_depth_mean": float(road_depth_mean),
            "depth_method": "Depth Anything V2 Small",

            "depth_score_da": float(depth_score_da),
            "dark_rim_ratio": float(dark_rim_ratio),
            "rim_score": float(rim_score),
            "contrast_score": float(contrast_score),

            "pothole_brightness": float(pothole_brightness),
            "road_brightness": float(road_brightness),
        }