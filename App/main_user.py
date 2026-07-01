import sys

from PyQt5.QtWidgets import QApplication

from repositories.report_repository import ReportRepository
from user.map_report_window import PotholeMapReportWindow


if __name__ == "__main__":
    ReportRepository().init_database()

    app = QApplication(sys.argv)
    window = PotholeMapReportWindow()
    window.showMaximized()
    sys.exit(app.exec_())
