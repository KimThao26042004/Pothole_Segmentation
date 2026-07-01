APP_STYLE = """
QWidget {
    background-color: #F7F7F7;
    color: #111827;
    font-family: "Segoe UI";
}
QLabel { background: transparent; }
QPushButton {
    background-color: #F97316;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 10px 16px;
    font-size: 13px;
    font-weight: 700;
}
QPushButton:hover { background-color: #EA580C; }
QPushButton:pressed { background-color: #C2410C; }
QScrollArea { border: none; background: transparent; }
QFrame#headerBar {
    background: white;
    border: 1px solid #D9D9D9;
    border-radius: 4px;
}
QFrame#panelBox {
    background: white;
    border: 1px solid #D9D9D9;
    border-radius: 4px;
}
QFrame#resultCard {
    background: #FCFCFC;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
}
QProgressBar {
    background-color: #E5E7EB;
    border: none;
    border-radius: 8px;
    text-align: center;
    min-height: 18px;
    font-size: 11px;
    font-weight: 700;
    color: #111827;
}
QProgressBar::chunk {
    background-color: #16A34A;
    border-radius: 8px;
}
"""
