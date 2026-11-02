"""
BankFusion Desktop Application Theme & Styling
==============================================
Dark charcoal banking-security theme inspired by modern SIEM and fraud triage dashboards.
Pure Qt stylesheets (QSS) for native PySide6 widgets.
"""

# Palette Constants
COLOR_BG_DARK = "#0b0f19"         # Deep charcoal canvas
COLOR_PANEL_BG = "#131b2e"        # Panel and card background
COLOR_PANEL_ALT = "#1a243b"       # Alternate row / card hover
COLOR_BORDER = "#232f48"          # Subtle structural borders
COLOR_BORDER_LIGHT = "#334155"    # Highlight borders

COLOR_TEXT_PRIMARY = "#f8fafc"    # High-contrast white
COLOR_TEXT_SECONDARY = "#94a3b8"  # Slate secondary text
COLOR_TEXT_MUTED = "#64748b"      # Muted labels

COLOR_RED = "#ef4444"             # Suspicious / high risk
COLOR_RED_BG = "#3f141b"          # Red badge / row background
COLOR_RED_BORDER = "#7f1d1d"

COLOR_GREEN = "#10b981"           # Clean / legitimate / normal
COLOR_GREEN_BG = "#0c2d23"        # Green badge / row background
COLOR_GREEN_BORDER = "#065f46"

COLOR_AMBER = "#f59e0b"           # Awaiting review / medium risk
COLOR_AMBER_BG = "#38230b"        # Amber badge / row background
COLOR_AMBER_BORDER = "#78350f"

COLOR_BLUE = "#3b82f6"            # Interactive cyan/blue
COLOR_BLUE_HOVER = "#2563eb"
COLOR_BLUE_BG = "#13233f"
COLOR_BLUE_BORDER = "#1d4ed8"

DARK_THEME_QSS = f"""
QMainWindow {{
    background-color: {COLOR_BG_DARK};
    color: {COLOR_TEXT_PRIMARY};
}}

QWidget {{
    background-color: {COLOR_BG_DARK};
    color: {COLOR_TEXT_PRIMARY};
    font-family: "Segoe UI", "Inter", -apple-system, sans-serif;
    font-size: 13px;
}}

/* Scrollbars */
QScrollBar:vertical {{
    background: {COLOR_BG_DARK};
    width: 10px;
    margin: 0px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {COLOR_BORDER_LIGHT};
    min-height: 24px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLOR_BLUE};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: {COLOR_BG_DARK};
    height: 10px;
    margin: 0px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal {{
    background: {COLOR_BORDER_LIGHT};
    min-width: 24px;
    border-radius: 5px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* Frames & Panels */
QFrame#sidebarPanel {{
    background-color: #0d1424;
    border-right: 1px solid {COLOR_BORDER};
}}
QFrame#summaryCard {{
    background-color: {COLOR_PANEL_BG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 12px;
}}
QFrame#alertCard {{
    background-color: {COLOR_PANEL_BG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}
QFrame#alertCard:hover {{
    border-color: {COLOR_BORDER_LIGHT};
    background-color: {COLOR_PANEL_ALT};
}}
QFrame#filterPanel {{
    background-color: {COLOR_PANEL_BG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 8px;
}}

/* Buttons */
QPushButton {{
    background-color: #1e293b;
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER_LIGHT};
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: #334155;
    border-color: #475569;
}}
QPushButton:pressed {{
    background-color: #0f172a;
}}
QPushButton:disabled {{
    background-color: #1a202c;
    color: #475569;
    border-color: #2d3748;
}}

/* Primary Blue Action Button */
QPushButton#primaryButton {{
    background-color: {COLOR_BLUE};
    border-color: {COLOR_BLUE_BORDER};
    color: #ffffff;
}}
QPushButton#primaryButton:hover {{
    background-color: {COLOR_BLUE_HOVER};
}}

/* Success Button */
QPushButton#successButton {{
    background-color: #059669;
    border-color: #047857;
    color: #ffffff;
}}
QPushButton#successButton:hover {{
    background-color: #10b981;
}}

/* Danger Button */
QPushButton#dangerButton {{
    background-color: #dc2626;
    border-color: #b91c1c;
    color: #ffffff;
}}
QPushButton#dangerButton:hover {{
    background-color: #ef4444;
}}

/* Warning / Amber Button */
QPushButton#warningButton {{
    background-color: #d97706;
    border-color: #b45309;
    color: #ffffff;
}}
QPushButton#warningButton:hover {{
    background-color: #f59e0b;
}}

/* Navigation Sidebar Buttons */
QPushButton#navButton {{
    background-color: transparent;
    color: {COLOR_TEXT_SECONDARY};
    border: none;
    border-radius: 6px;
    text-align: left;
    padding: 12px 16px;
    font-size: 14px;
    font-weight: 600;
}}
QPushButton#navButton:hover {{
    background-color: #1e293b;
    color: {COLOR_TEXT_PRIMARY};
}}
QPushButton#navButton[active="true"] {{
    background-color: #1e3a8a;
    color: #60a5fa;
    border-left: 4px solid {COLOR_BLUE};
}}

/* Inputs, Combos & SpinBoxes */
QLineEdit, QComboBox, QSpinBox {{
    background-color: #0f172a;
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 6px 12px;
    selection-background-color: {COLOR_BLUE};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {COLOR_BLUE};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: #1e293b;
    color: {COLOR_TEXT_PRIMARY};
    selection-background-color: {COLOR_BLUE};
    border: 1px solid {COLOR_BORDER};
    padding: 4px;
}}

/* Table Views */
QTableWidget, QTableView {{
    background-color: {COLOR_PANEL_BG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    gridline-color: {COLOR_BORDER};
    color: {COLOR_TEXT_PRIMARY};
    selection-background-color: {COLOR_BLUE_BG};
    selection-color: {COLOR_TEXT_PRIMARY};
}}
QTableWidget::item {{
    padding: 6px 10px;
    border-bottom: 1px solid {COLOR_BORDER};
}}
QHeaderView::section {{
    background-color: #0d1424;
    color: {COLOR_TEXT_MUTED};
    font-weight: 700;
    font-size: 11px;
    text-transform: uppercase;
    padding: 8px 10px;
    border: none;
    border-bottom: 2px solid {COLOR_BORDER};
}}

/* Tabs */
QTabWidget::pane {{
    border: none;
    background-color: transparent;
}}
QTabBar::tab {{
    background-color: #1e293b;
    color: {COLOR_TEXT_SECONDARY};
    padding: 9px 20px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    background-color: {COLOR_BLUE};
    color: #ffffff;
}}
QTabBar::tab:hover:!selected {{
    background-color: #334155;
    color: {COLOR_TEXT_PRIMARY};
}}

/* Dialogs */
QDialog {{
    background-color: {COLOR_BG_DARK};
    border: 1px solid {COLOR_BORDER_LIGHT};
}}

/* Sliders */
QSlider::groove:horizontal {{
    height: 6px;
    background: {COLOR_BORDER_LIGHT};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {COLOR_BLUE};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: #ffffff;
    border: 1px solid {COLOR_BLUE};
    width: 14px;
    margin-top: -4px;
    margin-bottom: -4px;
    border-radius: 7px;
}}
"""

