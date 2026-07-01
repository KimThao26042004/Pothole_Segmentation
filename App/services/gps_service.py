import csv
from bisect import bisect_left


class GPSService:
    """Đọc GPS CSV và tìm tọa độ gần nhất theo thời điểm video."""

    def __init__(self):
        self.gps_points = []
        self.gps_timestamps = []

    def load_csv(self, csv_path):
        points = []

        with open(csv_path, "r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)

            required_cols = {"timestamp", "latitude", "longitude"}
            if not required_cols.issubset(reader.fieldnames or []):
                raise ValueError("CSV phải có các cột: timestamp, latitude, longitude")

            for row in reader:
                points.append({
                    "timestamp": float(row["timestamp"]),
                    "latitude": float(row["latitude"]),
                    "longitude": float(row["longitude"]),
                    "road_name": row.get("road_name", "Chưa xác định")
                })

        points.sort(key=lambda item: item["timestamp"])

        if len(points) < 1:
            raise ValueError("CSV cần ít nhất 1 dòng GPS.")

        self.gps_points = points
        self.gps_timestamps = [item["timestamp"] for item in points]

        return points

    def get_by_time(self, current_time):
        if not self.gps_points:
            return None, None, "Chưa xác định"

        pos = bisect_left(self.gps_timestamps, current_time)

        if pos <= 0:
            nearest = self.gps_points[0]
        elif pos >= len(self.gps_points):
            nearest = self.gps_points[-1]
        else:
            before = self.gps_points[pos - 1]
            after = self.gps_points[pos]
            if abs(before["timestamp"] - current_time) <= abs(after["timestamp"] - current_time):
                nearest = before
            else:
                nearest = after

        return (
            float(nearest["latitude"]),
            float(nearest["longitude"]),
            str(nearest.get("road_name", "Chưa xác định"))
        )

    def clear(self):
        self.gps_points = []
        self.gps_timestamps = []
