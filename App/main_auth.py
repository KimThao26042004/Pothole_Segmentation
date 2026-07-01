import sys
from PyQt5.QtWidgets import QApplication

from auth.login_window import LoginRegisterWindow
from user.map_report_window import PotholeMapReportWindow

# Nếu main_window.py nằm ở thư mục gốc App/
from ui.main_window import YOLOApp

# Nếu admin của bạn nằm trong ui/main_window.py thì dùng dòng này thay cho dòng trên:
# from ui.main_window import YOLOApp


class AppLauncher:
    def __init__(self):
        self.login_window = None
        self.main_window = None

    def start(self):
        self.login_window = LoginRegisterWindow(
            on_login_success=self.open_by_role
        )
        self.login_window.show()

    def open_by_role(self, user):
        role = user.get("role", "user")

        if role == "manager":
            self.main_window = YOLOApp()
            self.main_window.setWindowTitle(
                f"Admin - {user.get('username')} | Quản lý báo cáo ổ gà"
            )
        else:
            self.main_window = PotholeMapReportWindow(
                current_user=user
            )

        self.main_window.show()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    launcher = AppLauncher()
    launcher.start()

    sys.exit(app.exec_())
