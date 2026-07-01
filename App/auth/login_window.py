import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QColor
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QTabWidget,
    QFormLayout,
    QCheckBox,
    QSizePolicy,
    QGraphicsDropShadowEffect,
)

from services.auth_service import AuthService
from auth.auth_styles import LOGIN_QSS
from auth.validators import validate_register_data
from auth.remember_login import RememberLoginManager


try:
    from config import LOGO_PATH
except Exception:
    try:
        from app_settings import LOGO_PATH
    except Exception:
        LOGO_PATH = ""


class LoginRegisterWindow(QWidget):
    """
    Cửa sổ đăng nhập / đăng ký dùng chung cho app User và Admin.

    File này chỉ quản lý giao diện và sự kiện.
    Các phần phụ đã được tách:
    - auth_styles.py: giao diện QSS.
    - validators.py: kiểm tra dữ liệu đăng ký.
    - remember_login.py: nhớ tài khoản / mật khẩu.
    - services/auth_service.py: xử lý database users, hash password, login/register.
    """

    def __init__(self, on_login_success):
        super().__init__()

        self.auth_service = AuthService()
        self.auth_service.seed_default_manager()
        self.remember_manager = RememberLoginManager()
        self.on_login_success = on_login_success

        self.setWindowTitle("Đăng nhập hệ thống")
        self.resize(900, 760)
        self.setMinimumSize(850, 720)

        self.build_ui()
        self.load_remembered_login()

    # ============================================================
    # UI
    # ============================================================

    def build_ui(self):
        self.setStyleSheet(LOGIN_QSS)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(36, 28, 36, 28)
        root_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(42, 36, 42, 38)
        card_layout.setSpacing(24)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 55))
        card.setGraphicsEffect(shadow)

        card_layout.addLayout(self.build_header())

        self.tabs = QTabWidget()
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.build_login_tab()
        self.build_register_tab()

        card_layout.addWidget(self.tabs, 1)

        root_layout.addStretch(1)
        root_layout.addWidget(card)
        root_layout.addStretch(1)

    def build_header(self):
        header_layout = QHBoxLayout()
        header_layout.setSpacing(20)

        logo_label = QLabel()
        logo_label.setFixedSize(90, 90)
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet("""
            QLabel {
                background: #EFF6FF;
                border: 1px solid #BFDBFE;
                border-radius: 22px;
                color: #1D4ED8;
                font-size: 32px;
                font-weight: 900;
            }
        """)

        if LOGO_PATH and os.path.exists(LOGO_PATH):
            pixmap = QPixmap(LOGO_PATH).scaled(
                68,
                68,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            logo_label.setPixmap(pixmap)
        else:
            logo_label.setText("UTC")

        text_layout = QVBoxLayout()
        text_layout.setSpacing(6)

        title = QLabel("Hệ thống giám sát ổ gà")
        title.setObjectName("appTitle")

        subtitle = QLabel("Đăng nhập để gửi báo cáo hoặc quản lý dữ liệu")
        subtitle.setObjectName("appSubtitle")
        subtitle.setWordWrap(True)

        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)

        header_layout.addWidget(logo_label)
        header_layout.addLayout(text_layout, 1)

        return header_layout

    def build_login_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 24, 4, 4)
        layout.setSpacing(18)

        title = QLabel("Đăng nhập")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(18)

        self.login_username = QLineEdit()
        self.login_username.setPlaceholderText("Nhập tên đăng nhập hoặc email")

        self.login_password = QLineEdit()
        self.login_password.setPlaceholderText("Nhập mật khẩu")
        self.login_password.setEchoMode(QLineEdit.Password)

        form.addRow("Tài khoản:", self.login_username)
        form.addRow("Mật khẩu:", self.login_password)

        layout.addLayout(form)

        option_row = QHBoxLayout()
        option_row.setSpacing(18)

        self.chk_login_show_password = QCheckBox("Hiện mật khẩu")
        self.chk_login_show_password.stateChanged.connect(self.toggle_login_password)

        self.chk_remember_password = QCheckBox("Nhớ mật khẩu")

        option_row.addWidget(self.chk_login_show_password)
        option_row.addStretch(1)
        option_row.addWidget(self.chk_remember_password)

        layout.addLayout(option_row)

        self.login_status = QLabel("")
        self.login_status.hide()
        layout.addWidget(self.login_status)

        self.btn_login = QPushButton("Đăng nhập")
        self.btn_login.clicked.connect(self.handle_login)
        layout.addWidget(self.btn_login)

        layout.addStretch(1)

        self.login_username.returnPressed.connect(self.handle_login)
        self.login_password.returnPressed.connect(self.handle_login)

        self.tabs.addTab(tab, "Đăng nhập")

    def build_register_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 24, 4, 4)
        layout.setSpacing(16)

        title = QLabel("Đăng ký tài khoản người dùng")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(14)

        self.reg_full_name = QLineEdit()
        self.reg_full_name.setPlaceholderText("Ví dụ: Nguyễn Văn A")

        self.reg_username = QLineEdit()
        self.reg_username.setPlaceholderText("4-30 ký tự, chữ/số/gạch dưới")

        self.reg_email = QLineEdit()
        self.reg_email.setPlaceholderText("Ví dụ: user@gmail.com")

        self.reg_password = QLineEdit()
        self.reg_password.setPlaceholderText("Ít nhất 8 ký tự, có hoa/thường/số/ký tự đặc biệt")
        self.reg_password.setEchoMode(QLineEdit.Password)

        self.reg_confirm_password = QLineEdit()
        self.reg_confirm_password.setPlaceholderText("Nhập lại mật khẩu")
        self.reg_confirm_password.setEchoMode(QLineEdit.Password)

        form.addRow("Họ tên:", self.reg_full_name)
        form.addRow("Tên đăng nhập:", self.reg_username)
        form.addRow("Email:", self.reg_email)
        form.addRow("Mật khẩu:", self.reg_password)
        form.addRow("Xác nhận:", self.reg_confirm_password)

        layout.addLayout(form)

        self.chk_register_show_password = QCheckBox("Hiện mật khẩu")
        self.chk_register_show_password.stateChanged.connect(self.toggle_register_password)
        layout.addWidget(self.chk_register_show_password)

        self.register_status = QLabel("")
        self.register_status.hide()
        layout.addWidget(self.register_status)

        self.btn_register = QPushButton("Tạo tài khoản")
        self.btn_register.setObjectName("registerButton")
        self.btn_register.clicked.connect(self.handle_register)
        layout.addWidget(self.btn_register)

        layout.addStretch(1)

        self.reg_full_name.returnPressed.connect(self.handle_register)
        self.reg_username.returnPressed.connect(self.handle_register)
        self.reg_email.returnPressed.connect(self.handle_register)
        self.reg_password.returnPressed.connect(self.handle_register)
        self.reg_confirm_password.returnPressed.connect(self.handle_register)

        self.tabs.addTab(tab, "Đăng ký")

    # ============================================================
    # PASSWORD VISIBILITY / REMEMBER
    # ============================================================

    def toggle_login_password(self):
        if self.chk_login_show_password.isChecked():
            self.login_password.setEchoMode(QLineEdit.Normal)
        else:
            self.login_password.setEchoMode(QLineEdit.Password)

    def toggle_register_password(self):
        mode = QLineEdit.Normal if self.chk_register_show_password.isChecked() else QLineEdit.Password
        self.reg_password.setEchoMode(mode)
        self.reg_confirm_password.setEchoMode(mode)

    def load_remembered_login(self):
        remembered = self.remember_manager.load()

        if not remembered["remember"]:
            return

        self.login_username.setText(remembered["username"])
        self.login_password.setText(remembered["password"])
        self.chk_remember_password.setChecked(True)

    def save_remembered_login(self, username, password):
        self.remember_manager.save(
            username=username,
            password=password,
            remember=self.chk_remember_password.isChecked(),
        )

    # ============================================================
    # VALIDATION / STATUS
    # ============================================================

    def show_status(self, label, message, success=False):
        label.setText(message)
        label.setObjectName("statusSuccess" if success else "statusError")
        label.style().unpolish(label)
        label.style().polish(label)
        label.show()

    # ============================================================
    # ACTIONS
    # ============================================================

    def handle_login(self):
        username = self.login_username.text().strip()
        password = self.login_password.text()

        if not username:
            self.show_status(self.login_status, "Vui lòng nhập tài khoản.", success=False)
            return

        if not password:
            self.show_status(self.login_status, "Vui lòng nhập mật khẩu.", success=False)
            return

        user = self.auth_service.authenticate(username, password)

        if user is None:
            self.show_status(
                self.login_status,
                "Đăng nhập thất bại. Sai tài khoản, sai mật khẩu hoặc tài khoản đã bị khóa.",
                success=False,
            )
            return

        self.save_remembered_login(username, password)

        self.show_status(
            self.login_status,
            f"Đăng nhập thành công: {user['full_name'] or user['username']} | Quyền: {user['role']}",
            success=True,
        )

        QMessageBox.information(
            self,
            "Đăng nhập thành công",
            f"Xin chào {user['full_name'] or user['username']}!\nQuyền: {user['role']}"
        )

        self.on_login_success(user)
        self.close()

    def handle_register(self):
        full_name = self.reg_full_name.text().strip()
        username = self.reg_username.text().strip()
        email = self.reg_email.text().strip()
        password = self.reg_password.text()
        confirm_password = self.reg_confirm_password.text()

        errors = validate_register_data(
            full_name=full_name,
            username=username,
            email=email,
            password=password,
            confirm_password=confirm_password,
        )

        if errors:
            self.show_status(
                self.register_status,
                "Đăng ký thất bại:\n- " + "\n- ".join(errors),
                success=False,
            )
            return

        try:
            self.auth_service.create_user(
                username=username,
                password=password,
                email=email,
                full_name=full_name,
                role="user",
            )

            self.show_status(
                self.register_status,
                "Đăng ký thành công. Bạn có thể chuyển sang tab Đăng nhập.",
                success=True,
            )

            QMessageBox.information(
                self,
                "Đăng ký thành công",
                "Tài khoản người dùng đã được tạo. Bạn có thể đăng nhập ngay."
            )

            self.login_username.setText(username)
            self.login_password.clear()
            self.tabs.setCurrentIndex(0)

        except Exception as error:
            self.show_status(
                self.register_status,
                f"Đăng ký thất bại: {error}",
                success=False,
            )
