"""
BankFusion Desktop Application: Main Window
===========================================
Primary QMainWindow hosting the NavigationSidebar and QStackedWidget
with exactly TWO main operational pages:
1. Fraud Review Queue
2. Transaction Feed
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QStackedWidget
)
from PySide6.QtCore import Qt

from ui.navigation_sidebar import NavigationSidebar
from ui.fraud_review_page import FraudReviewPage
from ui.transaction_feed_page import TransactionFeedPage
from ui.auto_blocked_page import AutoBlockedPage
from ui.theme import ENTERPRISE_LIGHT_THEME_QSS


class MainWindow(QMainWindow):
    """Main desktop application window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BankFusion — Enterprise Fraud & Risk Operations")
        self.resize(1366, 768)
        self.setMinimumSize(1080, 680)

        # Apply professional enterprise light theme styling
        self.setStyleSheet(ENTERPRISE_LIGHT_THEME_QSS)

        self._build_main_ui()

    def _build_main_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left Navigation Sidebar
        self.sidebar = NavigationSidebar(self)
        main_layout.addWidget(self.sidebar)

        # Right Stacked Widget for Pages
        self.stack = QStackedWidget(self)

        # Page 0: Fraud Review Queue
        self.page_queue = FraudReviewPage(self)
        self.stack.addWidget(self.page_queue)

        # Page 1: Transaction Feed
        self.page_feed = TransactionFeedPage(self)
        self.stack.addWidget(self.page_feed)

        # Page 2: Automatically Blocked Transactions
        self.page_blocked = AutoBlockedPage(self)
        self.stack.addWidget(self.page_blocked)

        main_layout.addWidget(self.stack)

        # Connect inter-page refresh triggers
        self.page_queue.screening_completed.connect(self.page_feed.mark_dirty)
        self.page_queue.screening_completed.connect(self.page_blocked.refresh_data)
        self.page_feed.screening_completed.connect(self.page_blocked.refresh_data)
        self.page_feed.screening_completed.connect(self.page_queue.refresh_queue)
        self.page_blocked.block_released.connect(self.page_feed.mark_dirty)
        self.page_blocked.block_released.connect(self.page_queue.refresh_queue)

        # Connect navigation signal
        self.sidebar.page_selected.connect(self._on_navigate)

    def _on_navigate(self, page_index: int):
        self.stack.setCurrentIndex(page_index)
        # Refresh target page data on navigation
        if page_index == 0:
            self.page_queue.refresh_queue()
        elif page_index == 1:
            self.page_feed.load_feed_data()
        elif page_index == 2:
            self.page_blocked.refresh_data()

    def closeEvent(self, event):
        """Cleanly halts background timers and workers upon window exit."""
        if hasattr(self.page_feed, "stop_all_workers"):
            self.page_feed.stop_all_workers()
        if hasattr(self.page_queue, "detection_worker") and self.page_queue.detection_worker:
            if self.page_queue.detection_worker.isRunning():
                self.page_queue.detection_worker.wait(2000)
        event.accept()

