from PyQt5.QtWidgets import QLabel, QFrame, QSizePolicy


def status_color(status):
    return "#DC2626" if "Pothole detected" in status else "#15803D"


def damage_level_color(level):
    mapping = {
        "Very Low": "#15803D",
        "Low": "#3B82F6",
        "Medium": "#D97706",
        "High": "#EA580C",
        "Severe": "#DC2626",
    }
    return mapping.get(level, "#334155")


def make_chip(text, bg="#EEF2FF", fg="#1E3A8A"):
    chip = QLabel(text)
    chip.setStyleSheet(f"""
        QLabel {{
            background: {bg};
            color: {fg};
            border: 1px solid rgba(0,0,0,0.08);
            border-radius: 12px;
            padding: 7px 12px;
            font-size: 12px;
            font-weight: 600;
        }}
    """)
    return chip


def create_card():
    card = QFrame()
    card.setObjectName("resultCard")
    card.setFrameShape(QFrame.StyledPanel)
    card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
    return card
