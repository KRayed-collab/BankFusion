"""
BankFusion Worker: Transaction Generation & Live Ingestion Worker
==================================================================
Simulates incoming banking transactions, executes the 7-stage ETL pipeline,
and runs screening asynchronously without freezing the UI.
"""

import time
import random
from datetime import datetime, timezone, timedelta
from PySide6.QtCore import QThread, Signal

from database.database_connection import SessionLocal
from database.database_models import (
    BankATransaction,
    BankBEvent,
    DimAccount,
    DimDevice,
)
from etl.run_etl_pipeline import execute_full_etl_pipeline
from fraud_detection.save_detection_results import execute_fraud_detection_run

IST = timezone(timedelta(hours=5, minutes=30))


class TransactionGenerationWorker(QThread):
    """Generates a synthetic live transaction, executes ETL, and updates detection."""

    generation_completed = Signal(str, dict)
    generation_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            now = datetime.now(IST)
            now_iso = now.isoformat()
            rand_id = f"SIM-{int(time.time() * 1000) % 1000000}"
            txn_id = f"A-TXN-{rand_id}"

            with SessionLocal() as s:
                # Pick accounts
                metro_accs = [
                    a.source_account_ref for a in
                    s.query(DimAccount).filter(DimAccount.bank_key == 1).limit(10).all()
                ]
                qpay_accs = [
                    a.source_account_ref for a in
                    s.query(DimAccount).filter(DimAccount.bank_key == 2).limit(10).all()
                ]
                devices = [
                    d.device_token for d in
                    s.query(DimDevice).filter(DimDevice.device_token != "UNKNOWN_DEVICE").limit(10).all()
                ]

                sender = random.choice(metro_accs) if metro_accs else "METRO-ACC-001"
                receiver = random.choice(qpay_accs) if qpay_accs else "QPAY-ACC-002"
                dev = random.choice(devices) if devices else "DEV-TOKEN-001"
                amt_paise = random.choice([45000, 120000, 250000, 750000, 1500000, 12000000])
                mode = random.choice(["UPI", "IMPS", "NEFT"])
                stat = random.choice(["SUCCESS", "SUCCESS", "SUCCESS", "FAILED"])

                new_record = BankATransaction(
                    transaction_id=txn_id,
                    transaction_timestamp=now_iso,
                    sender_account_ref=sender,
                    receiver_account_ref=receiver,
                    receiver_bank_code="QUICKPAY",
                    amount_paise=amt_paise,
                    payment_mode=mode,
                    transaction_status=stat,
                    device_token=dev,
                )
                s.add(new_record)
                s.commit()

            # Execute ETL pipeline
            etl_res = execute_full_etl_pipeline()

            # Execute Fraud Detection Run
            with SessionLocal() as s:
                det_res = execute_fraud_detection_run(s)

            self.generation_completed.emit(txn_id, {
                "etl": etl_res,
                "detection": det_res,
            })

        except Exception as e:
            self.generation_failed.emit(str(e))

