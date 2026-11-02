"""
BankFusion Warehouse Query & Dimension Resolution Engine
=========================================================
Provides helper functions for:
1. Dynamic dimension member resolution (Date, Account, Device)
2. Cached in-memory dimension key lookups for high-throughput ETL
3. Denormalized SQL queries joining FactTransaction with all 7 dimensions
4. Star-schema metadata and summary aggregations
5. Unified transaction feed dataframe with latest fraud predictions
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.database_models import (
    DimBank,
    DimAccount,
    DimDate,
    DimTime,
    DimPaymentMethod,
    DimTransactionStatus,
    DimDevice,
    FactTransaction,
    FraudTransactionPrediction,
    FraudDetectionRun,
)


def ensure_dim_date(session: Session, dt: datetime) -> int:
    """
    Ensures that a date dimension member exists for the given datetime.
    Returns the integer date_key (YYYYMMDD).
    """
    date_key = dt.year * 10000 + dt.month * 100 + dt.day
    full_date = dt.strftime("%Y-%m-%d")

    existing = session.query(DimDate).filter_by(date_key=date_key).first()
    if not existing:
        month_name = dt.strftime("%B")
        quarter = (dt.month - 1) // 3 + 1
        is_weekend = 1 if dt.weekday() in [5, 6] else 0

        dim_date = DimDate(
            date_key=date_key,
            full_date=full_date,
            day_of_month=dt.day,
            month=dt.month,
            month_name=month_name,
            quarter=quarter,
            year=dt.year,
            is_weekend=is_weekend,
        )
        session.add(dim_date)
        session.flush()

    return date_key


def resolve_account_key(
    session: Session,
    bank_key: int,
    source_account_ref: str,
    customer_id: str = "UNKNOWN_CUST",
    account_type: str = "SAVINGS",
    created_at: str = "2026-01-01T00:00:00+05:30",
) -> int:
    """
    Resolves the surrogate account_key for composite identity (bank_key, source_account_ref).
    Inserts a new dimension row if not present.
    """
    acc = (
        session.query(DimAccount)
        .filter_by(bank_key=bank_key, source_account_ref=source_account_ref)
        .first()
    )
    if not acc:
        acc = DimAccount(
            bank_key=bank_key,
            source_account_ref=source_account_ref,
            customer_id=customer_id,
            account_type=account_type,
            created_at=created_at,
        )
        session.add(acc)
        session.flush()

    return acc.account_key


def resolve_device_key(session: Session, device_token: Optional[str]) -> int:
    """
    Resolves the surrogate device_key.
    Maps None or empty tokens to surrogate 'UNKNOWN_DEVICE' (key 1).
    """
    token = device_token.strip() if device_token else "UNKNOWN_DEVICE"
    dev = session.query(DimDevice).filter_by(device_token=token).first()
    if not dev:
        dev = DimDevice(device_token=token, is_known=1 if token != "UNKNOWN_DEVICE" else 0)
        session.add(dev)
        session.flush()

    return dev.device_key


def load_dimension_cache(session: Session) -> Dict[str, Any]:
    """
    Preloads dimension lookup maps into memory to optimize bulk ETL resolution.
    """
    banks = {b.bank_code: b.bank_key for b in session.query(DimBank).all()}
    methods = {m.method_code: m.payment_method_key for m in session.query(DimPaymentMethod).all()}
    statuses = {s.status_code: s.status_key for s in session.query(DimTransactionStatus).all()}
    devices = {d.device_token: d.device_key for d in session.query(DimDevice).all()}
    accounts = {
        (a.bank_key, a.source_account_ref): a.account_key
        for a in session.query(DimAccount).all()
    }

    return {
        "banks": banks,
        "methods": methods,
        "statuses": statuses,
        "devices": devices,
        "accounts": accounts,
    }


def get_denormalized_fact_dataframe(
    session: Session,
    batch_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    """
    Returns a fully denormalized Pandas DataFrame joining FactTransaction with all 7 dimensions.
    This provides the operational dataset for OLAP slicing/dicing and rule evaluation.
    """
    query = (
        session.query(
            FactTransaction.transaction_key,
            FactTransaction.source_transaction_id,
            FactTransaction.source_record_refs,
            FactTransaction.transaction_timestamp,
            FactTransaction.epoch_timestamp,
            FactTransaction.amount_paise,
            FactTransaction.currency,
            FactTransaction.source_batch_id,
            DimBank.bank_code,
            DimBank.bank_name,
            DimBank.bank_type,
            DimDate.date_key,
            DimDate.full_date,
            DimDate.month_name,
            DimDate.quarter,
            DimDate.year,
            DimTime.time_key,
            DimTime.hour,
            DimTime.minute,
            DimTime.time_of_day,
            FactTransaction.source_account_key,
            FactTransaction.destination_account_key,
            DimPaymentMethod.method_code.label("payment_method"),
            DimPaymentMethod.method_category,
            DimTransactionStatus.status_code.label("transaction_status"),
            DimTransactionStatus.is_terminal,
            DimDevice.device_token,
            DimDevice.is_known.label("is_device_known"),
        )
        .join(DimBank, FactTransaction.bank_key == DimBank.bank_key)
        .join(DimDate, FactTransaction.date_key == DimDate.date_key)
        .join(DimTime, FactTransaction.time_key == DimTime.time_key)
        .join(DimPaymentMethod, FactTransaction.payment_method_key == DimPaymentMethod.payment_method_key)
        .join(DimTransactionStatus, FactTransaction.status_key == DimTransactionStatus.status_key)
        .join(DimDevice, FactTransaction.device_key == DimDevice.device_key)
    )

    if batch_id:
        query = query.filter(FactTransaction.source_batch_id == batch_id)

    query = query.order_by(FactTransaction.epoch_timestamp.asc())

    if limit:
        query = query.limit(limit)

    records = query.all()
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame([r._asdict() for r in records])

    # Join sender and receiver account natural refs
    acc_map = {
        a.account_key: a.source_account_ref
        for a in session.query(DimAccount.account_key, DimAccount.source_account_ref).all()
    }
    df["source_account_ref"] = df["source_account_key"].map(acc_map)
    df["destination_account_ref"] = df["destination_account_key"].map(acc_map)

    # Convert paise to rupees for display
    df["amount_inr"] = df["amount_paise"] / 100.0

    return df


def get_transaction_feed_dataframe(
    session: Session,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    """
    Returns denormalized transaction rows enriched with the latest fraud screening predictions.
    Ordered reverse chronologically (newest transactions first) for live feed monitoring.
    """
    df = get_denormalized_fact_dataframe(session)
    if df.empty:
        return pd.DataFrame()

    # Find the most recent fraud detection run
    latest_run = (
        session.query(FraudDetectionRun)
        .order_by(FraudDetectionRun.run_timestamp.desc())
        .first()
    )

    preds_map = {}
    if latest_run:
        preds = (
            session.query(FraudTransactionPrediction)
            .filter_by(detection_run_id=latest_run.detection_run_id)
            .all()
        )
        for p in preds:
            preds_map[p.transaction_key] = {
                "flagged_by_velocity": p.flagged_by_velocity,
                "flagged_by_device": p.flagged_by_device,
                "flagged_by_large_amount": p.flagged_by_large_amount,
                "flagged_by_cross_bank_movement": p.flagged_by_cross_bank_movement,
                "is_predicted_suspicious": p.is_predicted_suspicious,
            }

    # Attach prediction columns
    v_list, d_list, l_list, c_list, susp_list, factors_list = [], [], [], [], [], []
    for _, row in df.iterrows():
        tk = row["transaction_key"]
        p_info = preds_map.get(tk, {
            "flagged_by_velocity": 0,
            "flagged_by_device": 0,
            "flagged_by_large_amount": 0,
            "flagged_by_cross_bank_movement": 0,
            "is_predicted_suspicious": 0,
        })
        v = p_info["flagged_by_velocity"]
        d = p_info["flagged_by_device"]
        l = p_info["flagged_by_large_amount"]
        c = p_info["flagged_by_cross_bank_movement"]
        susp = p_info["is_predicted_suspicious"]

        v_list.append(v)
        d_list.append(d)
        l_list.append(l)
        c_list.append(c)
        susp_list.append(susp)

        factors = []
        if v:
            factors.append("Velocity Burst")
        if d:
            factors.append("Shared Device")
        if l:
            factors.append("Large Amount")
        if c:
            factors.append("Cross-Bank Movement")

        factors_list.append(", ".join(factors) if factors else "None (Clean)")

    df["flagged_by_velocity"] = v_list
    df["flagged_by_device"] = d_list
    df["flagged_by_large_amount"] = l_list
    df["flagged_by_cross_bank_movement"] = c_list
    df["is_predicted_suspicious"] = susp_list
    df["detection_factors"] = factors_list

    # Determine destination bank from account ref prefix or fallback
    dest_banks = []
    for _, row in df.iterrows():
        dest_acc = str(row.get("destination_account_ref") or "")
        if dest_acc.startswith("METRO-") or dest_acc.startswith("A-"):
            dest_banks.append("METROBANK")
        elif dest_acc.startswith("QPAY-") or dest_acc.startswith("B-"):
            dest_banks.append("QUICKPAY")
        elif dest_acc.startswith("TRUST-") or dest_acc.startswith("C-"):
            dest_banks.append("TRUSTLINE")
        else:
            dest_banks.append(row["bank_code"])
    df["destination_bank"] = dest_banks

    # Reverse chronological sort (latest transactions first)
    df = df.sort_values(by=["epoch_timestamp", "transaction_key"], ascending=[False, False]).reset_index(drop=True)

    if limit:
        df = df.head(limit)

    return df


def get_warehouse_summary_metrics(session: Session) -> Dict[str, Any]:
    """Calculates high-level warehouse key performance indicators."""
    total_txns = session.query(func.count(FactTransaction.transaction_key)).scalar() or 0
    total_paise = session.query(func.sum(FactTransaction.amount_paise)).scalar() or 0

    success_txns = (
        session.query(func.count(FactTransaction.transaction_key))
        .join(DimTransactionStatus)
        .filter(DimTransactionStatus.status_code == "SUCCESS")
        .scalar()
        or 0
    )
    failed_txns = (
        session.query(func.count(FactTransaction.transaction_key))
        .join(DimTransactionStatus)
        .filter(DimTransactionStatus.status_code == "FAILED")
        .scalar()
        or 0
    )

    return {
        "total_transactions": total_txns,
        "total_volume_paise": total_paise,
        "total_volume_inr": total_paise / 100.0,
        "successful_transactions": success_txns,
        "failed_transactions": failed_txns,
        "total_accounts": session.query(func.count(DimAccount.account_key)).scalar() or 0,
        "total_devices": session.query(func.count(DimDevice.device_key)).scalar() or 0,
    }
