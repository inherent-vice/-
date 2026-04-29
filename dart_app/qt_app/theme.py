from __future__ import annotations

COLORS = {
    "canvas": "#faf9f5",
    "surface_soft": "#f5f0e8",
    "surface_card": "#efe9de",
    "surface_cream_strong": "#e8e0d2",
    "surface_dark": "#181715",
    "surface_dark_elevated": "#252320",
    "surface_dark_soft": "#1f1e1b",
    "hairline": "#e6dfd8",
    "hairline_soft": "#ebe6df",
    "primary": "#cc785c",
    "primary_active": "#a9583e",
    "primary_disabled": "#e6dfd8",
    "ink": "#141413",
    "body": "#3d3d3a",
    "muted": "#6c6a64",
    "muted_soft": "#8e8b82",
    "on_primary": "#ffffff",
    "on_dark": "#faf9f5",
    "on_dark_soft": "#a09d96",
    "success": "#5db872",
    "warning": "#d4a017",
    "error": "#c64545",
}

FONT_BODY = '"Malgun Gothic", "Segoe UI", Arial, sans-serif'
FONT_DISPLAY = 'Georgia, Cambria, "Malgun Gothic", serif'
FONT_MONO = '"Cascadia Mono", Consolas, monospace'


def app_stylesheet():
    c = COLORS
    return f"""
    QWidget {{
        background: {c["canvas"]};
        color: {c["body"]};
        font-family: {FONT_BODY};
        font-size: 10.5pt;
    }}
    QMainWindow {{
        background: {c["canvas"]};
    }}
    QScrollArea#LeftRailScroll {{
        background: transparent;
        border: none;
    }}
    QScrollArea#LeftRailScroll > QWidget > QWidget {{
        background: transparent;
    }}
    #AppBar {{
        background: {c["canvas"]};
        border-bottom: 1px solid {c["hairline"]};
    }}
    #BrandTitle {{
        color: {c["ink"]};
        font-family: {FONT_DISPLAY};
        font-size: 24px;
        font-weight: 400;
    }}
    #SubtleText, QLabel[role="muted"] {{
        color: {c["muted"]};
    }}
    #SectionTitle {{
        background: transparent;
        color: {c["ink"]};
        font-weight: 600;
    }}
    #LeftRail, #Inspector, #TableFrame {{
        background: {c["surface_card"]};
        border: 1px solid {c["hairline"]};
        border-radius: 12px;
    }}
    #AdvancedPanel {{
        background: {c["surface_soft"]};
        border: 1px solid {c["hairline"]};
        border-radius: 10px;
    }}
    #DarkPanel {{
        background: {c["surface_dark"]};
        border: 1px solid {c["surface_dark_elevated"]};
        border-radius: 12px;
    }}
    #DarkPanel QLabel {{
        background: transparent;
        color: {c["on_dark"]};
    }}
    #DarkPanel QTextEdit {{
        background: {c["surface_dark_soft"]};
        color: {c["on_dark"]};
        border: 1px solid {c["surface_dark_elevated"]};
        border-radius: 8px;
        font-family: {FONT_MONO};
        font-size: 10pt;
        selection-background-color: {c["primary_active"]};
    }}
    QTextEdit, QLineEdit, QSpinBox, QDoubleSpinBox {{
        background: {c["canvas"]};
        color: {c["ink"]};
        border: 1px solid {c["hairline"]};
        border-radius: 8px;
        padding: 8px 10px;
        selection-background-color: {c["surface_cream_strong"]};
    }}
    QTextEdit:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {c["primary"]};
    }}
    QPushButton {{
        min-height: 36px;
        padding: 8px 16px;
        border-radius: 8px;
        border: 1px solid {c["hairline"]};
        background: {c["canvas"]};
        color: {c["ink"]};
        font-weight: 500;
    }}
    QPushButton:pressed {{
        background: {c["surface_cream_strong"]};
    }}
    QPushButton:disabled {{
        color: {c["muted_soft"]};
        background: {c["surface_soft"]};
    }}
    QPushButton#PrimaryButton {{
        background: {c["primary"]};
        border: 1px solid {c["primary"]};
        color: {c["on_primary"]};
    }}
    QPushButton#PrimaryButton:pressed {{
        background: {c["primary_active"]};
        border-color: {c["primary_active"]};
    }}
    QPushButton#PrimaryButton:disabled {{
        color: {c["muted_soft"]};
        background: {c["primary_disabled"]};
        border-color: {c["primary_disabled"]};
    }}
    QPushButton#DangerButton {{
        color: {c["error"]};
        border-color: {c["error"]};
    }}
    QPushButton#DangerButton:disabled {{
        color: {c["muted_soft"]};
        background: {c["surface_soft"]};
        border-color: {c["hairline"]};
    }}
    QCheckBox {{
        color: {c["body"]};
        spacing: 8px;
    }}
    QComboBox {{
        min-height: 34px;
        padding: 4px 10px;
        border: 1px solid {c["hairline"]};
        border-radius: 8px;
        background: {c["canvas"]};
    }}
    QTableView, QTableWidget {{
        background: {c["canvas"]};
        alternate-background-color: {c["surface_soft"]};
        color: {c["body"]};
        gridline-color: {c["hairline_soft"]};
        border: none;
        selection-background-color: {c["surface_cream_strong"]};
        selection-color: {c["ink"]};
    }}
    QHeaderView::section {{
        background: {c["surface_card"]};
        color: {c["muted"]};
        border: none;
        border-bottom: 1px solid {c["hairline"]};
        padding: 8px 10px;
        font-weight: 500;
    }}
    QTabWidget::pane {{
        border: none;
        background: transparent;
    }}
    QTabBar::tab {{
        padding: 8px 14px;
        margin-right: 6px;
        border-radius: 8px;
        color: {c["muted"]};
        background: transparent;
    }}
    QTabBar::tab:selected {{
        background: {c["surface_cream_strong"]};
        color: {c["ink"]};
    }}
    QProgressBar {{
        border: 1px solid {c["hairline"]};
        border-radius: 8px;
        background: {c["surface_soft"]};
        min-height: 22px;
        text-align: center;
        color: {c["body"]};
        font-weight: 500;
    }}
    QProgressBar::chunk {{
        border-radius: 8px;
        background: {c["primary"]};
    }}
    """
