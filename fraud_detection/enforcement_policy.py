"""
BankFusion Three-Tier Fraud Risk Enforcement Policy & Lifecycle Management
==========================================================================
Implements the deterministic three-tier risk handling model:

Tier 1: 0 distinct triggered factors -> CLEAR
        - Simulated transaction completes normally (SUCCESS).
        - Displayed as green in feeds.

Tier 2: 1-2 distinct triggered factors -> REVIEW_PENDING
        - Routed to human operators in Fraud Review Queue.
        - Transaction held in PENDING status.
        - Operator options: Legitimate (releases hold), Suspicious (MANUALLY_BLOCKED), Escalate.
        - Displayed as amber/warning.

Tier 3: 3-4 distinct triggered factors (configurable threshold >= 3) -> AUTO_BLOCKED
        - Automatically prevented from completing (held in PENDING/BLOCKED).
        - Displayed in dedicated Automatically Blocked Transactions page (red).
        - Operator can release with mandatory operator identity and reason -> RELEASED (blue).
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.path_resolver import get_config_path
from database.database_models import (
    TransactionEnforcementRecord,
    EnforcementAuditLog,
    FraudTransactionPrediction,
    FactTransaction,
    DimTransactionStatus,
    BankATransaction,
    BankBEvent,
    BankCLedgerEntry,
)


def get_auto_block_threshold() -> int:
    """Loads auto_block_rule_count from configuration with fallback to 3."""
    cfg_path = get_config_path("detection_thresholds.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return int(data.get("enforcement_policy", {}).get("auto_block_rule_count", 3))
    except Exception:
        return 3


def determine_enforcement_decision(
    flagged_by_velocity: int,
    flagged_by_device: int,
    flagged_by_large_amount: int,
    flagged_by_cross_bank_movement: int,
    auto_block_threshold: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Evaluates individual detection flags and returns the deterministic 3-tier risk decision.
    """
    if auto_block_threshold is None:
        auto_block_threshold = get_auto_block_threshold()

    factors = []
    if flagged_by_velocity:
        factors.append("Velocity Burst")
    if flagged_by_device:
        factors.append("Shared Device")
    if flagged_by_large_amount:
        factors.append("Large Amount")
    if flagged_by_cross_bank_movement:
        factors.append("Cross-Bank Movement")

    factor_count = len(factors)
    summary_str = ", ".join(factors) if factors else "None (Clean)"

    if factor_count == 0:
        return {
            "risk_tier": "CLEAR",
            "enforcement_status": "CLEAR",
            "triggered_factor_count": 0,
            "triggered_factors_summary": summary_str,
            "blocking_reason": None,
            "is_active_block": 0,
        }
    elif factor_count < auto_block_threshold:
        return {
            "risk_tier": "LOW" if factor_count == 1 else "MEDIUM",
            "enforcement_status": "REVIEW_PENDING",
            "triggered_factor_count": factor_count,
            "triggered_factors_summary": summary_str,
            "blocking_reason": f"Routing to manual triage: {factor_count} factor(s) triggered ({summary_str})",
            "is_active_block": 0,
        }
    else:
        return {
            "risk_tier": "HIGH",
            "enforcement_status": "AUTO_BLOCKED",
            "triggered_factor_count": factor_count,
            "triggered_factors_summary": summary_str,
            "blocking_reason": f"Deterministic auto-block triggered by {factor_count} distinct factors: {summary_str}",
            "is_active_block": 1,
        }


def apply_enforcement_for_detection_run(
    session: Session,
    detection_run_id: str,
    predictions: List[FraudTransactionPrediction],
) -> Dict[str, int]:
    """
    Applies the three-tier enforcement policy for all predictions in a detection run.
    Preserves manual operator overrides if previously executed.
    """
    now_str = datetime.now().isoformat()
    threshold = get_auto_block_threshold()

    counts = {
        "CLEAR": 0,
        "REVIEW_PENDING": 0,
        "AUTO_BLOCKED": 0,
        "PRESERVED_OVERRIDE": 0,
    }

    # Fetch existing enforcement records for these transaction keys
    txn_keys = [p.transaction_key for p in predictions]
    existing_records = {
        r.transaction_key: r
        for r in session.query(TransactionEnforcementRecord)
        .filter(TransactionEnforcementRecord.transaction_key.in_(txn_keys))
        .all()
    }

    for p in predictions:
        decision = determine_enforcement_decision(
            flagged_by_velocity=p.flagged_by_velocity,
            flagged_by_device=p.flagged_by_device,
            flagged_by_large_amount=p.flagged_by_large_amount,
            flagged_by_cross_bank_movement=p.flagged_by_cross_bank_movement,
            auto_block_threshold=threshold,
        )

        existing = existing_records.get(p.transaction_key)
        if existing:
            # Preserve operator decisions: RELEASED, MANUALLY_BLOCKED, ESCALATED
            if existing.enforcement_status in ("RELEASED", "MANUALLY_BLOCKED", "ESCALATED"):
                counts["PRESERVED_OVERRIDE"] += 1
                continue

            # Update enforcement record
            old_status = existing.enforcement_status
            new_status = decision["enforcement_status"]
            existing.detection_run_id = detection_run_id
            existing.risk_tier = decision["risk_tier"]
            existing.enforcement_status = new_status
            existing.triggered_factor_count = decision["triggered_factor_count"]
            existing.triggered_factors_summary = decision["triggered_factors_summary"]
            existing.blocking_reason = decision["blocking_reason"]
            existing.is_active_block = decision["is_active_block"]
            if new_status == "AUTO_BLOCKED" and not existing.blocked_at:
                existing.blocked_at = now_str

            if old_status != new_status:
                log_entry = EnforcementAuditLog(
                    transaction_key=p.transaction_key,
                    source_transaction_id=p.source_transaction_id,
                    detection_run_id=detection_run_id,
                    previous_status=old_status,
                    new_status=new_status,
                    action_type="POLICY_RE_EVALUATION",
                    operator_id="SYSTEM",
                    action_reason=decision["blocking_reason"],
                    timestamp=now_str,
                )
                session.add(log_entry)

            counts[new_status] = counts.get(new_status, 0) + 1
        else:
            new_status = decision["enforcement_status"]
            rec = TransactionEnforcementRecord(
                transaction_key=p.transaction_key,
                source_bank_code=p.source_bank_code,
                source_transaction_id=p.source_transaction_id,
                detection_run_id=detection_run_id,
                enforcement_status=new_status,
                risk_tier=decision["risk_tier"],
                triggered_factor_count=decision["triggered_factor_count"],
                triggered_factors_summary=decision["triggered_factors_summary"],
                blocking_reason=decision["blocking_reason"],
                is_active_block=decision["is_active_block"],
                created_at=now_str,
                blocked_at=now_str if new_status == "AUTO_BLOCKED" else None,
            )
            session.add(rec)

            log_entry = EnforcementAuditLog(
                transaction_key=p.transaction_key,
                source_transaction_id=p.source_transaction_id,
                detection_run_id=detection_run_id,
                previous_status="NONE",
                new_status=new_status,
                action_type="INITIAL_EVALUATION",
                operator_id="SYSTEM",
                action_reason=decision["blocking_reason"],
                timestamp=now_str,
            )
            session.add(log_entry)
            counts[new_status] = counts.get(new_status, 0) + 1

    session.flush()
    return counts


