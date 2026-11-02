"""
BankFusion UI Component: Navigation Sidebar
===========================================
Left sidebar providing one-click switching between the two primary pages:
1. Fraud Review Queue
2. Transaction Feed
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QFrame, QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Signal
from ui.theme import (
    COLOR_BLUE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED, COLOR_BORDER
)


class NavigationSidebar(QFrame):
    """Sidebar navigation panel for switching main stacked widget pages."""

    # Emits target page index: 0 = Review Queue, 1 = Transaction Feed
    page_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebarPanel")
        self.setFixedWidth(240)

        self._build_sidebar()

    def _build_sidebar(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(12)

        # Brand Title
        brand_lbl = QLabel("🛡️ BankFusion")
        brand_lbl.setStyleSheet(f"""
            font-size: 20px;
            font-weight: 800;
            color: {COLOR_TEXT_PRIMARY};
            background: transparent;
        """)

        sub_lbl = QLabel("Multi-Bank Risk Platform\nDesktop Edition (Qt 6)")
        sub_lbl.setStyleSheet(f"""
            font-size: 11px;
            color: {COLOR_TEXT_MUTED};
            margin-bottom: 20px;
            background: transparent;
        """)

        layout.addWidget(brand_lbl)
        layout.addWidget(sub_lbl)

        # Navigation Buttons
        self.btn_queue = QPushButton("🛡️  Fraud Review Queue")
        self.btn_queue.setObjectName("navButton")
        self.btn_queue.setProperty("active", "true")
        self.btn_queue.clicked.connect(lambda: self._set_active_page(0))

        self.btn_feed = QPushButton("💳  Transaction Feed")
        self.btn_feed.setObjectName("navButton")
        self.btn_feed.setProperty("active", "false")
        self.btn_feed.clicked.connect(lambda: self._set_active_page(1))

        layout.addWidget(self.btn_queue)
        layout.addWidget(self.btn_feed)

        # Spacer pushing status indicator to bottom
        layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # Bottom System Status Card
        status_box = QFrame()
        status_box.setStyleSheet(f"""
            background-color: #0b1120;
            border: 1px solid {COLOR_BORDER};
            border-radius: 6px;
            padding: 10px;
        """)
        s_layout = QVBoxLayout(status_box)
        s_layout.setContentsMargins(6, 6, 6, 6)
        s_layout.setSpacing(4)

        status_title = QLabel("🟢 System Operational")
        status_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #10b981; background: transparent;")

        status_desc = QLabel("SQLite Kimball Warehouse\n4 Deterministic Rules Active")
        status_desc.setStyleSheet(f"font-size: 10px; color: {COLOR_TEXT_MUTED}; background: transparent;")

        s_layout.addWidget(status_title)
        s_layout.addWidget(status_desc)

        layout.addWidget(status_box)

    def _set_active_page(self, page_idx: int):
        self.btn_queue.setProperty("active", "true" if page_idx == 0 else "false")
        self.btn_feed.setProperty("active", "true" if page_idx == 1 else "false")

        # Force style re-evaluation
        self.btn_queue.style().unpolish(self.btn_queue)
        self.btn_queue.style().polish(self.btn_queue)
        self.btn_feed.style().unpolish(self.btn_feed)
        self.btn_feed.style().polish(self.btn_feed)

        self.page_selected.emit(page_idx)

