"""
BankFusion UI Component: Alert Card
===================================
Visual representation of an entity warning / fraud alert in the triage queue.
Features risk priority accents, context grid, and direct action triggers.
"""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QWidget
)
from PySide6.QtCore import Qt, Signal
from ui.theme import (
    COLOR_PANEL_BG, COLOR_BORDER, COLOR_BORDER_LIGHT, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED, COLOR_RED, COLOR_AMBER, COLOR_BLUE,
    COLOR_GREEN
)


class AlertCard(QFrame):
    """Card widget representing one screening alert item."""

    # action_requested: (alert_id, action_type, account_ref, bank_code)
    action_requested = Signal(str, str, str, str)
    inspect_requested = Signal(dict)

    def __init__(self, alert_data: dict, parent=None):
        super().__init__(parent)
        self.alert_data = alert_data
        self.setObjectName("alertCard")

        self._init_card()

    def _init_card(self):
        prio = (self.alert_data.get("review_priority") or "MEDIUM").upper()
        accent_color = COLOR_RED if prio == "HIGH" else (COLOR_AMBER if prio == "MEDIUM" else COLOR_BLUE)

        self.setStyleSheet(f"""
            QFrame#alertCard {{
                background-color: {COLOR_PANEL_BG};
                border: 1px solid {COLOR_BORDER};
                border-left: 5px solid {accent_color};
                border-radius: 8px;
                padding: 12px;
            }}
            QFrame#alertCard:hover {{
                border-color: {COLOR_BORDER_LIGHT};
                border-left: 5px solid {accent_color};
                background-color: #172033;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # Header Row: ID, Priority, Status, Timestamp
        hdr = QHBoxLayout()
        alert_id = self.alert_data.get("alert_id") or f"ALT-{self.alert_data.get('warning_id', 0):04d}"
        id_lbl = QLabel(f"Alert {alert_id}")
        id_lbl.setStyleSheet("font-size: 15px; font-weight: 800; color: #f8fafc;")

        prio_badge = QLabel(f" {prio} RISK ")
        prio_badge.setStyleSheet(f"""
            background-color: {accent_color};
            color: #ffffff;
            font-weight: 700;
            font-size: 10px;
            padding: 3px 8px;
            border-radius: 4px;
        """)

        status_str = (self.alert_data.get("review_status") or "NEEDS_REVIEW").replace("_", " ")
        status_bg = "#064e3b" if status_str in ("LEGITIMATE", "SUSPICIOUS") else ("#831843" if status_str == "ACCOUNT RESTRICTED" else "#1e293b")
        status_color = "#6ee7b7" if status_str in ("LEGITIMATE", "SUSPICIOUS") else ("#fbcfe8" if status_str == "ACCOUNT RESTRICTED" else "#94a3b8")

        status_badge = QLabel(f" {status_str} ")
        status_badge.setStyleSheet(f"""
            background-color: {status_bg};
            color: {status_color};
            font-weight: 700;
            font-size: 10px;
            padding: 3px 8px;
            border-radius: 4px;
            border: 1px solid #334155;
        """)

        time_lbl = QLabel(f"⏱️ {self.alert_data.get('trigger_timestamp', '')}")
        time_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")

        hdr.addWidget(id_lbl)
        hdr.addWidget(prio_badge)
        hdr.addWidget(status_badge)
        hdr.addStretch()
        hdr.addWidget(time_lbl)
        layout.addLayout(hdr)

        # 4-Column Context Grid
        grid = QGridLayout()
        grid.setSpacing(10)

        amt_paise = self.alert_data.get("amount_paise") or 0
        amt_str = f"₹{amt_paise / 100:,.2f}" if amt_paise else "N/A"
        dev_str = self.alert_data.get("device_token")
        if not dev_str or dev_str == "UNKNOWN_DEVICE":
            dev_str = "None / Unknown"

        col1_w = self._make_meta_box("ORIGIN & SENDER", self.alert_data.get("originating_bank") or "UNKNOWN", self.alert_data.get("sender_account_ref") or self.alert_data.get("entity_ref", "N/A"))
        col2_w = self._make_meta_box("DESTINATION & RECEIVER", self.alert_data.get("destination_bank") or "INTERBANK", self.alert_data.get("receiver_account_ref") or "VARIOUS")
        col3_w = self._make_meta_box("AMOUNT & METHOD", amt_str, f"{self.alert_data.get('payment_method') or 'N/A'} • {self.alert_data.get('transaction_status') or 'SETTLED'}", value_highlight="#38bdf8")
        col4_w = self._make_meta_box("DEVICE & VERDICT", dev_str, self.alert_data.get("verdict") or "POTENTIALLY SUSPICIOUS", value_highlight="#f87171")

        grid.addWidget(col1_w, 0, 0)
        grid.addWidget(col2_w, 0, 1)
        grid.addWidget(col3_w, 0, 2)
        grid.addWidget(col4_w, 0, 3)
        layout.addLayout(grid)

        # Triggered Factors & Evidence Box
        ev_box = QFrame()
        ev_box.setStyleSheet(f"""
            background-color: #0d1424;
            border-left: 3px solid #64748b;
            border-radius: 4px;
            padding: 8px 12px;
        """)
        ev_layout = QVBoxLayout(ev_box)
        ev_layout.setContentsMargins(6, 4, 6, 4)
        ev_layout.setSpacing(2)

        rules_lbl = QLabel(f"<b>Triggered Factors:</b> <span style='color: #fbbf24;'>{self.alert_data.get('rules_triggered') or self.alert_data.get('rule_name', '')}</span>")
        rules_lbl.setStyleSheet("font-size: 11px; color: #cbd5e1;")
        ev_lbl = QLabel(f"<b>Evidence:</b> {self.alert_data.get('evidence_summary', '')}")
        ev_lbl.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_SECONDARY};")
        ev_lbl.setWordWrap(True)

        ev_layout.addWidget(rules_lbl)
        ev_layout.addWidget(ev_lbl)
        layout.addWidget(ev_box)

        # Actions Toolbar
        actions = QHBoxLayout()
        actions.setSpacing(8)

        btn_inspect = QPushButton("🔍 Inspect Evidence")
        btn_inspect.setStyleSheet("background-color: #1e3a8a; color: #93c5fd; font-size: 11px; padding: 5px 12px;")
        btn_inspect.clicked.connect(lambda: self.inspect_requested.emit(self.alert_data))

        btn_legit = QPushButton("✅ Mark Legitimate")
        btn_legit.setStyleSheet("background-color: #064e3b; color: #6ee7b7; font-size: 11px; padding: 5px 12px;")
        btn_legit.clicked.connect(lambda: self._trigger_action("LEGITIMATE"))

        btn_susp = QPushButton("🚨 Confirm Suspicious")
        btn_susp.setStyleSheet("background-color: #7f1d1d; color: #fca5a5; font-size: 11px; padding: 5px 12px;")
        btn_susp.clicked.connect(lambda: self._trigger_action("SUSPICIOUS"))

        btn_esc = QPushButton("⚠️ Escalate")
        btn_esc.setStyleSheet("background-color: #78350f; color: #fcd34d; font-size: 11px; padding: 5px 12px;")
        btn_esc.clicked.connect(lambda: self._trigger_action("ESCALATED"))

        btn_rest = QPushButton("🔒 Restrict Account")
        btn_rest.setStyleSheet("background-color: #831843; color: #fbcfe8; font-size: 11px; padding: 5px 12px;")
        btn_rest.clicked.connect(lambda: self._trigger_action("ACCOUNT_RESTRICTED"))

        actions.addWidget(btn_inspect)
        actions.addStretch()
        actions.addWidget(btn_legit)
        actions.addWidget(btn_susp)
        actions.addWidget(btn_esc)
        actions.addWidget(btn_rest)

        layout.addLayout(actions)

    def _make_meta_box(self, label: str, val1: str, val2: str, value_highlight=None) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(2)

        lbl = QLabel(label)
        lbl.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {COLOR_TEXT_MUTED};")

        v1 = QLabel(val1)
        v1_color = value_highlight or COLOR_TEXT_PRIMARY
        v1.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {v1_color};")

        v2 = QLabel(val2)
        v2.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_SECONDARY}; font-family: monospace;")

        l.addWidget(lbl)
        l.addWidget(v1)
        l.addWidget(v2)
        return w

    def _trigger_action(self, action_type: str):
        target_id = self.alert_data.get("alert_id") or str(self.alert_data.get("warning_id", ""))
        acc = self.alert_data.get("sender_account_ref") or self.alert_data.get("entity_ref", "")
        b_code = self.alert_data.get("originating_bank") or (acc.split('-')[0] if '-' in acc else "BANK")
        self.action_requested.emit(target_id, action_type, acc, b_code)

