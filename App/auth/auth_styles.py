LOGIN_QSS = """
QWidget {
    background: #F3F4F6;
    color: #111827;
    font-family: "Segoe UI";
    font-size: 16px;
}

QFrame#card {
    background: #FFFFFF;
    border-radius: 22px;
    border: 1px solid #E5E7EB;
}

QLabel#appTitle {
    font-size: 30px;
    font-weight: 900;
    color: #111827;
}

QLabel#appSubtitle {
    font-size: 16px;
    font-weight: 600;
    color: #6B7280;
}

QLabel#sectionTitle {
    font-size: 22px;
    font-weight: 900;
    color: #111827;
    padding-bottom: 8px;
}

QLabel#statusSuccess {
    background: #ECFDF5;
    color: #047857;
    border: 1px solid #A7F3D0;
    border-radius: 10px;
    padding: 12px;
    font-size: 15px;
    font-weight: 800;
}

QLabel#statusError {
    background: #FEF2F2;
    color: #B91C1C;
    border: 1px solid #FECACA;
    border-radius: 10px;
    padding: 12px;
    font-size: 15px;
    font-weight: 800;
}

QLineEdit {
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 12px;
    padding: 14px 16px;
    color: #111827;
    font-size: 16px;
    selection-background-color: #2563EB;
    min-height: 22px;
}

QLineEdit:focus {
    border: 2px solid #2563EB;
    background: #FFFFFF;
}

QPushButton {
    background: #2563EB;
    color: white;
    border: none;
    border-radius: 12px;
    padding: 15px 18px;
    font-weight: 900;
    font-size: 16px;
    min-height: 24px;
}

QPushButton:hover {
    background: #1D4ED8;
}

QPushButton:pressed {
    background: #1E40AF;
}

QPushButton#registerButton {
    background: #F97316;
}

QPushButton#registerButton:hover {
    background: #EA580C;
}

QPushButton#ghostButton {
    background: #F8FAFC;
    color: #1F2937;
    border: 1px solid #CBD5E1;
}

QPushButton#ghostButton:hover {
    background: #E5E7EB;
}

QCheckBox {
    color: #374151;
    font-size: 15px;
    font-weight: 700;
    spacing: 9px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
}

QTabWidget::pane {
    border: none;
    background: transparent;
}

QTabBar::tab {
    background: #F3F4F6;
    color: #374151;
    padding: 14px 34px;
    margin-right: 8px;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
    font-size: 16px;
    font-weight: 900;
    min-width: 120px;
}

QTabBar::tab:selected {
    background: #2563EB;
    color: white;
}

QTabBar::tab:hover {
    background: #DBEAFE;
    color: #1D4ED8;
}

QLabel#hintText {
    color: #64748B;
    font-size: 14px;
    font-weight: 600;
    padding-top: 6px;
    line-height: 1.4;
}
"""
