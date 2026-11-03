"""
BankFusion Controlled Fraud Demonstration Scenario: Three-Factor Auto-Block
=============================================================================
Deliberately generates a realistic, reproducible high-risk multi-factor transaction
that triggers exactly THREE distinct fraud rules simultaneously:

1. Rule 1 (Velocity Burst): Target account initiates 4 payment attempts within 3 minutes (<= 300s).
2. Rule 2 (Shared Device Abuse): 3 distinct sending accounts use the same device token within 24 hours.
3. Rule 3 (Unusually Large Amount): Target transaction is Rs. 1,50,000 (15,000,000 paise),
   which exceeds 3x historical median (Rs. 2,000) and the Rs. 50,000 floor (as well as Rs. 1,00,000 fallback).
4. Rule 4 (Cross-Bank Movement): 0 (Clean).

Total distinct triggered factors = 3 -> AUTO_BLOCKED (Tier 3).
The target transaction initiates as PENDING, is screened before simulated completion,
is prevented from completing (remains PENDING), and is persisted into
transaction_enforcement_record with is_active_block = 1.
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from database.database_connection import SessionLocal
from database.database_models import (
    BankATransaction,
    FactTransaction,
    DimTransactionStatus,
    TransactionEnforcementRecord,
)
from etl.run_etl_pipeline import execute_full_etl_pipeline
from fraud_detection.save_detection_results import execute_fraud_detection_run

IST = timezone(timedelta(hours=5, minutes=30))
logger = logging.getLogger("BankFusion.ControlledDemo")


def inject_controlled_auto_block_scenario(session=None) -> Dict[str, Any]:
    """
    Executes the controlled demonstration scenario.
    Returns summary details including the target transaction ID and enforcement outcome.
    """
    start_wall = time.time()
    now_dt = datetime.now(IST)
    anchor_ts = int(now_dt.timestamp())
    slug = f"{int(anchor_ts) % 1000000}-{int(time.time() * 1000) % 1000}"

    shared_dev_token = f"SIM-DEV-MULTI-{slug}"
    snd_acc_1 = f"A-ACC-SND1-{slug}"
    snd_acc_2 = f"A-ACC-SND2-{slug}"
    target_acc = f"A-ACC-TARGET-{slug}"
    receiver_acc = "B-ACC-0001"

    records_to_insert: List[BankATransaction] = []

    # -------------------------------------------------------------------------
    # 1. Accounts 1 & 2 use shared_dev_token earlier in the 24-hr window (Rule 2 setup)
    # -------------------------------------------------------------------------
    t1_iso = datetime.fromtimestamp(anchor_ts - 600, tz=IST).isoformat()
    records_to_insert.append(
        BankATransaction(
            transaction_id=f"A-TXN-DEV1-{slug}",
            transaction_timestamp=t1_iso,
            sender_account_ref=snd_acc_1,
            receiver_account_ref=receiver_acc,
            receiver_bank_code="QUICKPAY",
            amount_paise=100000,  # Rs. 1,000
            payment_mode="UPI",
            transaction_status="SUCCESS",
            device_token=shared_dev_token,
        )
    )

    t2_iso = datetime.fromtimestamp(anchor_ts - 400, tz=IST).isoformat()
    records_to_insert.append(
        BankATransaction(
            transaction_id=f"A-TXN-DEV2-{slug}",
            transaction_timestamp=t2_iso,
            sender_account_ref=snd_acc_2,
            receiver_account_ref=receiver_acc,
            receiver_bank_code="QUICKPAY",
            amount_paise=100000,  # Rs. 1,000
            payment_mode="UPI",
            transaction_status="SUCCESS",
            device_token=shared_dev_token,
        )
    )

    # -------------------------------------------------------------------------
    # 2. Target account historical baseline: 5 preceding transactions (Rule 3 setup)
    #    Median = Rs. 2,000 (200,000 paise)
    # -------------------------------------------------------------------------
    for d in [10, 8, 6, 4, 2]:
        hist_iso = datetime.fromtimestamp(anchor_ts - (d * 86400), tz=IST).isoformat()
        records_to_insert.append(
            BankATransaction(
                transaction_id=f"A-TXN-HIST{d}-{slug}",
                transaction_timestamp=hist_iso,
                sender_account_ref=target_acc,
                receiver_account_ref=receiver_acc,
                receiver_bank_code="QUICKPAY",
                amount_paise=200000,  # Rs. 2,000
                payment_mode="UPI",
                transaction_status="SUCCESS",
                device_token=f"SIM-DEV-NORMAL-{slug}",
            )
        )

    # -------------------------------------------------------------------------
    # 3. Target account rapid velocity attempts within 3 minutes (Rule 1 setup)
    # -------------------------------------------------------------------------
    vel_intervals = [150, 100, 50]  # seconds before anchor
    for idx, sec_offset in enumerate(vel_intervals, start=1):
        v_iso = datetime.fromtimestamp(anchor_ts - sec_offset, tz=IST).isoformat()
        records_to_insert.append(
            BankATransaction(
                transaction_id=f"A-TXN-VEL{idx}-{slug}",
                transaction_timestamp=v_iso,
                sender_account_ref=target_acc,
                receiver_account_ref=receiver_acc,
                receiver_bank_code="QUICKPAY",
                amount_paise=200000,  # Rs. 2,000
                payment_mode="UPI",
                transaction_status="SUCCESS" if idx == 1 else "FAILED",
                device_token=shared_dev_token,
            )
        )

    # -------------------------------------------------------------------------
    # 4. Target Transaction (Attempt #4 in 5-min window, 3rd account on device,
    #    unusually large amount Rs. 1,50,000, initiates as PENDING)
    # -------------------------------------------------------------------------
    target_txn_id = f"A-TXN-TARGET-AUTOBLK-{slug}"
    target_iso = datetime.fromtimestamp(anchor_ts, tz=IST).isoformat()
    target_amount_paise = 15000000  # Rs. 1,50,000

    records_to_insert.append(
        BankATransaction(
            transaction_id=target_txn_id,
            transaction_timestamp=target_iso,
            sender_account_ref=target_acc,
            receiver_account_ref=receiver_acc,
            receiver_bank_code="QUICKPAY",
            amount_paise=target_amount_paise,
            payment_mode="IMPS",
            transaction_status="PENDING",
            device_token=shared_dev_token,
        )
    )

    # Ingest records to Bank A table
    with SessionLocal() as s:
        for rec in records_to_insert:
            s.add(rec)
        s.commit()

    # Stage 5: Execute full ETL pipeline to resolve surrogate keys & load warehouse
    etl_result = execute_full_etl_pipeline()

    # Stage 6: Execute Fraud Detection & Enforcement Screening
    with SessionLocal() as s:
        detection_result = execute_fraud_detection_run(s)

        # Retrieve enforcement record for target transaction
        target_enforcement = (
            s.query(TransactionEnforcementRecord)
            .filter_by(source_transaction_id=target_txn_id)
            .first()
        )

        target_fact = (
            s.query(FactTransaction)
            .filter_by(source_transaction_id=target_txn_id)
            .first()
        )

        status_code = "UNKNOWN"
        if target_fact:
            st = s.query(DimTransactionStatus).filter_by(status_key=target_fact.status_key).first()
            if st:
                status_code = st.status_code

        enforcement_status = target_enforcement.enforcement_status if target_enforcement else "NONE"
        factor_count = target_enforcement.triggered_factor_count if target_enforcement else 0
        factors_summary = target_enforcement.triggered_factors_summary if target_enforcement else "None"
        is_active = target_enforcement.is_active_block if target_enforcement else 0

        # Pre-completion verification:
        # Since enforcement_status == "AUTO_BLOCKED", simulated completion is prevented.
        # Status must remain PENDING.
        source_rec = s.query(BankATransaction).filter_by(transaction_id=target_txn_id).first()
        source_status = source_rec.transaction_status if source_rec else "UNKNOWN"

    duration = round(time.time() - start_wall, 3)

    summary = {
        "success": True,
        "target_transaction_id": target_txn_id,
        "target_account": target_acc,
        "shared_device": shared_dev_token,
        "amount_inr": target_amount_paise / 100.0,
        "enforcement_status": enforcement_status,
        "triggered_factor_count": factor_count,
        "triggered_factors_summary": factors_summary,
        "is_active_block": is_active,
        "fact_status": status_code,
        "source_status": source_status,
        "duration_sec": duration,
        "etl_summary": etl_result,
        "detection_summary": detection_result,
    }

    logger.info(
        f"[CONTROLLED_DEMO] Completed in {duration}s | Target: {target_txn_id} | "
        f"Enforcement: {enforcement_status} | Factors: {factor_count} ({factors_summary}) | "
        f"ActiveBlock: {is_active} | FactStatus: {status_code}"
    )

    return summary

