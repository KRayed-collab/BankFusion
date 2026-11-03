"""
BankFusion UI Component: Summary Cards
======================================
Displays the top three real-time operational KPI metrics:
1. Awaiting Review (unresolved alerts requiring operator triage)
2. Escalated for Investigation (transferred to senior compliance)
3. Resolved Alerts (triaged as legitimate or confirmed suspicious)

Enterprise design: Single-level white cards (#FFFFFF) with neutral borders (#D9E0E7)
and purposeful semantic accent indicators.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt
from ui.theme import (
    COLOR_CARD_BG, COLOR_BORDER, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED, COLOR_AMBER, COLOR_BLUE, COLOR_GREEN
)


class SummaryCard(QFrame):
    """Individual KPI metric display card with color accent border."""

    def __init__(self, title: str, subtitle: str, accent_color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("summaryCard")
        self.setStyleSheet(f"""
            QFrame#summaryCard {{
                background-color: {COLOR_CARD_BG};
                border: 1px solid {COLOR_BORDER};
                border-left: 4px solid {accent_color};
                border-radius: 6px;
                padding: 12px 16px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

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
            font-size: 24px;
            font-weight: 800;
            color: {COLOR_TEXT_PRIMARY};
            background: transparent;
        """)

        self.sub_label = QLabel(subtitle)
        self.sub_label.setStyleSheet(f"""
            font-size: 11px;
            color: {COLOR_TEXT_MUTED};
            background: transparent;
        """)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.sub_label)

    def set_value(self, val: int):
        self.value_label.setText(f"{val:,}")


class SummaryCardsPanel(QWidget):
    """Panel holding all three KPI summary cards in a responsive horizontal layout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.card_awaiting = SummaryCard(
            "Awaiting Review",
            "Unresolved tier-2 alerts requiring triage",
            COLOR_AMBER,
            self
        )
        self.card_escalated = SummaryCard(
            "Escalated Investigation",
            "Under senior compliance & audit review",
            COLOR_BLUE,
            self
        )
        self.card_resolved = SummaryCard(
            "Resolved Alerts",
            "Manually triaged or legitimate",
            COLOR_GREEN,
            self
        )
        # Compatibility alias for existing tests / legacy code
        self.card_restricted = self.card_resolved

        layout.addWidget(self.card_awaiting)
        layout.addWidget(self.card_escalated)
        layout.addWidget(self.card_resolved)

    def update_metrics(self, awaiting: int = 0, escalated: int = 0, resolved: int = 0, restricted: int = 0):
        self.card_awaiting.set_value(awaiting)
        self.card_escalated.set_value(escalated)
        val_third = resolved if resolved > 0 else restricted
        self.card_resolved.set_value(val_third)
