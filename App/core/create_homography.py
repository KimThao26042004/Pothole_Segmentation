import cv2
import numpy as np
import os

# =========================
# 1. CẤU HÌNH SETUP
# =========================

# Đường dẫn ảnh calibration
image_path = r"D:\IT\NCKHSV_2025-2026\PotholeApp\App\sample_images\ref_object\setup3_nozoom_pothole 68.jpg"

# Tên setup để lưu file
setup_name = "setup3_nozoom"

# =========================
# TỌA ĐỘ 4 GÓC VẬT CHUẨN
# =========================
# Thứ tự:
# top-left
# top-right
# bottom-right
# bottom-left

src_points = np.float32([
    [528, 594],
    [1012, 624],
    [952, 834],
    [160, 748],
])

# =========================
# TỌA ĐỘ THẬT NGOÀI ĐỜI (MÉT)
# =========================
# Vật chuẩn thật: 1m x 1m

dst_points = np.float32([
    [0, 0],
    [1, 0],
    [1, 1],
    [0, 1]
])

# =========================
# FOLDER OUTPUT
# =========================

homography_dir = "homography"
output_dir = "output_homography"

os.makedirs(homography_dir, exist_ok=True)
os.makedirs(output_dir, exist_ok=True)

# =========================
# 2. ĐỌC ẢNH
# =========================

image = cv2.imread(image_path)

if image is None:
    print("Không đọc được ảnh. Kiểm tra lại đường dẫn:")
    print(image_path)
    exit()

# =========================
# 3. TẠO HOMOGRAPHY
# =========================
# Homography:
# pixel ảnh -> tọa độ mét thật

H = cv2.getPerspectiveTransform(src_points, dst_points)

homography_path = os.path.join(
    homography_dir,
    f"{setup_name}.npy"
)

np.save(homography_path, H)

print("===================================")
print("ĐÃ LƯU HOMOGRAPHY")
print(homography_path)

print("\nHomography Matrix:")
print(H)

# =========================
# 4. WARP TEST ĐỂ KIỂM TRA
# =========================
# H gốc: pixel ảnh -> mét thật
# H_visual: pixel ảnh -> pixel ảnh test 500x500

test_pixels_per_meter = 500

S = np.array([
    [test_pixels_per_meter, 0, 0],
    [0, test_pixels_per_meter, 0],
    [0, 0, 1]
], dtype=np.float32)

H_visual = S @ H

warped_image = cv2.warpPerspective(
    image,
    H_visual,
    (test_pixels_per_meter, test_pixels_per_meter)
)

# =========================
# 5. HIỂN THỊ DEBUG
# =========================

display_scale = 0.5

display_original = cv2.resize(
    image,
    None,
    fx=display_scale,
    fy=display_scale
)

# Vẽ 4 góc vật chuẩn
for idx, point in enumerate(src_points):

    x = int(point[0] * display_scale)
    y = int(point[1] * display_scale)

    cv2.circle(
        display_original,
        (x, y),
        6,
        (0, 0, 255),
        -1
    )

    cv2.putText(
        display_original,
        str(idx + 1),
        (x + 10, y - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2
    )

# =========================
# SHOW WINDOW
# =========================

cv2.imshow(
    "Original Image - Selected Points",
    display_original
)

cv2.imshow(
    "Top-down View Test",
    warped_image
)

cv2.waitKey(0)
cv2.destroyAllWindows()