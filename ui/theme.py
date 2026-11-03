"""
BankFusion Desktop Application Theme & Styling
==============================================
Professional Enterprise Light Theme for Financial Banking Operations & Fraud Investigation.
Features:
- Clean light workspace (#F3F5F7) and single-level white cards (#FFFFFF)
- High-contrast dark slate sidebar (#202C38) with muted teal active indicators (#176B66)
- Strict adherence to preserved fraud status colours:
  * CLEAR / NON-FRAUD: #268653 on #E6F4EA
  * REVIEW_PENDING: #D69E27 on #FFF3D6
  * AUTO_BLOCKED / MANUALLY_BLOCKED: #C43D3D on #FCE8E8
  * RELEASED: #2B6CB0 on #EBF8FF
- High data-density tabular layouts with user-resizable headers
"""

# Palette Constants
COLOR_BG = "#F3F5F7"               # Clean workspace light canvas
COLOR_BG_DARK = COLOR_BG           # Backward compatibility alias
COLOR_CARD_BG = "#FFFFFF"          # Single-level white card container
COLOR_PANEL_BG = "#FFFFFF"         # Main panels
COLOR_PANEL_ALT = "#F8FAFC"        # Sub-panels / table alternating rows

COLOR_SIDEBAR_BG = "#202C38"       # Deep slate enterprise sidebar
COLOR_SIDEBAR_TEXT = "#94A3B8"     # Inactive sidebar navigation text
COLOR_SIDEBAR_ACTIVE = "#176B66"   # Muted teal active navigation indicator
COLOR_SIDEBAR_ACTIVE_TEXT = "#FFFFFF"

COLOR_TEXT_PRIMARY = "#202B36"     # High readability dark charcoal
COLOR_TEXT_SECONDARY = "#64748B"   # Cool grey secondary labels & hints
COLOR_TEXT_MUTED = "#94A3B8"       # Subtle tertiary text

COLOR_BORDER = "#D9E0E7"           # Standard 1px neutral borders
COLOR_BORDER_LIGHT = "#E2E8F0"     # Divider lines
COLOR_BORDER_DARK = "#CBD5E1"      # Interactive borders

COLOR_ACCENT = "#176B66"           # Muted teal primary accent
COLOR_ACCENT_HOVER = "#135652"     # Darker teal hover
COLOR_ACCENT_LIGHT = "#E6F0EF"     # Very soft teal tint for selection

# Preserved Fraud Status Colours (MANDATORY)
COLOR_CLEAR = "#268653"            # CLEAR / NON-FRAUD dark green text
COLOR_CLEAR_BG = "#E6F4EA"         # Light green badge background
COLOR_CLEAR_BORDER = "#A3D9B8"

COLOR_REVIEW = "#D69E27"           # REVIEW_PENDING amber/yellow text
COLOR_REVIEW_BG = "#FFF3D6"        # Light amber badge background
COLOR_REVIEW_BORDER = "#F5D585"

COLOR_BLOCKED = "#C43D3D"          # AUTO_BLOCKED / MANUALLY_BLOCKED red text
COLOR_BLOCKED_BG = "#FCE8E8"       # Light red badge background
COLOR_BLOCKED_BORDER = "#F4AAAA"

COLOR_RELEASED = "#2B6CB0"         # RELEASED muted blue-grey text
COLOR_RELEASED_BG = "#EBF8FF"      # Light blue-grey badge background
COLOR_RELEASED_BORDER = "#BEE3F8"

# Compatibility Aliases for Existing Pages & Workers
COLOR_GREEN = COLOR_CLEAR
COLOR_GREEN_BG = COLOR_CLEAR_BG
COLOR_GREEN_BORDER = COLOR_CLEAR_BORDER

COLOR_AMBER = COLOR_REVIEW
COLOR_AMBER_BG = COLOR_REVIEW_BG
COLOR_AMBER_BORDER = COLOR_REVIEW_BORDER

COLOR_RED = COLOR_BLOCKED
COLOR_RED_BG = COLOR_BLOCKED_BG
COLOR_RED_BORDER = COLOR_BLOCKED_BORDER

COLOR_BLUE = COLOR_RELEASED
COLOR_BLUE_BG = COLOR_RELEASED_BG
COLOR_BLUE_BORDER = COLOR_RELEASED_BORDER
COLOR_BLUE_HOVER = "#1A4971"

