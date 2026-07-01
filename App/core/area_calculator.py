import os
import cv2
import numpy as np


class PotholeAreaCalculator:
    """
    Tính diện tích ổ gà từ YOLO segmentation mask bằng Homography.

    Cách tính:
    - Homography .npy phải là ma trận chuyển từ pixel ảnh -> tọa độ mét thực tế.
    - Mask YOLO được lấy contour.
    - Contour pixel được biến đổi sang contour mét.
    - Diện tích = cv2.contourArea(contour_meters), đơn vị m².
    """

    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.homography_dir = os.path.join(base_dir, "homography")

    def load_homography(self, setup_name):
        h_path = os.path.join(self.homography_dir, f"{setup_name}.npy")

        if not os.path.exists(h_path):
            raise FileNotFoundError(f"Không tìm thấy file homography: {h_path}")

        return np.load(h_path).astype(np.float32)

    def resize_mask_to_frame(self, mask, frame_shape):
        frame_h, frame_w = frame_shape[:2]

        mask_resized = cv2.resize(
            mask,
            (frame_w, frame_h),
            interpolation=cv2.INTER_LINEAR
        )

        return mask_resized

    def calculate_area_from_mask(self, mask, frame_shape, setup_name):
        """
        Tính diện tích 1 mask ổ gà.

        Return:
        - area_m2: diện tích m²
        - area_pixel: diện tích pixel gốc của mask
        - mask_binary: mask nhị phân để debug
        """
        H = self.load_homography(setup_name)

        mask_resized = self.resize_mask_to_frame(mask, frame_shape)
        mask_binary = (mask_resized > 0.5).astype(np.uint8)

        area_pixel = int(np.sum(mask_binary))

        contours, _ = cv2.findContours(
            mask_binary,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        area_m2 = 0.0

        for contour in contours:

            pixel_area = cv2.contourArea(contour)

            if pixel_area < 500:
                continue

            contour_float = contour.reshape(-1, 1, 2).astype(np.float32)

            contour_meter = cv2.perspectiveTransform(
                contour_float,
                H
            )

            if np.abs(contour_meter).max() > 20:
                continue

            area = abs(cv2.contourArea(contour_meter))

            if area > 10:
                continue

            area_m2 += area

        return area_m2, area_pixel, mask_binary

    def calculate_total_area_from_yolo_result(self, result, frame, setup_name):
        """
        Tính tổng diện tích tất cả vùng hư hỏng trong 1 frame.
        """
        if result.masks is None:
            return 0.0, 0, []

        masks = result.masks.data.cpu().numpy()

        total_area_m2 = 0.0
        total_area_pixel = 0
        debug_masks = []

        for mask in masks:
            area_m2, area_pixel, mask_binary = self.calculate_area_from_mask(
                mask=mask,
                frame_shape=frame.shape,
                setup_name=setup_name
            )

            total_area_m2 += area_m2
            total_area_pixel += area_pixel
            debug_masks.append(mask_binary)

        return total_area_m2, total_area_pixel, debug_masks