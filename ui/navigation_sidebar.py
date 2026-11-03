"""
BankFusion UI Component: Navigation Sidebar
===========================================
Left sidebar providing switching between operational pages:
1. Fraud Review Queue
2. Transaction Feed
3. Automatically Blocked
Styled with dark slate palette (#202C38), clean typography, and muted teal accents.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QFrame, QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Signal
from ui.theme import (
    COLOR_SIDEBAR_BG, COLOR_SIDEBAR_TEXT, COLOR_SIDEBAR_ACTIVE,
    COLOR_SIDEBAR_ACTIVE_TEXT, COLOR_TEXT_MUTED
)


class NavigationSidebar(QFrame):
    """Sidebar navigation panel with enterprise dark slate aesthetic."""

    page_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebarPanel")
        self.setFixedWidth(240)
        self._build_sidebar()

    def _build_sidebar(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(8)

        # Brand Title & Subtitle
        brand_lbl = QLabel("🛡 BankFusion")
        brand_lbl.setStyleSheet("""
            font-size: 19px;
            font-weight: 800;
            color: #FFFFFF;
            letter-spacing: 0.5px;
            background: transparent;
        """)

        sub_lbl = QLabel("Enterprise Fraud & Risk Operations")
        sub_lbl.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 500;
            color: {COLOR_SIDEBAR_TEXT};
            margin-bottom: 16px;
            background: transparent;
        """)

        layout.addWidget(brand_lbl)
        layout.addWidget(sub_lbl)

        # Navigation Section Header
        nav_header = QLabel("OPERATIONAL CONSOLE")
        nav_header.setStyleSheet("""
            font-size: 10px;
            font-weight: 700;
            color: #64748B;
            letter-spacing: 0.8px;
            margin-top: 8px;
            margin-bottom: 4px;
            background: transparent;
        """)
        layout.addWidget(nav_header)

        # Navigation Buttons
        self.btn_queue = QPushButton("🛡  Fraud Review Queue")
        self.btn_queue.setObjectName("navButton")
        self.btn_queue.setProperty("active", "true")
        self.btn_queue.clicked.connect(lambda: self._set_active_page(0))

        self.btn_feed = QPushButton("💳  Transaction Feed")
        self.btn_feed.setObjectName("navButton")
        self.btn_feed.setProperty("active", "false")
        self.btn_feed.clicked.connect(lambda: self._set_active_page(1))

        self.btn_blocked = QPushButton("🚫  Automatically Blocked")
        self.btn_blocked.setObjectName("navButton")
        self.btn_blocked.setProperty("active", "false")
        self.btn_blocked.clicked.connect(lambda: self._set_active_page(2))

        layout.addWidget(self.btn_queue)
        layout.addWidget(self.btn_feed)
        layout.addWidget(self.btn_blocked)

        # Spacer
        layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # Bottom System Status Card
        status_box = QFrame()
        status_box.setStyleSheet("""
            background-color: #17222C;
            border: 1px solid #283747;
            border-radius: 6px;
            padding: 8px 10px;
        """)
        s_layout = QVBoxLayout(status_box)
        s_layout.setContentsMargins(4, 4, 4, 4)
        s_layout.setSpacing(3)

        status_title = QLabel("● System Operational")
        status_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #34D399; background: transparent;")

        status_desc = QLabel("SQLite Kimball Warehouse\n4 Detection Rules Active")
        status_desc.setStyleSheet(f"font-size: 10px; color: {COLOR_SIDEBAR_TEXT}; line-height: 1.3; background: transparent;")

        s_layout.addWidget(status_title)
        s_layout.addWidget(status_desc)
        layout.addWidget(status_box)

    def _set_active_page(self, page_idx: int):
        self.btn_queue.setProperty("active", "true" if page_idx == 0 else "false")
        self.btn_feed.setProperty("active", "true" if page_idx == 1 else "false")
        self.btn_blocked.setProperty("active", "true" if page_idx == 2 else "false")

        # Force style re-evaluation
        for btn in (self.btn_queue, self.btn_feed, self.btn_blocked):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self.page_selected.emit(page_idx)
