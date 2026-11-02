"""
BankFusion Dialog: Transaction Detail Inspector
===============================================
Native Qt QDialog presenting dimensional star-schema context,
integer-paise verification, and deterministic rule breakdowns for a transaction.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QTextEdit
)
from PySide6.QtCore import Qt
from ui.theme import (
    COLOR_PANEL_BG, COLOR_BORDER, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED, COLOR_BLUE, COLOR_RED, COLOR_GREEN
)


class TransactionDetailsDialog(QDialog):
    """Deep inspection dialog for FactTransaction records."""

    def __init__(self, txn_row: dict, parent=None):
        super().__init__(parent)
        self.txn = txn_row
        self.setWindowTitle(f"Transaction Record — {self.txn.get('source_transaction_id', 'TXN')}")
        self.resize(720, 560)
        self.setModal(True)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Header: ID and Screening Badge
        hdr = QHBoxLayout()
        title = QLabel(f"Fact Transaction: {self.txn.get('source_transaction_id', 'TXN')}")
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #f8fafc;")

        is_susp = self.txn.get("is_predicted_suspicious", 0) == 1
        badge_text = "🚨 SUSPICIOUS" if is_susp else "✅ CLEAN / CLEARED"
        badge_bg = "#7f1d1d" if is_susp else "#064e3b"
        badge_fg = "#fca5a5" if is_susp else "#6ee7b7"

        badge = QLabel(f" {badge_text} ")
        badge.setStyleSheet(f"""
            background-color: {badge_bg};
            color: {badge_fg};
            font-weight: 700;
            font-size: 11px;
            padding: 4px 10px;
            border-radius: 4px;
        """)

        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(badge)
        layout.addLayout(hdr)

        # Dimensional Context Frame
        grid_frame = QFrame()
        grid_frame.setStyleSheet(f"""
            background-color: {COLOR_PANEL_BG};
            border: 1px solid {COLOR_BORDER};
            border-radius: 8px;
            padding: 14px;
        """)
        grid = QGridLayout(grid_frame)
        grid.setSpacing(12)

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
            l_w.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-weight: 600; font-size: 11px;")
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
        sec_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8;")
        layout.addWidget(sec_title)

        rule_frame = QFrame()
        rule_frame.setStyleSheet(f"""
            background-color: #0d1424;
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
            r_lbl.setStyleSheet("color: #cbd5e1; font-size: 12px;")

            res_text = "🚨 FLAGGED" if is_flagged else "✅ Clear"
            res_color = COLOR_RED if is_flagged else COLOR_GREEN
            res_lbl = QLabel(res_text)
            res_lbl.setStyleSheet(f"color: {res_color}; font-weight: 700; font-size: 12px;")

            r_row.addWidget(r_lbl)
            r_row.addStretch()
            r_row.addWidget(res_lbl)
            rule_layout.addLayout(r_row)

        layout.addWidget(rule_frame)

        # Bottom Close button
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)

