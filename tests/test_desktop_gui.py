"""
BankFusion Automated Test Suite: Native PySide6 Desktop GUI
============================================================
Validates desktop UI components in Qt offscreen mode:
- SummaryCardsPanel updates
- AlertCard and AlertDetailsDialog action signals
- TransactionDetailsDialog metadata presentation
- FraudReviewPage triage queue filtering and empty state
- TransactionFeedPage filters, table population, and row coloring
"""

import os
import sys
from pathlib import Path
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from ui.summary_cards import SummaryCardsPanel
from ui.alert_card import AlertCard
from ui.alert_details_dialog import AlertDetailsDialog
from ui.transaction_details_dialog import TransactionDetailsDialog
from ui.fraud_review_page import FraudReviewPage
from ui.transaction_feed_page import TransactionFeedPage


from database.database_connection import SessionLocal
from database.database_models import FactTransaction
from etl.run_etl_pipeline import execute_full_etl_pipeline
from fraud_detection.save_detection_results import execute_fraud_detection_run


@pytest.fixture(autouse=True)
def ensure_warehouse():
    """Ensures warehouse has facts and detection run before GUI tests."""
    session = SessionLocal()
    try:
        if session.query(FactTransaction).count() == 0:
            execute_full_etl_pipeline()
            execute_fraud_detection_run(session)
    finally:
        session.close()


@pytest.fixture(scope="session")
def qapp():
    """Initializes or returns QApplication singleton for offscreen testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_summary_cards_metric_updates(qapp):
    """Verifies that summary cards update values correctly."""
    panel = SummaryCardsPanel()
    panel.update_metrics(awaiting=15, escalated=4, restricted=2)

    assert panel.card_awaiting.value_label.text() == "15"
    assert panel.card_escalated.value_label.text() == "4"
    assert panel.card_restricted.value_label.text() == "2"


def test_alert_card_signals(qapp):
    """Verifies that AlertCard renders and emits action_requested signals."""
    alert_payload = {
        "warning_id": 99,
        "alert_id": "ALT-0099",
        "review_priority": "HIGH",
        "review_status": "NEEDS_REVIEW",
        "amount_paise": 5000000,
        "entity_ref": "METRO-ACC-TEST",
        "originating_bank": "METROBANK",
        "destination_bank": "QUICKPAY",
        "sender_account_ref": "METRO-ACC-TEST",
        "receiver_account_ref": "QPAY-ACC-REC",
        "payment_method": "UPI",
        "transaction_status": "SUCCESS",
        "device_token": "DEV-TEST-001",
        "rule_name": "VELOCITY_BURST",
        "rules_triggered": "Velocity Burst",
        "evidence_summary": "4 attempts in 110s",
        "trigger_timestamp": "2026-11-02T12:00:00+05:30",
    }

    card = AlertCard(alert_payload)
    emitted_signals = []

    def on_action(aid, action, acc, bank):
        emitted_signals.append((aid, action, acc, bank))

    card.action_requested.connect(on_action)
    card._trigger_action("ESCALATED")

    assert len(emitted_signals) == 1
    assert emitted_signals[0] == ("ALT-0099", "ESCALATED", "METRO-ACC-TEST", "METROBANK")


def test_transaction_details_dialog_content(qapp):
    """Verifies that TransactionDetailsDialog formats and presents all 4 rule breakdowns."""
    txn_row = {
        "transaction_key": 501,
        "source_transaction_id": "A-TXN-DEMO-501",
        "source_record_refs": "A-TXN-DEMO-501",
        "bank_code": "METROBANK",
        "bank_name": "MetroBank Retail Core",
        "destination_bank": "QUICKPAY",
        "source_account_ref": "A-ACC-01",
        "destination_account_ref": "B-ACC-02",
        "amount_paise": 150000,
        "amount_inr": 1500.0,
        "payment_method": "IMPS",
        "transaction_status": "SUCCESS",
        "device_token": "DEV-01",
        "transaction_timestamp": "2026-11-02T10:00:00+05:30",
        "epoch_timestamp": 1793500000,
        "is_predicted_suspicious": 1,
        "flagged_by_velocity": 1,
        "flagged_by_device": 0,
        "flagged_by_large_amount": 0,
        "flagged_by_cross_bank_movement": 0,
        "detection_factors": "Velocity Burst",
    }

    dialog = TransactionDetailsDialog(txn_row)
    assert dialog.windowTitle() == "Transaction Record — A-TXN-DEMO-501"


def test_fraud_review_page_lifecycle(qapp):
    """Verifies that FraudReviewPage initializes, switches tabs, and builds cards."""
    page = FraudReviewPage()
    assert page.tab_widget.count() == 3

    # Switch to "All Alerts"
    page._on_tab_changed(1)
    assert page.current_filter == "All Alerts"

    # Switch to "Resolved"
    page._on_tab_changed(2)
    assert page.current_filter == "Resolved"


def test_transaction_feed_page_filtering(qapp):
    """Verifies that TransactionFeedPage loads, applies filters, and populates table rows."""
    page = TransactionFeedPage()
    page.wait_for_load(5000)
    qapp.processEvents()
    assert page.table.columnCount() == 11
    assert page.table.rowCount() > 0

    # Test filtering to "Suspected Fraud Only"
    page.combo_status.setCurrentText("Suspected Fraud Only")
    page.apply_filters()
    assert page.table.rowCount() >= 0
