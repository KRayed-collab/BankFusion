"""
BankFusion UI Component: Summary Cards
======================================
Displays the top three real-time KPI metrics:
1. Awaiting Review (unresolved alerts)
2. Escalated for Investigation
3. Accounts Restricted (simulated)
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt
from ui.theme import (
    COLOR_AMBER, COLOR_BLUE, COLOR_RED,
    COLOR_PANEL_BG, COLOR_BORDER, COLOR_TEXT_SECONDARY, COLOR_TEXT_PRIMARY
)


class SummaryCard(QFrame):
    """Individual KPI metric display card with color accent border."""

    def __init__(self, title: str, accent_color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("summaryCard")
        self.setStyleSheet(f"""
            QFrame#summaryCard {{
                background-color: {COLOR_PANEL_BG};
                border: 1px solid {COLOR_BORDER};
                border-left: 5px solid {accent_color};
                border-radius: 8px;
                padding: 14px 18px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        self.title_label = QLabel(title.upper())
        self.title_label.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 700;
            color: {COLOR_TEXT_SECONDARY};
            letter-spacing: 0.5px;
            background: transparent;
        """)

        self.value_label = QLabel("0")
        self.value_label.setStyleSheet(f"""
            font-size: 26px;
            font-weight: 800;
            color: {COLOR_TEXT_PRIMARY};
            background: transparent;
        """)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, val: int):
        self.value_label.setText(f"{val:,}")


class SummaryCardsPanel(QWidget):
    """Panel holding all three KPI summary cards in a responsive horizontal layout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        self.card_awaiting = SummaryCard("Awaiting Review", COLOR_AMBER, self)
        self.card_escalated = SummaryCard("Escalated for Investigation", COLOR_BLUE, self)
        self.card_restricted = SummaryCard("Accounts Restricted", COLOR_RED, self)

        layout.addWidget(self.card_awaiting)
        layout.addWidget(self.card_escalated)
        layout.addWidget(self.card_restricted)

    def update_metrics(self, awaiting: int, escalated: int, restricted: int):
        self.card_awaiting.set_value(awaiting)
        self.card_escalated.set_value(escalated)
        self.card_restricted.set_value(restricted)

