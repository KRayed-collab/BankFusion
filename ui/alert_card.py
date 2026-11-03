"""
BankFusion UI Component: Alert Card
===================================
Visual representation of an entity warning / fraud alert in the triage queue.
Features:
- Clean enterprise white card (#FFFFFF) with neutral 1px border (#D9E0E7)
- Semantic left border accent for review priority
- 4-column structured context grid (Origin, Destination, Amount, Device)
- Individual triggered rule badges
- Collapsible inline evidence summary with Show More / Show Less toggle
- Transaction-level actions: Inspect Evidence, Mark Legitimate, Confirm Suspicious, Escalate Case
  (Account-wide restriction action removed per system specifications)
"""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QWidget
)
from PySide6.QtCore import Qt, Signal
from ui.theme import (
    COLOR_CARD_BG, COLOR_BORDER, COLOR_BORDER_DARK, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED, COLOR_ACCENT,
    COLOR_CLEAR, COLOR_CLEAR_BG, COLOR_CLEAR_BORDER,
    COLOR_REVIEW, COLOR_REVIEW_BG, COLOR_REVIEW_BORDER,
    COLOR_BLOCKED, COLOR_BLOCKED_BG, COLOR_BLOCKED_BORDER,
    COLOR_RELEASED, COLOR_RELEASED_BG, COLOR_RELEASED_BORDER
)


