import cv2
import numpy as np
from core.depth_anything_estimator import DepthAnythingEstimator

class PotholeDepthAnalyzer:
    """
    Phân tích:
    1. CLAHE cân bằng độ sáng cục bộ
    2. Phát hiện nước trong mask ổ gà bằng rule-based
    3. Nếu không có nước: ước lượng độ sâu tương đối bằng chênh lệch độ sáng
    """

    def __init__(
        self,
        clahe_clip_limit=2.0,
        clahe_tile_grid_size=(8, 8),
        ring_kernel_size=35,
        bright_threshold=210,
        bright_ratio_threshold=0.12,
        texture_threshold=80,
        saturation_threshold=60,
        shallow_threshold=15,
        medium_threshold=35,
    ):
        self.clahe_clip_limit = clahe_clip_limit
        self.clahe_tile_grid_size = clahe_tile_grid_size
        self.ring_kernel_size = ring_kernel_size

        # Ngưỡng phát hiện nước
        self.bright_threshold = bright_threshold
        self.bright_ratio_threshold = bright_ratio_threshold
        self.texture_threshold = texture_threshold
        self.saturation_threshold = saturation_threshold

        # Ngưỡng phân loại độ sâu tương đối
        self.shallow_threshold = shallow_threshold
        self.medium_threshold = medium_threshold
        self.depth_anything = DepthAnythingEstimator()
        
    def apply_clahe(self, frame_bgr):
        """
        CLAHE trên kênh L trong không gian LAB.
        Giúp tăng tương phản cục bộ nhưng vẫn giữ màu ảnh tương đối tự nhiên.
        """
        lab = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)

        clahe = cv2.createCLAHE(
            clipLimit=self.clahe_clip_limit,
            tileGridSize=self.clahe_tile_grid_size
        )

        l_clahe = clahe.apply(l_channel)
        lab_clahe = cv2.merge((l_clahe, a_channel, b_channel))
        result = cv2.cvtColor(lab_clahe, cv2.COLOR_LAB2BGR)

        return result
    
    def translate_depth_level(self, level):
        level_map = {
            "Shallow": "Nông",
            "Medium": "Trung bình",
            "Deep": "Sâu",
            "Unknown": "Không xác định",
            "Không xác định": "Không xác định",
            "Nông": "Nông",
            "Trung bình": "Trung bình",
            "Sâu": "Sâu",
        }

        return level_map.get(level, level)
    
    def ensure_binary_mask(self, mask, frame_shape):
        """
        Chuẩn hóa mask về dạng uint8, kích thước bằng frame.
        mask > 0 là vùng ổ gà.
        """
        if mask is None:
            return None

        mask = np.asarray(mask)

        if mask.ndim == 3:
            mask = mask[:, :, 0]

        if mask.shape[:2] != frame_shape[:2]:
            mask = cv2.resize(
                mask.astype(np.uint8),
                (frame_shape[1], frame_shape[0]),
                interpolation=cv2.INTER_NEAREST
            )

        binary = np.zeros(mask.shape[:2], dtype=np.uint8)
        binary[mask > 0] = 255

        return binary

    def create_road_ring_mask(self, pothole_mask):
        """
        Tạo vùng đường xung quanh ổ gà bằng cách dilate mask rồi trừ mask gốc.
        road_ring = vùng tham chiếu để so sánh độ sáng.
        """
        kernel = np.ones((self.ring_kernel_size, self.ring_kernel_size), np.uint8)

        dilated = cv2.dilate(pothole_mask, kernel, iterations=1)
        road_ring = cv2.subtract(dilated, pothole_mask)

        return road_ring

    def detect_water(self, frame_bgr, pothole_mask):
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        mask = pothole_mask > 0
        total = np.count_nonzero(mask)

        if total == 0:
            return False, {}

        v = hsv[:, :, 2]
        s = hsv[:, :, 1]

        # =========================
        # 1. XÁC ĐỊNH NGÀY / ĐÊM
        # =========================
        # global_mean_v: độ sáng trung bình toàn ảnh
        # pothole_mean_v: độ sáng trung bình trong vùng ổ gà
        global_mean_v = float(np.mean(v))
        pothole_mean_v = float(np.mean(v[mask]))

        # Tỷ lệ pixel tối trong toàn ảnh
        dark_global_ratio = np.count_nonzero(v < 80) / v.size

        # Tỷ lệ pixel rất sáng trong toàn ảnh, thường là đèn xe/đèn đường
        bright_global_ratio = np.count_nonzero(v > 180) / v.size

        # Ảnh ban đêm thường có nhiều vùng tối,
        # dù có một số vùng rất sáng do đèn xe/đèn đường
        is_night = (
            global_mean_v < 140 and dark_global_ratio > 0.30
        ) or (
            dark_global_ratio > 0.40 and bright_global_ratio > 0.03
        )

        # =========================
        # 2. TÍNH TEXTURE
        # =========================
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        texture_values = np.abs(lap[mask])

        # =========================
        # 3. RULE BAN ĐÊM
        # =========================
        if is_night:
            # Ban đêm: ánh phản chiếu thường yếu hơn, không cần V quá cao
            # s nới rộng hơn vì nước có thể phản chiếu đèn vàng/đỏ
            highlight_mask = (v > 120) & (s < 170) & mask
            dark_smooth_mask = (gray < 150) & (s < 180) & mask

            highlight_ratio = np.count_nonzero(highlight_mask) / total
            dark_smooth_ratio = np.count_nonzero(dark_smooth_mask) / total
            low_texture_ratio = np.count_nonzero(texture_values < 12) / total

            water_score = 0

            if highlight_ratio > 0.05:
                water_score += 1

            if dark_smooth_ratio > 0.20:                                              
                water_score += 1

            if low_texture_ratio > 0.20:
                water_score += 1

            # Ban đêm dễ nhầm mặt đường tối thành nước,
            # nên vẫn yêu cầu vùng đó phải tương đối mịn
            has_water = water_score >= 2 and low_texture_ratio > 0.15

        # =========================
        # 4. RULE BAN NGÀY
        # =========================
        else:
            highlight_mask = (v > 180) & (s < 90) & mask
            dark_smooth_mask = (gray < 130) & (s < 100) & mask

            highlight_ratio = np.count_nonzero(highlight_mask) / total
            dark_smooth_ratio = np.count_nonzero(dark_smooth_mask) / total
            low_texture_ratio = np.count_nonzero(texture_values < 8) / total

            water_score = 0

            if highlight_ratio > 0.18:
                water_score += 1

            if dark_smooth_ratio > 0.22:
                water_score += 1

            if low_texture_ratio > 0.221:
                water_score += 1

            has_water = water_score >= 2

        info = {
            "is_night": bool(is_night),
            "global_mean_v": float(global_mean_v),
            "pothole_mean_v": float(pothole_mean_v),
            "dark_global_ratio": float(dark_global_ratio),
            "bright_global_ratio": float(bright_global_ratio),
            "highlight_ratio": float(highlight_ratio),
            "dark_smooth_ratio": float(dark_smooth_ratio),
            "low_texture_ratio": float(low_texture_ratio),
            "water_score": water_score
        }

        return has_water, info

    def estimate_relative_depth_by_brightness(self, frame_bgr, pothole_mask, road_ring_mask):
        """
        Nếu ổ gà khô:
        - CLAHE ảnh
        - lấy gray
        - so sánh mean brightness giữa road_ring và pothole
        depth_score = road_mean - pothole_mean
        Nếu pothole tối hơn vùng đường xung quanh nhiều => nghi sâu hơn.
        """
        clahe_img = self.apply_clahe(frame_bgr)
        gray = cv2.cvtColor(clahe_img, cv2.COLOR_BGR2GRAY)

        pothole_pixels = gray[pothole_mask > 0]
        road_pixels = gray[road_ring_mask > 0]

        if len(pothole_pixels) == 0 or len(road_pixels) == 0:
            return {
                "depth_status": "invalid",
                "depth_score": 0.0,
                "depth_level": "Không xác định",
                "pothole_brightness": 0.0,
                "road_brightness": 0.0,
            }

        pothole_mean = float(np.mean(pothole_pixels))
        road_mean = float(np.mean(road_pixels))
        
        depth_score = road_mean - pothole_mean
        
        if depth_score < 8:
            level = "Nông"
        elif depth_score < 28:
            level = "Trung bình"
        else:
            level = "Sâu"

        return {
            "depth_status": "estimated",
            "depth_score": float(depth_score),
            "depth_level": level,
            "pothole_brightness": pothole_mean,
            "road_brightness": road_mean,
        }

    def analyze(self, frame_bgr, pothole_mask):
        """
        Hàm chính để gọi trong map_report.py
        """
        pothole_mask = self.ensure_binary_mask(pothole_mask, frame_bgr.shape)

        if pothole_mask is None or np.count_nonzero(pothole_mask) == 0:
            return {
                "has_water": False,
                "depth_status": "invalid_mask",
                "depth_confidence": "Thấp",
                "depth_level": "Không xác định",
                "depth_score": 0.0,
                "water_info": {}
            }

        road_ring_mask = self.create_road_ring_mask(pothole_mask)

        has_water, water_info = self.detect_water(frame_bgr, pothole_mask)

        if has_water:
            try:
                depth_anything_result = self.depth_anything.estimate_water_pothole_depth(
                    frame_bgr=frame_bgr,
                    pothole_mask=pothole_mask,
                    road_ring_mask=road_ring_mask
                )
                
                return {
                    "has_water": True,
                    "depth_status": depth_anything_result["depth_status"],
                    "depth_confidence": "Trung bình",
                    "depth_level": depth_anything_result["depth_level"],
                    "depth_score": depth_anything_result["depth_score"],

                    "pothole_depth_mean": depth_anything_result["pothole_depth_mean"],
                    "road_depth_mean": depth_anything_result["road_depth_mean"],
                    "depth_method": depth_anything_result["depth_method"],

                    "depth_score_da": depth_anything_result.get("depth_score_da", 0.0),
                    "dark_rim_ratio": depth_anything_result.get("dark_rim_ratio", 0.0),
                    "rim_score": depth_anything_result.get("rim_score", 0.0),
                    "contrast_score": depth_anything_result.get("contrast_score", 0.0),

                    "pothole_brightness": depth_anything_result.get("pothole_brightness", 0.0),
                    "road_brightness": depth_anything_result.get("road_brightness", 0.0),

                    "water_info": water_info
                }
            except Exception as error:
                return {
                    "has_water": True,
                    "depth_status": f"depth_anything_error: {error}",
                    "depth_confidence": "Thấp",
                    "depth_level": "Không xác định",
                    "depth_score": 0.0,
                    "pothole_depth_mean": 0.0,
                    "road_depth_mean": 0.0,
                    "depth_method": "Depth Anything V2 Small",
                    "water_info": water_info
                }

        depth_result = self.estimate_relative_depth_by_brightness(
            frame_bgr,
            pothole_mask,
            road_ring_mask
        )

        return {
            "has_water": False,
            "depth_status": depth_result["depth_status"],
            "depth_confidence": "Trung bình",
            "depth_level": depth_result["depth_level"],
            "depth_score": depth_result["depth_score"],
            "pothole_brightness": depth_result["pothole_brightness"],
            "road_brightness": depth_result["road_brightness"],
            "water_info": water_info
        }

    def draw_result_on_frame(self, frame_bgr, analysis_result, start_y=140):
        """
        Vẽ kết quả lên frame để hiển thị trong demo.
        """
        output = frame_bgr.copy()

        has_water = analysis_result.get("has_water", False)
        depth_level = analysis_result.get("depth_level", "Không xác định")
        depth_score = analysis_result.get("depth_score", 0.0)
        confidence = analysis_result.get("depth_confidence", "Thấp")

        water_text = "YES" if has_water else "NO"

        water_info = analysis_result.get("water_info", {})

        lines = [
            f"Water: {water_text}",
            f"Water score: {water_info.get('water_score', 0)}",
            f"Highlight: {water_info.get('highlight_ratio', 0):.2f}",
            f"Dark smooth: {water_info.get('dark_smooth_ratio', 0):.2f}",
            f"Low texture: {water_info.get('low_texture_ratio', 0):.2f}",
            f"Depth level: {depth_level}",
            f"Depth score: {depth_score:.2f}",
            f"Depth confidence: {confidence}",
        ]
        y = start_y
        for line in lines:
            cv2.putText(
                output,
                line,
                (30, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (0, 255, 255),
                2,
                cv2.LINE_AA
            )
            y += 30

        return output


def get_first_yolo_mask(result, frame_shape):
    """
    Lấy mask đầu tiên từ kết quả YOLO segmentation.
    Dùng cho demo nhanh trong map_report.py.

    Lưu ý:
    - Nếu có nhiều ổ gà, nên loop qua từng mask.
    - Hàm này lấy mask đầu tiên để tích hợp đơn giản trước.
    """
    if result is None or result.masks is None:
        return None

    if result.masks.data is None or len(result.masks.data) == 0:
        return None

    mask = result.masks.data[0].detach().cpu().numpy()
    mask = cv2.resize(mask, (frame_shape[1], frame_shape[0]), interpolation=cv2.INTER_NEAREST)

    binary = np.zeros(frame_shape[:2], dtype=np.uint8)
    binary[mask > 0.5] = 255

    return binary