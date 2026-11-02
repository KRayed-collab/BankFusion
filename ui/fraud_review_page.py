"""
BankFusion Desktop Page 1: Fraud Review Queue
=============================================
Operational triage queue for bank fraud investigators.
Features real-time summary cards, tabbed alert filtering, detailed alert cards,
empty-state handling, and instant SQLite decision persistence.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QMessageBox, QTabWidget, QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Qt, Slot, Signal

from database.database_connection import SessionLocal
from fraud_detection import review_actions
from ui.summary_cards import SummaryCardsPanel
from ui.alert_card import AlertCard
from ui.alert_details_dialog import AlertDetailsDialog
from ui.theme import (
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED,
    COLOR_BORDER, COLOR_PANEL_BG, COLOR_BLUE
)
from workers.detection_worker import DetectionWorker


class FraudReviewPage(QWidget):
    """Main triage queue view for reviewing and resolving fraud alerts."""

    screening_completed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_filter = "Needs Review"
        self.detection_worker = None
        self.is_dirty = True
        self.has_loaded = False

        self._build_ui()
        self.refresh_queue(force=True)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 24, 28, 24)
        main_layout.setSpacing(18)

        # 1. Header Toolbar
        hdr_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title_lbl = QLabel("🛡️ Fraud Review Queue")
        title_lbl.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {COLOR_TEXT_PRIMARY};")
        subtitle_lbl = QLabel("Operational Multi-Bank Risk Surveillance & Triage Station")
        subtitle_lbl.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_MUTED};")

        title_box.addWidget(title_lbl)
        title_box.addWidget(subtitle_lbl)

        self.btn_run_detection = QPushButton("⚡ Run Fraud Screening")
        self.btn_run_detection.setObjectName("primaryButton")
        self.btn_run_detection.setMinimumHeight(38)
        self.btn_run_detection.clicked.connect(self.trigger_fraud_detection)

        hdr_layout.addLayout(title_box)
        hdr_layout.addStretch()
        hdr_layout.addWidget(self.btn_run_detection)
        main_layout.addLayout(hdr_layout)

        # 2. Top Summary KPI Cards
        self.summary_panel = SummaryCardsPanel(self)
        main_layout.addWidget(self.summary_panel)

        # 3. Tab Navigation for Queue Views
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(QWidget(), "🚨 Needs Review")
        self.tab_widget.addTab(QWidget(), "📋 All Alerts")
        self.tab_widget.addTab(QWidget(), "✅ Resolved")
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.tab_widget)

        # 4. Scroll Area for Alert Cards
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
        """)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.addStretch()
        self.is_dirty = False
        self.has_loaded = True

        self.scroll_area.setWidget(self.cards_container)
        main_layout.addWidget(self.scroll_area)

    def _on_tab_changed(self, idx: int):
        tab_names = ["Needs Review", "All Alerts", "Resolved"]
        self.current_filter = tab_names[idx] if idx < len(tab_names) else "Needs Review"
        self.refresh_queue(force=True)

    def mark_dirty(self):
        """Marks queue data as dirty so next view refresh gets updated state."""
        self.is_dirty = True

    def refresh_queue(self, force: bool = False):
        """Fetches live alert data and metrics from SQLite and rebuilds the card list."""
        if not force and not self.is_dirty and self.has_loaded:
            return

        # 1. Update Top Summary Cards
        with SessionLocal() as session:
            metrics = review_actions.get_review_queue_summary_metrics(session)
            alerts = review_actions.get_alerts_for_queue(session, status_filter=self.current_filter)

        self.summary_panel.update_metrics(
            awaiting=metrics["awaiting_review"],
            escalated=metrics["escalated"],
            restricted=metrics["accounts_restricted"],
        )

        # Update tab label with live count
        self.tab_widget.setTabText(0, f"🚨 Needs Review ({metrics['awaiting_review']})")

        # 2. Clear Previous Cards
        while self.cards_layout.count() > 0:
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # 3. Handle Empty State
        if not alerts:
            empty_widget = self._create_empty_state_widget()
            self.cards_layout.addWidget(empty_widget)
            self.cards_layout.addStretch()
            self.is_dirty = False
            self.has_loaded = True
            return

        # 4. Populate Alert Cards
        for alert_obj in alerts:
            alert_dict = {
                "warning_id": alert_obj.warning_id,
                "alert_id": alert_obj.alert_id,
                "detection_run_id": alert_obj.detection_run_id,
                "rule_name": alert_obj.rule_name,
                "review_priority": alert_obj.review_priority,
                "verdict": alert_obj.verdict,
                "entity_type": alert_obj.entity_type,
                "entity_ref": alert_obj.entity_ref,
                "trigger_timestamp": alert_obj.trigger_timestamp,
                "window_start": alert_obj.window_start,
                "window_end": alert_obj.window_end,
                "threshold_value": alert_obj.threshold_value,
                "observed_value": alert_obj.observed_value,
                "evidence_summary": alert_obj.evidence_summary,
                "originating_bank": alert_obj.originating_bank,
                "destination_bank": alert_obj.destination_bank,
                "sender_account_ref": alert_obj.sender_account_ref,
                "receiver_account_ref": alert_obj.receiver_account_ref,
                "amount_paise": alert_obj.amount_paise,
                "payment_method": alert_obj.payment_method,
                "transaction_status": alert_obj.transaction_status,
                "device_token": alert_obj.device_token,
                "rules_triggered": alert_obj.rules_triggered,
                "linked_route_summary": alert_obj.linked_route_summary,
                "linked_transaction_ids": alert_obj.linked_transaction_ids,
                "review_status": alert_obj.review_status,
                "review_notes": alert_obj.review_notes,
                "reviewed_at": alert_obj.reviewed_at,
            }

            card = AlertCard(alert_dict, self)
            card.action_requested.connect(self._handle_card_action)
            card.inspect_requested.connect(self._open_inspect_dialog)
            self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()
        self.is_dirty = False
        self.has_loaded = True

    def _create_empty_state_widget(self) -> QWidget:
        """Creates the required informative empty state widget."""
        box = QFrame()
        box.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_PANEL_BG};
                border: 1px dashed {COLOR_BORDER};
                border-radius: 8px;
                padding: 40px;
            }}
        """)
        layout = QVBoxLayout(box)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)

        icon_lbl = QLabel("✅")
        icon_lbl.setStyleSheet("font-size: 36px; background: transparent;")
        icon_lbl.setAlignment(Qt.AlignCenter)

        msg_lbl = QLabel("No suspicious transactions currently require review.")
        msg_lbl.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLOR_TEXT_PRIMARY}; background: transparent;")
        msg_lbl.setAlignment(Qt.AlignCenter)

        desc_lbl = QLabel("All evaluated transactions have either cleared detection rules or have been resolved.\nClick below to screen newly arrived transactions against all 4 deterministic rules:")
        desc_lbl.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_MUTED}; background: transparent;")
        desc_lbl.setAlignment(Qt.AlignCenter)

        btn_screen = QPushButton("▶️ Run Fraud Detection on Warehouse Transactions")
        btn_screen.setObjectName("primaryButton")
        btn_screen.setMinimumHeight(36)
        btn_screen.clicked.connect(self.trigger_fraud_detection)

        layout.addWidget(icon_lbl)
        layout.addWidget(msg_lbl)
        layout.addWidget(desc_lbl)
        layout.addWidget(btn_screen)
        return box

    @Slot(str, str, str, str)
    def _handle_card_action(self, alert_id: str, action_type: str, account_ref: str, bank_code: str):
        with SessionLocal() as s:
            if action_type == "ACCOUNT_RESTRICTED":
                review_actions.restrict_account_simulated(
                    session=s,
                    bank_code=bank_code,
                    account_ref=account_ref,
                    reason=f"Restricted by investigator from Alert {alert_id}",
                    alert_id=alert_id,
                )
            else:
                review_actions.update_alert_status(
                    session=s,
                    alert_id=alert_id,
                    new_status=action_type,
                    notes=f"Investigator triage decision: {action_type}",
                )

        self.refresh_queue()

    @Slot(dict)
    def _open_inspect_dialog(self, alert_data: dict):
        dialog = AlertDetailsDialog(alert_data, self)
        dialog.action_submitted.connect(self._on_dialog_action)
        dialog.exec()

    @Slot(str, str, str, str, str)
    def _on_dialog_action(self, alert_id: str, status: str, notes: str, account_ref: str, bank_code: str):
        with SessionLocal() as s:
            if status == "ACCOUNT_RESTRICTED":
                review_actions.restrict_account_simulated(
                    session=s,
                    bank_code=bank_code,
                    account_ref=account_ref,
                    reason=notes or f"Restricted from Alert {alert_id}",
                    alert_id=alert_id,
                )
            else:
                review_actions.update_alert_status(
                    session=s,
                    alert_id=alert_id,
                    new_status=status,
                    notes=notes,
                )
        self.refresh_queue()

    def trigger_fraud_detection(self):
        """Launches the background detection worker."""
        if self.detection_worker and self.detection_worker.isRunning():
            return

        self.btn_run_detection.setEnabled(False)
        self.btn_run_detection.setText("Screening in Progress...")

        self.detection_worker = DetectionWorker(self)
        self.detection_worker.detection_completed.connect(self._on_detection_success)
        self.detection_worker.detection_failed.connect(self._on_detection_failure)
        self.detection_worker.start()

    @Slot(dict)
    def _on_detection_success(self, res: dict):
        self.btn_run_detection.setEnabled(True)
        self.btn_run_detection.setText("⚡ Run Fraud Screening")
        self.refresh_queue(force=True)
        self.screening_completed.emit()

        QMessageBox.information(
            self,
            "Screening Completed",
            f"Detection Run '{res['detection_run_id']}' Finished Successfully!\n\n"
            f"• Transactions Evaluated: {res['total_transactions_evaluated']:,}\n"
            f"• Suspicious Flagged: {res['total_flagged_transactions']:,}\n"
            f"• Alerts Generated: {res['total_warnings_generated']:,}\n"
            f"• Execution Time: {res['execution_duration_sec']:.3f}s"
        )

    @Slot(str)
    def _on_detection_failure(self, err_msg: str):
        self.btn_run_detection.setEnabled(True)
        self.btn_run_detection.setText("⚡ Run Fraud Screening")
        QMessageBox.critical(self, "Detection Failed", f"Screening error:\n{err_msg}")

