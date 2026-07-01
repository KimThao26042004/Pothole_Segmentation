from PyQt5.QtCore import QObject, pyqtSlot


class MapBridge(QObject):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

    @pyqtSlot(float, float)
    def receive_location(self, lat, lng):
        self.main_window.selected_lat = lat
        self.main_window.selected_lng = lng
        self.main_window.update_address_from_coordinates(lat, lng)

    @pyqtSlot(str)
    def show_report_image(self, image_path):
        self.main_window.show_report_image_from_map(image_path)

    @pyqtSlot(str)
    def show_pothole_analysis(self, analysis_html):
        if analysis_html:
            self.main_window.lbl_analysis_info.setText(analysis_html)
            self.main_window.lbl_alert.setText(
                "Đang xem thông tin phân tích của ổ gà đã chọn trên bản đồ"
            )
        else:
            self.main_window.lbl_analysis_info.setText(
                "Thông tin phân tích: Chưa có dữ liệu"
            )
            self.main_window.lbl_alert.setText(
                "Marker này chưa có thông tin phân tích"
            )