# Enterprise Light Theme QSS
ENTERPRISE_LIGHT_THEME_QSS = f"""
QMainWindow {{
    background-color: {COLOR_BG};
    color: {COLOR_TEXT_PRIMARY};
}}

QWidget {{
    background-color: {COLOR_BG};
    color: {COLOR_TEXT_PRIMARY};
    font-family: "Segoe UI", "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 13px;
}}

/* Scrollbars */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {COLOR_BORDER_DARK};
    min-height: 24px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLOR_TEXT_SECONDARY};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {COLOR_BORDER_DARK};
    min-width: 24px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {COLOR_TEXT_SECONDARY};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* Sidebar Panel */
QFrame#sidebarPanel {{
    background-color: {COLOR_SIDEBAR_BG};
    border-right: 1px solid #1E2833;
}}

/* Cards & KPI Panels */
QFrame#summaryCard, QFrame#kpiCard {{
    background-color: {COLOR_CARD_BG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 12px;
}}

QFrame#alertCard {{
    background-color: {COLOR_CARD_BG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
}}
QFrame#alertCard:hover {{
    border-color: {COLOR_BORDER_DARK};
    background-color: #FAFCFE;
}}

QFrame#filterPanel {{
    background-color: {COLOR_CARD_BG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 8px 12px;
}}

/* Buttons */
QPushButton {{
    background-color: #FFFFFF;
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
    font-size: 12px;
}}
QPushButton:hover {{
    background-color: #F8FAFC;
    border-color: {COLOR_BORDER_DARK};
}}
QPushButton:pressed {{
    background-color: #EEF2F6;
}}
QPushButton:disabled {{
    background-color: #F1F5F9;
    color: {COLOR_TEXT_MUTED};
    border-color: {COLOR_BORDER};
}}

/* Primary Muted Teal Action Button */
QPushButton#primaryButton {{
    background-color: {COLOR_ACCENT};
    border: 1px solid {COLOR_ACCENT_HOVER};
    color: #FFFFFF;
}}
QPushButton#primaryButton:hover {{
    background-color: {COLOR_ACCENT_HOVER};
    border-color: #0E4340;
}}
QPushButton#primaryButton:pressed {{
    background-color: #0E4340;
}}

/* Secondary Neutral Outline Button */
QPushButton#secondaryButton {{
    background-color: #FFFFFF;
    border: 1px solid {COLOR_BORDER};
    color: {COLOR_TEXT_PRIMARY};
}}
QPushButton#secondaryButton:hover {{
    background-color: #F8FAFC;
    border-color: {COLOR_BORDER_DARK};
}}

/* Semantic Action Buttons */
QPushButton#successButton {{
    background-color: {COLOR_CLEAR};
    border: 1px solid #1E6B42;
    color: #FFFFFF;
}}
QPushButton#successButton:hover {{
    background-color: #1E6B42;
}}

QPushButton#dangerButton {{
    background-color: {COLOR_BLOCKED};
    border: 1px solid #A83232;
    color: #FFFFFF;
}}
QPushButton#dangerButton:hover {{
    background-color: #A83232;
}}

QPushButton#warningButton {{
    background-color: {COLOR_REVIEW};
    border: 1px solid #B8851E;
    color: #FFFFFF;
}}
QPushButton#warningButton:hover {{
    background-color: #B8851E;
}}

/* Navigation Sidebar Buttons */
QPushButton#navButton {{
    background-color: transparent;
    color: {COLOR_SIDEBAR_TEXT};
    border: none;
    border-radius: 6px;
    text-align: left;
    padding: 10px 14px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#navButton:hover {{
    background-color: #2A3744;
    color: #FFFFFF;
}}
QPushButton#navButton[active="true"] {{
    background-color: {COLOR_ACCENT};
    color: #FFFFFF;
    border-left: 4px solid #34D399;
    font-weight: 700;
}}

/* Form Controls */
QLineEdit, QComboBox, QSpinBox {{
    background-color: #FFFFFF;
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
    selection-background-color: {COLOR_ACCENT_LIGHT};
    selection-color: {COLOR_ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {COLOR_ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: #FFFFFF;
    color: {COLOR_TEXT_PRIMARY};
    selection-background-color: {COLOR_ACCENT_LIGHT};
    selection-color: {COLOR_ACCENT};
    border: 1px solid {COLOR_BORDER};
    padding: 4px;
}}

/* Tables */
QTableWidget, QTableView {{
    background-color: #FFFFFF;
    alternate-background-color: #F8FAFC;
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    gridline-color: #EDF2F7;
    color: {COLOR_TEXT_PRIMARY};
    selection-background-color: {COLOR_ACCENT_LIGHT};
    selection-color: {COLOR_TEXT_PRIMARY};
    font-size: 12px;
}}
QTableWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid #EDF2F7;
}}
QHeaderView::section {{
    background-color: #F1F5F9;
    color: {COLOR_TEXT_SECONDARY};
    font-weight: 700;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid {COLOR_BORDER};
}}

/* Tab Bar */
QTabWidget::pane {{
    border: none;
    background-color: transparent;
}}
QTabBar::tab {{
    background-color: #E2E8F0;
    color: {COLOR_TEXT_SECONDARY};
    padding: 8px 18px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 600;
    font-size: 12px;
}}
QTabBar::tab:selected {{
    background-color: #FFFFFF;
    color: {COLOR_ACCENT};
    border: 1px solid {COLOR_BORDER};
    border-bottom: none;
}}
QTabBar::tab:hover:!selected {{
    background-color: #CBD5E1;
    color: {COLOR_TEXT_PRIMARY};
}}

/* Dialogs */
QDialog {{
    background-color: {COLOR_BG};
    border: 1px solid {COLOR_BORDER};
}}

/* Sliders */
QSlider::groove:horizontal {{
    height: 6px;
    background: {COLOR_BORDER};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {COLOR_ACCENT};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: #FFFFFF;
    border: 1px solid {COLOR_ACCENT};
    width: 14px;
    margin-top: -4px;
    margin-bottom: -4px;
    border-radius: 7px;
}}
"""

# Alias for backward compatibility
DARK_THEME_QSS = ENTERPRISE_LIGHT_THEME_QSS
