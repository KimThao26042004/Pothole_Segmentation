import cv2
import numpy as np

points = []

image_path = r"D:\IT\NCKHSV_2025-2026\PotholeApp\App\sample_images\ref_object\setup3_nozoom_pothole 68.jpg"

img_original = cv2.imread(image_path)

if img_original is None:
    print("Không đọc được ảnh:", image_path)
    exit()

# Tỉ lệ thu nhỏ ảnh để dễ click
scale = 0.5

img_display = cv2.resize(
    img_original,
    None,
    fx=scale,
    fy=scale
)

def click_event(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        # Quy đổi tọa độ ảnh nhỏ về tọa độ ảnh gốc
        original_x = int(x / scale)
        original_y = int(y / scale)

        points.append([original_x, original_y])

        print(f"Point {len(points)} display: [{x}, {y}]")
        print(f"Point {len(points)} original: [{original_x}, {original_y}]")

        cv2.circle(img_display, (x, y), 5, (0, 0, 255), -1)
        cv2.imshow("Select 4 corners", img_display)

cv2.imshow("Select 4 corners", img_display)
cv2.setMouseCallback("Select 4 corners", click_event)

cv2.waitKey(0)
cv2.destroyAllWindows()

src_points = np.float32(points)

print("src_points = np.float32([")
for p in points:
    print(f"    [{p[0]}, {p[1]}],")
print("])")