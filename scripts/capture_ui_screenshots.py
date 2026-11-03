"""
BankFusion Script: Capture UI Screenshots
=========================================
Renders all redesigned pages and modal dialogs across 1366x768, 1600x900,
and 1920x1080 resolutions in offscreen mode and exports PNG screenshots.
"""

import os
import sys
import shutil
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from ui.main_window import MainWindow
from ui.transaction_details_dialog import TransactionDetailsDialog
from ui.alert_details_dialog import AlertDetailsDialog
from ui.evaluation_dialog import EvaluationDialog
from ui.auto_blocked_page import ReleaseBlockDialog


ARTIFACTS_DIR = Path(r"C:\Users\RAYED KHAN\.gemini\antigravity\brain\58169ecf-b10b-4e7a-a6f9-2cf570ef829c")
SCREENSHOTS_DIR = PROJECT_ROOT / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def process_events_extensively(app, iterations=15, sleep_ms=30):
    for _ in range(iterations):
        app.processEvents()
        time.sleep(sleep_ms / 1000.0)


def capture_all():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    window = MainWindow()
    window.show()

    resolutions = [
        (1366, 768),
        (1600, 900),
        (1920, 1080),
    ]

    pages = [
        (0, "fraud_review_queue"),
        (1, "transaction_feed"),
        (2, "automatically_blocked"),
    ]

    captured_files = []

    for width, height in resolutions:
        window.resize(width, height)
        process_events_extensively(app)

        for page_idx, page_name in pages:
            window._on_navigate(page_idx)
            # Ensure feed has data loaded if on feed
            if page_idx == 1:
                window.page_feed.load_feed_data(force=True)
            elif page_idx == 0:
                window.page_queue.refresh_queue(force=True)
            elif page_idx == 2:
                window.page_blocked.refresh_data()

            process_events_extensively(app, iterations=20, sleep_ms=40)

            pixmap = window.grab()
            filename = f"{page_name}_{width}x{height}.png"
            dest_path = SCREENSHOTS_DIR / filename
            pixmap.save(str(dest_path), "PNG")
            captured_files.append(dest_path)
            print(f"Captured: {dest_path} ({width}x{height})")

            # Copy to artifacts directory
            if ARTIFACTS_DIR.exists():
                artifact_dest = ARTIFACTS_DIR / filename
                shutil.copy2(dest_path, artifact_dest)
                print(f"Copied to artifact: {artifact_dest}")

    # Capture Transaction Details Dialog
    sample_txn = {
        "transaction_key": 1042,
        "source_transaction_id": "METRO-TXN-20261103-09412",
        "source_record_refs": "A-TXN-09412",
        "bank_code": "METROBANK",
        "bank_name": "MetroBank Retail Core",
        "destination_bank": "QUICKPAY",
        "source_account_ref": "METRO-ACC-88412",
        "destination_account_ref": "QPAY-ACC-11029",
        "amount_paise": 15000000,
        "amount_inr": 150000.0,
        "payment_method": "IMPS",
        "transaction_status": "PENDING",
        "device_token": "DEV-TOK-7721-SHARED",
        "transaction_timestamp": "2026-11-03 21:15:32",
        "epoch_timestamp": 1793732132,
        "is_predicted_suspicious": 1,
        "flagged_by_velocity": 1,
        "flagged_by_device": 1,
        "flagged_by_large_amount": 1,
        "flagged_by_cross_bank_movement": 0,
    }
    txn_dlg = TransactionDetailsDialog(sample_txn)
    txn_dlg.resize(740, 580)
    txn_dlg.show()
    process_events_extensively(app)
    dlg_pix = txn_dlg.grab()
    dlg_path = SCREENSHOTS_DIR / "dialog_transaction_details.png"
    dlg_pix.save(str(dlg_path), "PNG")
    if ARTIFACTS_DIR.exists():
        shutil.copy2(dlg_path, ARTIFACTS_DIR / "dialog_transaction_details.png")
    txn_dlg.close()
    print("Captured: dialog_transaction_details.png")

    # Capture Alert Details Dialog
    sample_alert = {
        "alert_id": "ALT-20261103-088",
        "warning_id": 88,
        "detection_run_id": "RUN-20261103-210000",
        "rule_name": "Velocity Burst, Shared Device, Large Amount",
        "rules_triggered": "Velocity Burst, Shared Device, Large Amount",
        "review_priority": "HIGH",
        "review_status": "NEEDS_REVIEW",
        "verdict": "MULTI_FACTOR_SUSPICIOUS",
        "originating_bank": "METROBANK",
        "destination_bank": "QUICKPAY",
        "sender_account_ref": "METRO-ACC-88412",
        "receiver_account_ref": "QPAY-ACC-11029",
        "amount_paise": 15000000,
        "payment_method": "IMPS",
        "transaction_status": "SETTLED",
        "device_token": "DEV-TOK-7721-SHARED",
        "trigger_timestamp": "2026-11-03 21:15:32",
        "window_start": "2026-11-03 21:10:32",
        "window_end": "2026-11-03 21:15:32",
        "threshold_value": "3 distinct factors",
        "observed_value": "3 triggered factors",
        "evidence_summary": "4 rapid attempts in 118s; shared token across 3 customer accounts; ₹150,000 exceeds 3x median threshold (₹42,000).",
    }
    alert_dlg = AlertDetailsDialog(sample_alert)
    alert_dlg.resize(760, 640)
    alert_dlg.show()
    process_events_extensively(app)
    alert_pix = alert_dlg.grab()
    alert_path = SCREENSHOTS_DIR / "dialog_alert_details.png"
    alert_pix.save(str(alert_path), "PNG")
    if ARTIFACTS_DIR.exists():
        shutil.copy2(alert_path, ARTIFACTS_DIR / "dialog_alert_details.png")
    alert_dlg.close()
    print("Captured: dialog_alert_details.png")

    # Capture Evaluation Dialog
    eval_dlg = EvaluationDialog()
    eval_dlg.resize(880, 680)
    eval_dlg.show()
    process_events_extensively(app)
    eval_pix = eval_dlg.grab()
    eval_path = SCREENSHOTS_DIR / "dialog_evaluation_metrics.png"
    eval_pix.save(str(eval_path), "PNG")
    if ARTIFACTS_DIR.exists():
        shutil.copy2(eval_path, ARTIFACTS_DIR / "dialog_evaluation_metrics.png")
    eval_dlg.close()
    print("Captured: dialog_evaluation_metrics.png")

    window.close()
    print("\nAll screenshots captured successfully!")


if __name__ == "__main__":
    capture_all()

