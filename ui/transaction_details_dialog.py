"""
BankFusion Dialog: Transaction Detail Inspector
===============================================
Native Qt QDialog presenting dimensional star-schema context,
integer-paise verification, and deterministic rule breakdowns for a transaction.
Features:
- Enterprise light styling
- One-click copy buttons for Transaction ID and Account References
- Full 4-factor deterministic rule inspection with actual triggered state
- Preserved status colors and clear typography
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QApplication
)
from PySide6.QtCore import Qt
from ui.theme import (
    COLOR_CARD_BG, COLOR_BORDER, COLOR_BORDER_DARK, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED, COLOR_ACCENT,
    COLOR_CLEAR, COLOR_CLEAR_BG, COLOR_CLEAR_BORDER,
    COLOR_BLOCKED, COLOR_BLOCKED_BG, COLOR_BLOCKED_BORDER
)


class TransactionDetailsDialog(QDialog):
    """Deep inspection dialog for FactTransaction records."""

    def __init__(self, txn_row: dict, parent=None):
        super().__init__(parent)
        self.txn = txn_row
        self.setWindowTitle(f"Transaction Record — {self.txn.get('source_transaction_id', 'TXN')}")
        self.resize(740, 580)
        self.setModal(True)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 20)

        # Header: ID and Screening Badge
        hdr = QHBoxLayout()
        txn_id = str(self.txn.get('source_transaction_id', 'TXN'))
        title = QLabel(f"Transaction: {txn_id}")
        title.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {COLOR_TEXT_PRIMARY};")

        is_susp = self.txn.get("is_predicted_suspicious", 0) == 1
        if is_susp:
            badge_text = "SUSPICIOUS / FLAGGED"
            badge_bg = COLOR_BLOCKED_BG
            badge_fg = COLOR_BLOCKED
            badge_bd = COLOR_BLOCKED_BORDER
        else:
            badge_text = "CLEARED / BENIGN"
            badge_bg = COLOR_CLEAR_BG
            badge_fg = COLOR_CLEAR
            badge_bd = COLOR_CLEAR_BORDER

        badge = QLabel(f" {badge_text} ")
        badge.setStyleSheet(f"""
            background-color: {badge_bg};
            color: {badge_fg};
            font-weight: 700;
            font-size: 11px;
            padding: 4px 10px;
            border-radius: 4px;
            border: 1px solid {badge_bd};
        """)

        btn_copy_id = QPushButton("📋 Copy ID")
        btn_copy_id.setObjectName("secondaryButton")
        btn_copy_id.setStyleSheet("font-size: 11px; padding: 4px 8px;")
        btn_copy_id.clicked.connect(lambda: self._copy_to_clipboard(txn_id))

        hdr.addWidget(title)
        hdr.addWidget(btn_copy_id)
        hdr.addStretch()
        hdr.addWidget(badge)
        layout.addLayout(hdr)

        # Dimensional Context Frame
        grid_frame = QFrame()
        grid_frame.setStyleSheet(f"""
            background-color: #FFFFFF;
            border: 1px solid {COLOR_BORDER};
            border-radius: 6px;
            padding: 12px;
        """)
        grid = QGridLayout(grid_frame)
        grid.setSpacing(10)

        amt_paise = self.txn.get("amount_paise", 0)
        amt_inr = self.txn.get("amount_inr", amt_paise / 100.0)

        meta_items = [
            ("Transaction Key:", str(self.txn.get("transaction_key", "N/A"))),
            ("Source Record Refs:", str(self.txn.get("source_record_refs", "N/A"))),
            ("Originating Bank:", f"{self.txn.get('bank_code', 'N/A')} ({self.txn.get('bank_name', '')})"),
            ("Destination Bank:", str(self.txn.get("destination_bank", "N/A"))),
            ("Sender Account:", str(self.txn.get("source_account_ref", "N/A"))),
            ("Receiver Account:", str(self.txn.get("destination_account_ref", "N/A"))),
            ("Monetary Amount:", f"₹{amt_inr:,.2f} ({int(amt_paise):,} paise)"),
            ("Payment Method:", str(self.txn.get("payment_method", "N/A"))),
            ("Transaction Status:", str(self.txn.get("transaction_status", "N/A"))),
            ("Device Token:", str(self.txn.get("device_token") or "UNKNOWN_DEVICE")),
            ("Timestamp (IST):", str(self.txn.get("transaction_timestamp", "N/A"))),
            ("Unix Epoch:", str(self.txn.get("epoch_timestamp", "N/A"))),
        ]

        row, col = 0, 0
        for label, val in meta_items:
            l_w = QLabel(label)
            l_w.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-weight: 600; font-size: 11px;")
            v_w = QLabel(str(val))
            v_w.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-weight: 700; font-size: 12px;")
            v_w.setTextInteractionFlags(Qt.TextSelectableByMouse)

            grid.addWidget(l_w, row, col)
            grid.addWidget(v_w, row, col + 1)
            col += 2
            if col >= 4:
                col = 0
                row += 1

        layout.addWidget(grid_frame)

        # 4-Factor Deterministic Rule Breakdown
        sec_title = QLabel("4-FACTOR DETERMINISTIC RULE BREAKDOWN")
        sec_title.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {COLOR_TEXT_SECONDARY}; letter-spacing: 0.5px;")
        layout.addWidget(sec_title)

        rule_frame = QFrame()
        rule_frame.setStyleSheet(f"""
            background-color: #FFFFFF;
            border: 1px solid {COLOR_BORDER};
            border-radius: 6px;
            padding: 12px;
        """)
        rule_layout = QVBoxLayout(rule_frame)
        rule_layout.setSpacing(8)

        v_flag = self.txn.get("flagged_by_velocity", 0) == 1
        d_flag = self.txn.get("flagged_by_device", 0) == 1
        l_flag = self.txn.get("flagged_by_large_amount", 0) == 1
        c_flag = self.txn.get("flagged_by_cross_bank_movement", 0) == 1

        rules = [
            ("Rule 1 — Velocity Burst (≥4 attempts in 300s):", v_flag),
            ("Rule 2 — Shared Device (≥3 accounts on token in 24h):", d_flag),
            ("Rule 3 — Unusually Large Amount (≥3x median & ≥₹50k / Fallback ≥₹100k):", l_flag),
            ("Rule 4 — Rapid Cross-Bank Movement (Multi-hop 80%-100% in 10 mins):", c_flag),
        ]

        for rule_name, is_flagged in rules:
            r_row = QHBoxLayout()
            r_lbl = QLabel(rule_name)
            r_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")

            res_text = "FLAGGED" if is_flagged else "Clear"
            res_color = COLOR_BLOCKED if is_flagged else COLOR_CLEAR
            res_bg = COLOR_BLOCKED_BG if is_flagged else COLOR_CLEAR_BG
            res_bd = COLOR_BLOCKED_BORDER if is_flagged else COLOR_CLEAR_BORDER

            res_lbl = QLabel(f" {res_text} ")
            res_lbl.setStyleSheet(f"""
                color: {res_color};
                background-color: {res_bg};
                border: 1px solid {res_bd};
                border-radius: 3px;
                font-weight: 700;
                font-size: 11px;
                padding: 2px 6px;
            """)

            r_row.addWidget(r_lbl)
            r_row.addStretch()
            r_row.addWidget(res_lbl)
            rule_layout.addLayout(r_row)

        layout.addWidget(rule_frame)

        # Bottom Close button
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setObjectName("primaryButton")
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)

    def _copy_to_clipboard(self, text: str):
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