class AlertCard(QFrame):
    """Card widget representing an alert item in the review queue."""

    # action_requested: (alert_id, action_type, account_ref, bank_code)
    action_requested = Signal(str, str, str, str)
    inspect_requested = Signal(dict)

    def __init__(self, alert_data: dict, parent=None):
        super().__init__(parent)
        self.alert_data = alert_data
        self.setObjectName("alertCard")
        self._evidence_visible = False

        self._init_card()

    def _init_card(self):
        prio = (self.alert_data.get("review_priority") or "MEDIUM").upper()
        if prio == "HIGH":
            accent_color = COLOR_BLOCKED
        elif prio == "MEDIUM":
            accent_color = COLOR_REVIEW
        else:
            accent_color = COLOR_RELEASED

        self.setStyleSheet(f"""
            QFrame#alertCard {{
                background-color: {COLOR_CARD_BG};
                border: 1px solid {COLOR_BORDER};
                border-left: 4px solid {accent_color};
                border-radius: 6px;
                padding: 10px;
            }}
            QFrame#alertCard:hover {{
                border-color: {COLOR_BORDER_DARK};
                border-left: 4px solid {accent_color};
                background-color: #FAFCFE;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        # 1. Header Row: ID, Priority Badge, Status Badge, Timestamp
        hdr = QHBoxLayout()
        alert_id = self.alert_data.get("alert_id") or f"ALT-{self.alert_data.get('warning_id', 0):04d}"
        id_lbl = QLabel(f"Alert {alert_id}")
        id_lbl.setStyleSheet(f"font-size: 14px; font-weight: 800; color: {COLOR_TEXT_PRIMARY};")

        # Priority badge
        if prio == "HIGH":
            prio_bg, prio_fg, prio_bd = COLOR_BLOCKED_BG, COLOR_BLOCKED, COLOR_BLOCKED_BORDER
        elif prio == "MEDIUM":
            prio_bg, prio_fg, prio_bd = COLOR_REVIEW_BG, COLOR_REVIEW, COLOR_REVIEW_BORDER
        else:
            prio_bg, prio_fg, prio_bd = COLOR_RELEASED_BG, COLOR_RELEASED, COLOR_RELEASED_BORDER

        prio_badge = QLabel(f" {prio} PRIORITY ")
        prio_badge.setStyleSheet(f"""
            background-color: {prio_bg};
            color: {prio_fg};
            font-weight: 700;
            font-size: 10px;
            padding: 2px 8px;
            border-radius: 4px;
            border: 1px solid {prio_bd};
        """)

        # Status badge
        raw_status = (self.alert_data.get("review_status") or "NEEDS_REVIEW").upper()
        if raw_status in ("LEGITIMATE", "RESOLVED"):
            st_bg, st_fg, st_bd = COLOR_CLEAR_BG, COLOR_CLEAR, COLOR_CLEAR_BORDER
            status_text = "LEGITIMATE"
        elif raw_status == "SUSPICIOUS":
            st_bg, st_fg, st_bd = COLOR_BLOCKED_BG, COLOR_BLOCKED, COLOR_BLOCKED_BORDER
            status_text = "CONFIRMED SUSPICIOUS"
        elif raw_status == "ESCALATED":
            st_bg, st_fg, st_bd = COLOR_RELEASED_BG, COLOR_RELEASED, COLOR_RELEASED_BORDER
            status_text = "ESCALATED"
        else:
            st_bg, st_fg, st_bd = COLOR_REVIEW_BG, COLOR_REVIEW, COLOR_REVIEW_BORDER
            status_text = "REVIEW PENDING"

        status_badge = QLabel(f" {status_text} ")
        status_badge.setStyleSheet(f"""
            background-color: {st_bg};
            color: {st_fg};
            font-weight: 700;
            font-size: 10px;
            padding: 2px 8px;
            border-radius: 4px;
            border: 1px solid {st_bd};
        """)

        time_lbl = QLabel(f"⏱ {str(self.alert_data.get('trigger_timestamp', ''))[:19]}")
        time_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")

        hdr.addWidget(id_lbl)
        hdr.addWidget(prio_badge)
        hdr.addWidget(status_badge)
        hdr.addStretch()
        hdr.addWidget(time_lbl)
        layout.addLayout(hdr)

        # 2. Structured 4-Column Context Grid
        grid = QGridLayout()
        grid.setSpacing(10)

        amt_paise = self.alert_data.get("amount_paise") or 0
        amt_str = f"₹{amt_paise / 100:,.2f}" if amt_paise else "N/A"
        dev_str = self.alert_data.get("device_token")
        if not dev_str or dev_str == "UNKNOWN_DEVICE":
            dev_str = "None / Default"

        col1_w = self._make_meta_box("ORIGIN & SENDER", self.alert_data.get("originating_bank") or "UNKNOWN", self.alert_data.get("sender_account_ref") or self.alert_data.get("entity_ref", "N/A"))
        col2_w = self._make_meta_box("DESTINATION & RECEIVER", self.alert_data.get("destination_bank") or "INTERBANK", self.alert_data.get("receiver_account_ref") or "VARIOUS")
        col3_w = self._make_meta_box("AMOUNT & METHOD", amt_str, f"{self.alert_data.get('payment_method') or 'N/A'} • {self.alert_data.get('transaction_status') or 'SETTLED'}", value_highlight=COLOR_TEXT_PRIMARY)
        col4_w = self._make_meta_box("DEVICE TOKEN", dev_str, self.alert_data.get("verdict") or "FLAGGED BY RULES", value_highlight=COLOR_TEXT_SECONDARY)

        grid.addWidget(col1_w, 0, 0)
        grid.addWidget(col2_w, 0, 1)
        grid.addWidget(col3_w, 0, 2)
        grid.addWidget(col4_w, 0, 3)
        layout.addLayout(grid)

        # 3. Triggered Factors Strip & Collapsible Evidence
        ev_container = QFrame()
        ev_container.setStyleSheet(f"""
            background-color: #F8FAFC;
            border: 1px solid {COLOR_BORDER};
            border-radius: 4px;
            padding: 8px 10px;
        """)
        ev_layout = QVBoxLayout(ev_container)
        ev_layout.setContentsMargins(6, 4, 6, 4)
        ev_layout.setSpacing(4)

        factors_row = QHBoxLayout()
        factors_title = QLabel("Triggered Detection Rules:")
        factors_title.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {COLOR_TEXT_PRIMARY};")
        factors_row.addWidget(factors_title)

        # Render factor badges
        rules_str = self.alert_data.get('rules_triggered') or self.alert_data.get('rule_name', '')
        rules_list = [r.strip() for r in rules_str.split(',') if r.strip()]
        if not rules_list:
            rules_list = [rules_str] if rules_str else ["Rule Match"]

        for rule in rules_list:
            badge = QLabel(f" {rule} ")
            badge.setStyleSheet(f"""
                background-color: {COLOR_REVIEW_BG};
                color: {COLOR_REVIEW};
                font-size: 10px;
                font-weight: 700;
                padding: 2px 6px;
                border: 1px solid {COLOR_REVIEW_BORDER};
                border-radius: 3px;
            """)
            factors_row.addWidget(badge)

        factors_row.addStretch()

        self.btn_toggle_evidence = QPushButton("▼ Show Evidence")
        self.btn_toggle_evidence.setObjectName("secondaryButton")
        self.btn_toggle_evidence.setStyleSheet("font-size: 10px; padding: 2px 8px; border-radius: 3px;")
        self.btn_toggle_evidence.clicked.connect(self._toggle_evidence)
        factors_row.addWidget(self.btn_toggle_evidence)

        ev_layout.addLayout(factors_row)

        self.ev_details_lbl = QLabel(f"<b>Evidence Summary:</b> {self.alert_data.get('evidence_summary', 'No summary details.')}")
        self.ev_details_lbl.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_SECONDARY}; line-height: 1.3;")
        self.ev_details_lbl.setWordWrap(True)
        self.ev_details_lbl.setVisible(False)
        ev_layout.addWidget(self.ev_details_lbl)

        layout.addWidget(ev_container)

        # 4. Actions Toolbar
        actions = QHBoxLayout()
        actions.setSpacing(8)

        btn_inspect = QPushButton("🔍 Inspect Evidence")
        btn_inspect.setObjectName("primaryButton")
        btn_inspect.setStyleSheet(f"""
            background-color: {COLOR_ACCENT};
            color: #FFFFFF;
            font-size: 11px;
            font-weight: 600;
            padding: 5px 12px;
            border-radius: 4px;
        """)
        btn_inspect.clicked.connect(lambda: self.inspect_requested.emit(self.alert_data))

        btn_legit = QPushButton("✓ Mark Legitimate")
        btn_legit.setStyleSheet(f"""
            background-color: #FFFFFF;
            color: {COLOR_CLEAR};
            border: 1px solid {COLOR_CLEAR_BORDER};
            font-size: 11px;
            font-weight: 600;
            padding: 5px 12px;
            border-radius: 4px;
        """)
        btn_legit.clicked.connect(lambda: self._trigger_action("LEGITIMATE"))

        btn_susp = QPushButton("⚠ Confirm Suspicious")
        btn_susp.setStyleSheet(f"""
            background-color: #FFFFFF;
            color: {COLOR_REVIEW};
            border: 1px solid {COLOR_REVIEW_BORDER};
            font-size: 11px;
            font-weight: 600;
            padding: 5px 12px;
            border-radius: 4px;
        """)
        btn_susp.clicked.connect(lambda: self._trigger_action("SUSPICIOUS"))

        btn_esc = QPushButton("⤴ Escalate Case")
        btn_esc.setStyleSheet(f"""
            background-color: #FFFFFF;
            color: {COLOR_RELEASED};
            border: 1px solid {COLOR_RELEASED_BORDER};
            font-size: 11px;
            font-weight: 600;
            padding: 5px 12px;
            border-radius: 4px;
        """)
        btn_esc.clicked.connect(lambda: self._trigger_action("ESCALATED"))

        actions.addWidget(btn_inspect)
        actions.addStretch()
        actions.addWidget(btn_legit)
        actions.addWidget(btn_susp)
        actions.addWidget(btn_esc)

        layout.addLayout(actions)

    def _toggle_evidence(self):
        self._evidence_visible = not self._evidence_visible
        self.ev_details_lbl.setVisible(self._evidence_visible)
        self.btn_toggle_evidence.setText("▲ Hide Evidence" if self._evidence_visible else "▼ Show Evidence")

    def _make_meta_box(self, label: str, val1: str, val2: str, value_highlight=None) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(2)

        lbl = QLabel(label)
        lbl.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {COLOR_TEXT_MUTED}; letter-spacing: 0.3px;")

        v1 = QLabel(val1)
        v1_color = value_highlight or COLOR_TEXT_PRIMARY
        v1.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {v1_color};")

        v2 = QLabel(val2)
        v2.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_SECONDARY}; font-family: 'Consolas', 'Courier New', monospace;")

        l.addWidget(lbl)
        l.addWidget(v1)
        l.addWidget(v2)
        return w

    def _trigger_action(self, action_type: str):
        target_id = self.alert_data.get("alert_id") or str(self.alert_data.get("warning_id", ""))
        acc = self.alert_data.get("sender_account_ref") or self.alert_data.get("entity_ref", "")
        b_code = self.alert_data.get("originating_bank") or (acc.split('-')[0] if '-' in acc else "BANK")
        self.action_requested.emit(target_id, action_type, acc, b_code)
