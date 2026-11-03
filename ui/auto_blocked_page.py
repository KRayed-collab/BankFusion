"""
BankFusion Desktop Page 3: Automatically Blocked Transactions
============================================================
Dedicated operations panel for managing high-risk multi-factor transactions (Tier 3).
Features:
- Enterprise light theme with white KPI cards and crisp typography
- Summary KPI Cards: Active Blocks, Released Blocks, Blocked Volume, Avg Triggered Rules
- Tabbed Filtering: Active Blocks, Released History, All Auto-Blocks
- High data-density interactive table with user-resizable columns
- Operator Inspect & Release Workflow with mandatory audit justification and simulated processing release
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QTabWidget, QDialog, QTextEdit, QLineEdit, QMessageBox,
    QGridLayout, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QBrush

from database.database_connection import SessionLocal
from warehouse.warehouse_queries import (
    get_auto_blocked_transactions,
    get_auto_blocked_summary_metrics,
)
from fraud_detection.enforcement_policy import release_enforcement_transaction
from ui.theme import (
    COLOR_BG, COLOR_CARD_BG, COLOR_BORDER, COLOR_BORDER_DARK,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED,
    COLOR_ACCENT, COLOR_CLEAR, COLOR_CLEAR_BG,
    COLOR_REVIEW, COLOR_REVIEW_BG,
    COLOR_BLOCKED, COLOR_BLOCKED_BG, COLOR_BLOCKED_BORDER,
    COLOR_RELEASED, COLOR_RELEASED_BG, COLOR_RELEASED_BORDER
)


class ReleaseBlockDialog(QDialog):
    """Modal dialog allowing an investigator to inspect evidence and release an auto-blocked transaction."""

    def __init__(self, record_dict: dict, parent=None):
        super().__init__(parent)
        self.rec = record_dict
        self.setWindowTitle(f"Inspect & Release Auto-Block — Txn #{self.rec['transaction_key']}")
        self.resize(580, 520)
        self.setMinimumSize(500, 440)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Title
        t_lbl = QLabel(f"Inspect Auto-Blocked Transaction: {self.rec['source_transaction_id']}")
        t_lbl.setStyleSheet(f"font-size: 16px; font-weight: 800; color: {COLOR_BLOCKED};")
        layout.addWidget(t_lbl)

        # Evidence Summary Card
        ev_box = QFrame()
        ev_box.setStyleSheet(f"""
            background-color: #FFFFFF;
            border: 1px solid {COLOR_BORDER};
            border-left: 4px solid {COLOR_BLOCKED};
            border-radius: 6px;
            padding: 12px;
        """)
        ev_l = QVBoxLayout(ev_box)
        ev_l.setSpacing(6)

        amt_inr = self.rec.get("amount_inr", self.rec.get("amount_paise", 0) / 100.0)
        ev_l.addWidget(QLabel(f"<b>Source Bank:</b> {self.rec.get('bank_name', self.rec['source_bank_code'])}  |  <b>Mode:</b> {self.rec.get('payment_method', 'N/A')}"))
        ev_l.addWidget(QLabel(f"<b>Amount:</b> ₹{amt_inr:,.2f}  |  <b>Timestamp:</b> {str(self.rec.get('created_at', 'N/A'))[:19].replace('T', ' ')}"))
        ev_l.addWidget(QLabel(f"<b>Sender:</b> {self.rec.get('sender_account_ref', 'N/A')}  →  <b>Receiver:</b> {self.rec.get('receiver_account_ref', 'N/A')}"))
        ev_l.addWidget(QLabel(f"<b>Triggered Factors ({self.rec.get('triggered_factor_count', 0)}):</b> <span style='color:{COLOR_BLOCKED}; font-weight:700;'>{self.rec.get('triggered_factors_summary', 'N/A')}</span>"))
        if self.rec.get("blocking_reason"):
            ev_l.addWidget(QLabel(f"<b>Enforcement Policy:</b> {self.rec['blocking_reason']}"))

        layout.addWidget(ev_box)

        # Form Inputs
        f_lbl = QLabel("Operator Release Justification:")
        f_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-weight: 700; font-size: 12px;")
        layout.addWidget(f_lbl)

        layout.addWidget(QLabel("Operator ID / Badge Ref:"))
        self.edit_operator = QLineEdit("OPERATOR-01")
        layout.addWidget(self.edit_operator)

        layout.addWidget(QLabel("Documented Release Justification (Mandatory):"))
        self.edit_reason = QTextEdit()
        self.edit_reason.setPlaceholderText("Enter the verified compliance justification or customer confirmation details...")
        self.edit_reason.setFixedHeight(80)
        layout.addWidget(self.edit_reason)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryButton")
        btn_cancel.clicked.connect(self.reject)

        self.btn_confirm = QPushButton("🔓 Confirm Release & Allow Processing")
        self.btn_confirm.setObjectName("primaryButton")
        self.btn_confirm.setStyleSheet(f"""
            background-color: {COLOR_RELEASED};
            color: #FFFFFF;
            font-weight: 700;
            border-radius: 6px;
            padding: 8px 16px;
        """)
        self.btn_confirm.clicked.connect(self._on_confirm_release)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(self.btn_confirm)
        layout.addLayout(btn_layout)

    def _on_confirm_release(self):
        op_id = self.edit_operator.text().strip()
        reason = self.edit_reason.toPlainText().strip()

        if not op_id:
            QMessageBox.warning(self, "Missing Operator ID", "Please specify an Operator ID.")
            return

        if not reason or len(reason) < 5:
            QMessageBox.warning(
                self,
                "Justification Required",
                "A documented justification reason (at least 5 characters) is required to release an auto-block."
            )
            return

        try:
            with SessionLocal() as session:
                release_enforcement_transaction(
                    session=session,
                    transaction_key=self.rec["transaction_key"],
                    operator_id=op_id,
                    release_reason=reason,
                )
            QMessageBox.information(
                self,
                "Transaction Released",
                f"Transaction #{self.rec['transaction_key']} has been successfully released.\n"
                f"Simulated processing completed and immutable audit entry logged."
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Release Failed", f"Failed to release transaction:\n{str(e)}")


class AutoBlockedPage(QWidget):
    """Primary operational page for inspecting and managing automatically blocked transactions."""

    block_released = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_filter = "ACTIVE"
        self._build_ui()
        self.refresh_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # 1. Header Toolbar
        hdr_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title_lbl = QLabel("Automatically Blocked Transactions")
        title_lbl.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {COLOR_TEXT_PRIMARY};")
        subtitle_lbl = QLabel("Tier 3 Policy Enforcement: High-confidence multi-factor fraud automated containment")
        subtitle_lbl.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_SECONDARY};")

        title_box.addWidget(title_lbl)
        title_box.addWidget(subtitle_lbl)

        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.setObjectName("secondaryButton")
        btn_refresh.setMinimumHeight(36)
        btn_refresh.clicked.connect(self.refresh_data)

        self.btn_inject_demo = QPushButton("🚨 Trigger 3-Factor Demo Block")
        self.btn_inject_demo.setObjectName("dangerButton")
        self.btn_inject_demo.setMinimumHeight(36)
        self.btn_inject_demo.setToolTip("Inject controlled 3-factor fraud pattern (Velocity + Device + Large Amount) to verify Tier 3 auto-blocking")
        self.btn_inject_demo.clicked.connect(self._on_inject_demo)

        hdr_layout.addLayout(title_box)
        hdr_layout.addStretch()
        hdr_layout.addWidget(self.btn_inject_demo)
        hdr_layout.addWidget(btn_refresh)
        layout.addLayout(hdr_layout)

        # 2. KPI Summary Cards
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(12)

        self.card_active = self._create_card("Active Auto-Blocks", "0", "Awaiting operator triage", COLOR_BLOCKED)
        self.card_released = self._create_card("Released Blocks", "0", "Operator overridden & allowed", COLOR_RELEASED)
        self.card_amount = self._create_card("Blocked Volume", "₹0.00", "Total active blocked value", COLOR_REVIEW)
        self.card_factors = self._create_card("Avg Triggered Rules", "0.0", "Rules per blocked transaction", COLOR_TEXT_PRIMARY)

        kpi_grid.addWidget(self.card_active, 0, 0)
        kpi_grid.addWidget(self.card_released, 0, 1)
        kpi_grid.addWidget(self.card_amount, 0, 2)
        kpi_grid.addWidget(self.card_factors, 0, 3)
        layout.addLayout(kpi_grid)

        # 3. Filter Tabs
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(QWidget(), "Active Blocks")
        self.tab_widget.addTab(QWidget(), "Released History")
        self.tab_widget.addTab(QWidget(), "All Auto-Blocks")
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tab_widget)

        # 4. Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Key / Ref", "Timestamp & Bank", "Sender → Receiver",
            "Amount (₹)", "Rules Count", "Factors Triggered", "Status & Policy", "Action"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.resizeSection(0, 120)  # Key / Ref
        header.resizeSection(1, 150)  # Timestamp & Bank
        header.resizeSection(2, 190)  # Sender -> Receiver
        header.resizeSection(3, 110)  # Amount (₹)
        header.resizeSection(4, 95)   # Rules Count
        header.resizeSection(5, 240)  # Factors Triggered
        header.resizeSection(6, 140)  # Status & Policy
        header.resizeSection(7, 130)  # Action
        header.setSectionResizeMode(5, QHeaderView.Stretch)

        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        layout.addWidget(self.table)

        # 5. Empty State Label
        self.lbl_empty_state = QLabel(
            "No automatically blocked transactions found for the selected view."
        )
        self.lbl_empty_state.setAlignment(Qt.AlignCenter)
        self.lbl_empty_state.setStyleSheet(f"""
            background-color: {COLOR_CARD_BG};
            border: 1px dashed {COLOR_BORDER};
            border-radius: 6px;
            color: {COLOR_TEXT_SECONDARY};
            font-size: 13px;
            font-weight: 500;
            padding: 40px;
        """)
        self.lbl_empty_state.setVisible(False)
        layout.addWidget(self.lbl_empty_state)

    def _create_card(self, title: str, value: str, sub: str, color_hex: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_CARD_BG};
                border: 1px solid {COLOR_BORDER};
                border-top: 3px solid {color_hex};
                border-radius: 6px;
                padding: 10px 14px;
            }}
        """)
        l = QVBoxLayout(card)
        l.setContentsMargins(4, 4, 4, 4)
        l.setSpacing(2)

        t_lbl = QLabel(title.upper())
        t_lbl.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {COLOR_TEXT_SECONDARY}; letter-spacing: 0.4px;")
        v_lbl = QLabel(value)
        v_lbl.setObjectName("card_val")
        v_lbl.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {COLOR_TEXT_PRIMARY};")
        s_lbl = QLabel(sub)
        s_lbl.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_MUTED};")

        l.addWidget(t_lbl)
        l.addWidget(v_lbl)
        l.addWidget(s_lbl)
        return card

    def _on_tab_changed(self, index: int):
        if index == 0:
            self.current_filter = "ACTIVE"
        elif index == 1:
            self.current_filter = "RELEASED"
        else:
            self.current_filter = "ALL"
        self.refresh_data()

    def refresh_data(self):
        with SessionLocal() as session:
            metrics = get_auto_blocked_summary_metrics(session)
            records = get_auto_blocked_transactions(session, status_filter=self.current_filter, limit=200)

        # Update KPI Cards
        self.card_active.findChild(QLabel, "card_val").setText(str(metrics["active_blocks"]))
        self.card_released.findChild(QLabel, "card_val").setText(str(metrics["released_blocks"]))
        self.card_amount.findChild(QLabel, "card_val").setText(f"₹{metrics['total_blocked_inr']:,.2f}")
        self.card_factors.findChild(QLabel, "card_val").setText(str(metrics["avg_factors"]))

        self.tab_widget.setTabText(0, f"Active Blocks ({metrics['active_blocks']})")
        self.tab_widget.setTabText(1, f"Released History ({metrics['released_blocks']})")

        # Populate Table
        if not records:
            self.lbl_empty_state.setVisible(True)
            self.table.setVisible(False)
            filter_name = "active blocks" if self.current_filter == "ACTIVE" else ("released history" if self.current_filter == "RELEASED" else "auto-blocks")
            self.lbl_empty_state.setText(
                f"No {filter_name} found in the Kimball warehouse. System is actively screening transactions."
            )
            self.table.setRowCount(0)
            return

        self.lbl_empty_state.setVisible(False)
        self.table.setVisible(True)
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(records))

        for row_idx, r in enumerate(records):
            # Col 0: Key / Ref
            item_ref = QTableWidgetItem(f"#{r['transaction_key']}\n{r['source_transaction_id']}")
            item_ref.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(row_idx, 0, item_ref)

            # Col 1: Timestamp & Bank
            ts_str = str(r.get("created_at") or "")[:19].replace("T", " ")
            item_time = QTableWidgetItem(f"{ts_str}\n{r.get('bank_name', r['source_bank_code'])}")
            item_time.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(row_idx, 1, item_time)

            # Col 2: Sender -> Receiver
            item_acc = QTableWidgetItem(f"{r['sender_account_ref']}\n→ {r['receiver_account_ref']}")
            item_acc.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(row_idx, 2, item_acc)

            # Col 3: Amount (Right aligned)
            amt_inr = r.get("amount_inr", r.get("amount_paise", 0) / 100.0)
            item_amt = QTableWidgetItem(f"₹{amt_inr:,.2f}")
            item_amt.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item_amt.setForeground(QBrush(QColor(COLOR_TEXT_PRIMARY)))
            self.table.setItem(row_idx, 3, item_amt)

            # Col 4: Factor Count Badge
            fc = r.get("triggered_factor_count", 0)
            item_fc = QTableWidgetItem(f"{fc} Rules")
            item_fc.setTextAlignment(Qt.AlignCenter)
            item_fc.setForeground(QBrush(QColor(COLOR_BLOCKED if fc >= 3 else COLOR_REVIEW)))
            self.table.setItem(row_idx, 4, item_fc)

            # Col 5: Triggered Factors Summary
            summary_str = r.get("triggered_factors_summary", "None")
            item_summary = QTableWidgetItem(summary_str)
            item_summary.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(row_idx, 5, item_summary)

            # Col 6: Status & Policy
            st = r["enforcement_status"]
            if st == "AUTO_BLOCKED":
                stat_text = "AUTO-BLOCKED"
                color = COLOR_BLOCKED
            elif st == "RELEASED":
                rel_by = r.get("released_by") or "Operator"
                stat_text = f"RELEASED\nby {rel_by}"
                color = COLOR_RELEASED
            else:
                stat_text = st
                color = COLOR_TEXT_SECONDARY

            item_status = QTableWidgetItem(stat_text)
            item_status.setTextAlignment(Qt.AlignCenter)
            item_status.setForeground(QBrush(QColor(color)))
            self.table.setItem(row_idx, 6, item_status)

            # Col 7: Action Button
            if r.get("is_active_block") == 1:
                btn_action = QPushButton("Inspect & Release")
                btn_action.setObjectName("dangerButton")
                btn_action.setStyleSheet(f"""
                    background-color: #FFFFFF;
                    color: {COLOR_BLOCKED};
                    border: 1px solid {COLOR_BLOCKED_BORDER};
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-weight: 600;
                    font-size: 11px;
                """)
                btn_action.clicked.connect(lambda checked=False, rec=r: self._open_release_dialog(rec))
                self.table.setCellWidget(row_idx, 7, btn_action)
            else:
                item_done = QTableWidgetItem("Released")
                item_done.setTextAlignment(Qt.AlignCenter)
                item_done.setForeground(QBrush(QColor(COLOR_TEXT_MUTED)))
                self.table.setItem(row_idx, 7, item_done)

        self.table.setUpdatesEnabled(True)

    def _open_release_dialog(self, record_dict: dict):
        dlg = ReleaseBlockDialog(record_dict, self)
        if dlg.exec():
            self.refresh_data()
            self.block_released.emit()

    def _on_inject_demo(self):
        """Triggers controlled 3-factor fraud scenario directly from blocked page."""
        try:
            from fraud_detection.demo_auto_block_scenario import inject_controlled_auto_block_scenario
            res = inject_controlled_auto_block_scenario()
            self.refresh_data()
            self.block_released.emit()
            QMessageBox.information(
                self,
                "Demo Auto-Block Injected",
                f"Controlled 3-factor fraud scenario successfully injected!\n\n"
                f"• Target Transaction: {res['target_transaction_id']}\n"
                f"• Amount: ₹{res['amount_inr']:,.2f}\n"
                f"• Triggered Rules ({res['triggered_factor_count']}): {res['triggered_factors_summary']}\n"
                f"• Status: {res['enforcement_status']} (Tier 3)\n"
                f"• Pre-Completion Hold: {res['fact_status']}\n\n"
                f"The transaction is now active under Active Blocks and ready for inspection."
            )
        except Exception as e:
            QMessageBox.critical(self, "Demo Error", f"Failed to inject demonstration scenario:\n{str(e)}")
