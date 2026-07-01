import cv2
import argparse
import pandas as pd
import numpy as np
from pathlib import Path


def get_video_duration(video_path: str) -> float:
    """
    Lấy thời lượng video theo giây.
    """
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise ValueError(f"Không mở được video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)

    cap.release()

    if fps <= 0:
        raise ValueError("Không lấy được FPS của video.")

    duration = frame_count / fps
    return duration


def generate_gps_log(
    video_path: str,
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    interval: float = 1.0
):
    """
    Sinh GPS log giả lập cho video.
    Mỗi dòng CSV tương ứng với một mốc thời gian trong video.
    """

    video_path = Path(video_path)

    if not video_path.exists():
        raise FileNotFoundError(f"Không tìm thấy video: {video_path}")

    duration = get_video_duration(str(video_path))

    # Tạo timestamp từ 0 đến hết video
    timestamps = np.arange(0, duration + interval, interval)

    # Không để timestamp vượt quá duration quá nhiều
    timestamps = timestamps[timestamps <= duration]

    # Nội suy latitude, longitude từ điểm đầu đến điểm cuối
    latitudes = np.linspace(start_lat, end_lat, len(timestamps))
    longitudes = np.linspace(start_lng, end_lng, len(timestamps))

    gps_df = pd.DataFrame({
        "timestamp": timestamps.round(2),
        "latitude": latitudes,
        "longitude": longitudes
    })

    # Tạo tên file CSV cùng thư mục với video
    output_csv = video_path.with_name(video_path.stem + "_gps.csv")

    gps_df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    print("Đã tạo GPS log thành công!")
    print(f"Video: {video_path}")
    print(f"Thời lượng video: {duration:.2f} giây")
    print(f"File CSV: {output_csv}")
    print(f"Số dòng GPS: {len(gps_df)}")

    return output_csv


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sinh file GPS CSV giả lập cho video."
    )

    parser.add_argument(
        "--video",
        required=True,
        help="Đường dẫn video đầu vào."
    )

    parser.add_argument(
        "--start_lat",
        type=float,
        required=True,
        help="Vĩ độ điểm bắt đầu."
    )

    parser.add_argument(
        "--start_lng",
        type=float,
        required=True,
        help="Kinh độ điểm bắt đầu."
    )

    parser.add_argument(
        "--end_lat",
        type=float,
        required=True,
        help="Vĩ độ điểm kết thúc."
    )

    parser.add_argument(
        "--end_lng",
        type=float,
        required=True,
        help="Kinh độ điểm kết thúc."
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Khoảng cách thời gian giữa các điểm GPS, đơn vị giây. Mặc định 1 giây."
    )

    args = parser.parse_args()

    generate_gps_log(
        video_path=args.video,
        start_lat=args.start_lat,
        start_lng=args.start_lng,
        end_lat=args.end_lat,
        end_lng=args.end_lng,
        interval=args.interval
    )