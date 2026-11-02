"""
BankFusion Dialog: Alert Evidence & Audit Trail
===============================================
Native Qt QDialog presenting full investigator evidence, interbank routing,
and case action controls for a selected fraud alert.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QTextEdit, QMessageBox
)
from PySide6.QtCore import Qt, Signal
from ui.theme import (
    COLOR_PANEL_BG, COLOR_BORDER, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED, COLOR_BLUE, COLOR_RED, COLOR_AMBER, COLOR_GREEN
)


class AlertDetailsDialog(QDialog):
    """Deep inspection dialog for fraud screening warnings and entity evidence."""

    # Signal emitted when investigator takes an action: (alert_id, new_status, notes, account_ref, bank_code)
    action_submitted = Signal(str, str, str, str, str)

    def __init__(self, alert_data: dict, parent=None):
        super().__init__(parent)
        self.alert_data = alert_data
        self.setWindowTitle(f"Alert Investigation — {alert_data.get('alert_id', 'ALT')}")
        self.resize(750, 620)
        self.setModal(True)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Header: Alert ID, Priority, Status
        hdr_layout = QHBoxLayout()
        title_label = QLabel(f"Investigation File: {self.alert_data.get('alert_id', 'ALT')}")
        title_label.setStyleSheet("font-size: 20px; font-weight: 800; color: #f8fafc;")

        prio = self.alert_data.get("review_priority", "MEDIUM")
        prio_color = COLOR_RED if prio == "HIGH" else (COLOR_AMBER if prio == "MEDIUM" else COLOR_BLUE)
        prio_badge = QLabel(f" {prio} PRIORITY ")
        prio_badge.setStyleSheet(f"""
            background-color: {prio_color};
            color: #ffffff;
            font-weight: 700;
            font-size: 11px;
            padding: 4px 10px;
            border-radius: 4px;
        """)

        status_str = self.alert_data.get("review_status", "NEEDS_REVIEW").replace("_", " ")
        status_badge = QLabel(f" {status_str} ")
        status_badge.setStyleSheet("""
            background-color: #1e293b;
            color: #94a3b8;
            font-weight: 700;
            font-size: 11px;
            padding: 4px 10px;
            border-radius: 4px;
            border: 1px solid #334155;
        """)

        hdr_layout.addWidget(title_label)
        hdr_layout.addStretch()
        hdr_layout.addWidget(prio_badge)
        hdr_layout.addWidget(status_badge)
        layout.addLayout(hdr_layout)

        # Metadata Grid Frame
        grid_frame = QFrame()
        grid_frame.setStyleSheet(f"""
            background-color: {COLOR_PANEL_BG};
            border: 1px solid {COLOR_BORDER};
            border-radius: 8px;
            padding: 14px;
        """)
        grid = QGridLayout(grid_frame)
        grid.setSpacing(12)

        amt_paise = self.alert_data.get("amount_paise") or 0
        amt_inr = f"₹{amt_paise / 100:,.2f}" if amt_paise else "N/A"

        items = [
            ("Originating Bank:", self.alert_data.get("originating_bank") or "UNKNOWN"),
            ("Sender Account:", self.alert_data.get("sender_account_ref") or self.alert_data.get("entity_ref", "N/A")),
            ("Destination Bank:", self.alert_data.get("destination_bank") or "INTERBANK"),
            ("Receiver Account:", self.alert_data.get("receiver_account_ref") or "VARIOUS"),
            ("Monetary Amount:", f"{amt_inr} ({amt_paise:,} paise)"),
            ("Payment Method:", f"{self.alert_data.get('payment_method') or 'N/A'} • {self.alert_data.get('transaction_status') or 'SETTLED'}"),
            ("Device Token:", self.alert_data.get("device_token") or "UNKNOWN_DEVICE"),
            ("Detection Run ID:", self.alert_data.get("detection_run_id") or "N/A"),
            ("Trigger Timestamp:", self.alert_data.get("trigger_timestamp") or "N/A"),
            ("Window Interval:", f"{self.alert_data.get('window_start') or 'N/A'} → {self.alert_data.get('window_end') or 'N/A'}"),
            ("Threshold Value:", str(self.alert_data.get("threshold_value", "N/A"))),
            ("Observed Metric:", str(self.alert_data.get("observed_value", "N/A"))),
        ]

        row, col = 0, 0
        for label, val in items:
            lbl_widget = QLabel(label)
            lbl_widget.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-weight: 600; font-size: 11px;")
            val_widget = QLabel(str(val))
            val_widget.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-weight: 700; font-size: 12px;")
            val_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)

            grid.addWidget(lbl_widget, row, col)
            grid.addWidget(val_widget, row, col + 1)
            col += 2
            if col >= 4:
                col = 0
                row += 1

        layout.addWidget(grid_frame)

        # Evidence Box
        ev_title = QLabel("DETECTION EVIDENCE & REASONING")
        ev_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8;")
        layout.addWidget(ev_title)

        ev_box = QTextEdit()
        ev_box.setReadOnly(True)
        rules_str = self.alert_data.get("rules_triggered") or self.alert_data.get("rule_name", "UNKNOWN")
        summary_text = (
            f"TRIGGERED RULES: {rules_str}\n\n"
            f"EVIDENCE SUMMARY:\n{self.alert_data.get('evidence_summary', 'No summary provided.')}\n\n"
        )
        if self.alert_data.get("linked_route_summary"):
            summary_text += f"INTERBANK ROUTE CHAIN:\n{self.alert_data.get('linked_route_summary')}\n\n"
        if self.alert_data.get("linked_transaction_ids"):
            summary_text += f"ASSOCIATED TRANSACTION KEYS:\n{self.alert_data.get('linked_transaction_ids')}\n\n"
        if self.alert_data.get("review_notes"):
            summary_text += f"PREVIOUS INVESTIGATOR NOTES:\n{self.alert_data.get('review_notes')}\n"

        ev_box.setPlainText(summary_text)
        ev_box.setStyleSheet(f"""
            background-color: #0d1424;
            color: #e2e8f0;
            border: 1px solid {COLOR_BORDER};
            border-radius: 6px;
            padding: 10px;
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 12px;
        """)
        layout.addWidget(ev_box)

        # Investigator Actions Section
        action_title = QLabel("INVESTIGATOR TRIAGE ACTIONS")
        action_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8;")
        layout.addWidget(action_title)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_legit = QPushButton("✅ Mark as Legitimate")
        self.btn_legit.setObjectName("successButton")
        self.btn_legit.clicked.connect(lambda: self._on_action("LEGITIMATE", "Verified by investigator as benign traffic."))

        self.btn_susp = QPushButton("🚨 Confirm as Suspicious")
        self.btn_susp.setObjectName("dangerButton")
        self.btn_susp.clicked.connect(lambda: self._on_action("SUSPICIOUS", "Confirmed suspicious by triage officer."))

        self.btn_escalate = QPushButton("⚠️ Escalate Case")
        self.btn_escalate.setObjectName("warningButton")
        self.btn_escalate.clicked.connect(lambda: self._on_action("ESCALATED", "Escalated for senior compliance review."))

        self.btn_restrict = QPushButton("🔒 Restrict Account")
        self.btn_restrict.setStyleSheet("background-color: #831843; color: #ffffff; font-weight: 700;")
        self.btn_restrict.clicked.connect(lambda: self._on_action("ACCOUNT_RESTRICTED", "Simulated restriction placed."))

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_legit)
        btn_layout.addWidget(self.btn_susp)
        btn_layout.addWidget(self.btn_escalate)
        btn_layout.addWidget(self.btn_restrict)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _on_action(self, status: str, notes: str):
        target_id = self.alert_data.get("alert_id") or str(self.alert_data.get("warning_id", ""))
        acc = self.alert_data.get("sender_account_ref") or self.alert_data.get("entity_ref", "")
        b_code = self.alert_data.get("originating_bank") or (acc.split('-')[0] if '-' in acc else "BANK")

        self.action_submitted.emit(target_id, status, notes, acc, b_code)
        QMessageBox.information(
            self,
            "Decision Recorded",
            f"Alert {target_id} updated to status: {status}\n(Persisted to SQLite)"
        )
        self.accept()

