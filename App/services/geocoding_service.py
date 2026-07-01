import requests


class GeocodingService:
    """Gọi Nominatim để search địa chỉ và reverse geocode."""

    def __init__(self):
        self.headers = {"User-Agent": "PotholeDetectionDemo/1.0"}

    def search(self, query, limit=1):
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": query,
            "format": "json",
            "limit": limit,
            "countrycodes": "vn",
            "addressdetails": 1
        }
        response = requests.get(url, params=params, headers=self.headers, timeout=10)
        response.raise_for_status()
        return response.json()

    def reverse(self, lat, lng):
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": lat,
            "lon": lng,
            "format": "json",
            "zoom": 18,
            "addressdetails": 1
        }
        response = requests.get(url, params=params, headers=self.headers, timeout=10)
        response.raise_for_status()
        return response.json()