def release_enforcement_transaction(
    session: Session,
    transaction_key: int,
    operator_id: str,
    release_reason: str,
) -> Dict[str, Any]:
    """
    Operator action to release an automatically blocked or held transaction.
    - Requires non-empty release reason and operator ID.
    - Updates enforcement status to RELEASED and sets is_active_block = 0.
    - Writes immutable record to EnforcementAuditLog.
    - If the simulated transaction was held PENDING, transitions status to SUCCESS.
    """
    if not operator_id or not operator_id.strip():
        raise ValueError("Operator ID is required to release an enforcement hold.")
    if not release_reason or not release_reason.strip():
        raise ValueError("A documented release justification reason is required.")

    rec = (
        session.query(TransactionEnforcementRecord)
        .filter_by(transaction_key=transaction_key)
        .first()
    )
    if not rec:
        raise ValueError(f"No enforcement record found for transaction_key: {transaction_key}")

    now_str = datetime.now().isoformat()
    old_status = rec.enforcement_status

    rec.enforcement_status = "RELEASED"
    rec.is_active_block = 0
    rec.released_at = now_str
    rec.released_by = operator_id.strip()
    rec.release_reason = release_reason.strip()

    # Immutable audit log
    audit = EnforcementAuditLog(
        transaction_key=rec.transaction_key,
        source_transaction_id=rec.source_transaction_id,
        detection_run_id=rec.detection_run_id,
        previous_status=old_status,
        new_status="RELEASED",
        action_type="OPERATOR_RELEASE",
        operator_id=operator_id.strip(),
        action_reason=release_reason.strip(),
        timestamp=now_str,
    )
    session.add(audit)

    # Transition simulated pending status to SUCCESS
    _complete_simulated_transaction_hold(session, rec.transaction_key, rec.source_bank_code, rec.source_transaction_id)

    session.commit()
    return {
        "success": True,
        "transaction_key": transaction_key,
        "previous_status": old_status,
        "new_status": "RELEASED",
        "released_at": now_str,
        "released_by": operator_id.strip(),
    }


def _complete_simulated_transaction_hold(
    session: Session,
    transaction_key: int,
    source_bank_code: str,
    source_transaction_id: str,
) -> None:
    """Helper to update PENDING status to SUCCESS across warehouse and source tables."""
    # Find SUCCESS status member
    success_status = (
        session.query(DimTransactionStatus)
        .filter_by(status_code="SUCCESS")
        .first()
    )

    if success_status:
        fact = (
            session.query(FactTransaction)
            .filter_by(transaction_key=transaction_key)
            .first()
        )
        if fact:
            # Check if current fact status is PENDING
            current_status = session.query(DimTransactionStatus).filter_by(status_key=fact.status_key).first()
            if current_status and current_status.status_code == "PENDING":
                fact.status_key = success_status.status_key

    # Also update source bank record if it was held as PENDING
    if source_bank_code == "BANK_A":
        bank_rec = session.query(BankATransaction).filter_by(transaction_id=source_transaction_id).first()
        if bank_rec and bank_rec.transaction_status == "PENDING":
            bank_rec.transaction_status = "SUCCESS"
    elif source_bank_code == "BANK_B":
        bank_rec = session.query(BankBEvent).filter_by(event_id=source_transaction_id).first()
        if bank_rec and bank_rec.payment_status == "PENDING":
            bank_rec.payment_status = "SUCCESS"
    elif source_bank_code == "BANK_C":
        bank_rec = session.query(BankCLedgerEntry).filter_by(entry_id=source_transaction_id).first()
        if bank_rec and bank_rec.posting_status == "PENDING":
            bank_rec.posting_status = "POSTED"

