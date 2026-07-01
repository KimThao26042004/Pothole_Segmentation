from PyQt5.QtCore import QSettings


class RememberLoginManager:
    """
    Quản lý chức năng nhớ thông tin đăng nhập bằng QSettings.

    Lưu ý:
    - Cách này phù hợp demo đồ án / chạy nội bộ.
    - Nếu triển khai thực tế, nên lưu token đăng nhập thay vì lưu mật khẩu.
    """

    ORG_NAME = "PotholeDetectionUTC2"
    APP_NAME = "LoginRemember"

    def __init__(self):
        self.settings = QSettings(self.ORG_NAME, self.APP_NAME)

    def load(self):
        remember = self.settings.value("remember_password", False, type=bool)

        if not remember:
            return {
                "remember": False,
                "username": "",
                "password": "",
            }

        return {
            "remember": True,
            "username": self.settings.value("login_username", "", type=str),
            "password": self.settings.value("login_password", "", type=str),
        }

    def save(self, username, password, remember):
        if remember:
            self.settings.setValue("remember_password", True)
            self.settings.setValue("login_username", username)
            self.settings.setValue("login_password", password)
        else:
            self.clear()

    def clear(self):
        self.settings.remove("remember_password")
        self.settings.remove("login_username")
        self.settings.remove("login_password")
