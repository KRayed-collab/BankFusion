"""
BankFusion Review Actions & Case Status Management
==================================================
Manages investigator actions on alerts in the Fraud Review Queue:
- Mark as Legitimate
- Confirm as Suspicious
- Escalate for Investigation
- Restrict Account (simulation only)
- Persists all state updates to SQLite.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.database_models import (
    FraudScreeningWarning,
    SimulatedRestrictedAccount,
    TransactionEnforcementRecord,
    EnforcementAuditLog,
)
from fraud_detection.enforcement_policy import _complete_simulated_transaction_hold


def get_review_queue_summary_metrics(session: Session) -> Dict[str, int]:
    """
    Returns actual counts from SQLite for the top 3 summary cards:
    1. Awaiting Review (unresolved alerts with review_status='NEEDS_REVIEW')
    2. Escalated (alerts escalated for investigation with review_status='ESCALATED')
    3. Resolved Alerts (alerts marked legitimate or suspicious)
    """
    awaiting = session.query(FraudScreeningWarning).filter_by(review_status="NEEDS_REVIEW").count()
    escalated = session.query(FraudScreeningWarning).filter_by(review_status="ESCALATED").count()
    resolved = session.query(FraudScreeningWarning).filter(
        FraudScreeningWarning.review_status.in_(["LEGITIMATE", "SUSPICIOUS", "RESOLVED"])
    ).count()
    restricted = session.query(SimulatedRestrictedAccount).count()

    return {
        "awaiting_review": awaiting,
        "escalated": escalated,
        "resolved": resolved,
        "accounts_restricted": restricted,
    }


def update_alert_status(
    session: Session,
    alert_id: str,
    new_status: str,
    notes: Optional[str] = None,
    operator_id: str = "OPERATOR",
) -> bool:
    """
    Updates the review status of an alert in the database and synchronizes
    transaction enforcement state and audit logs.
    Status choices: 'NEEDS_REVIEW', 'LEGITIMATE', 'SUSPICIOUS', 'ESCALATED', 'ACCOUNT_RESTRICTED'
    """
    warning_int = int(alert_id) if str(alert_id).isdigit() else -1
    alert = (
        session.query(FraudScreeningWarning)
        .filter(
            or_(
                FraudScreeningWarning.alert_id == str(alert_id),
                FraudScreeningWarning.warning_id == warning_int,
            )
        )
        .first()
    )
    if not alert:
        return False

    now_str = datetime.now().isoformat()
    old_alert_status = alert.review_status
    alert.review_status = new_status
    alert.reviewed_at = now_str
    if notes:
        alert.review_notes = notes

    # Synchronize transaction enforcement records for linked transactions
    linked_str = alert.linked_transaction_ids or ""
    linked_keys = [int(k) for k in linked_str.split(",") if k.strip().isdigit()]

    for tk in linked_keys:
        enf = session.query(TransactionEnforcementRecord).filter_by(transaction_key=tk).first()
        if not enf:
            continue

        old_enf_status = enf.enforcement_status
        if new_status == "LEGITIMATE":
            enf.enforcement_status = "RELEASED"
            enf.is_active_block = 0
            enf.released_at = now_str
            enf.released_by = operator_id
            enf.release_reason = notes or "Marked legitimate in review queue"
            _complete_simulated_transaction_hold(session, enf.transaction_key, enf.source_bank_code, enf.source_transaction_id)
            action_type = "OPERATOR_REVIEW_LEGITIMATE"
        elif new_status == "SUSPICIOUS":
            enf.enforcement_status = "MANUALLY_BLOCKED"
            enf.is_active_block = 1
            enf.blocking_reason = notes or "Manually confirmed suspicious by operator"
            action_type = "OPERATOR_CONFIRM_SUSPICIOUS"
        elif new_status == "ESCALATED":
            enf.enforcement_status = "ESCALATED"
            enf.blocking_reason = notes or "Escalated for fraud investigation"
            action_type = "OPERATOR_ESCALATE"
        else:
            action_type = f"STATUS_CHANGE_{new_status}"

        log_entry = EnforcementAuditLog(
            transaction_key=enf.transaction_key,
            source_transaction_id=enf.source_transaction_id,
            detection_run_id=enf.detection_run_id,
            previous_status=old_enf_status,
            new_status=enf.enforcement_status,
            action_type=action_type,
            operator_id=operator_id,
            action_reason=notes or f"Updated via alert {alert.alert_id}",
            timestamp=now_str,
        )
        session.add(log_entry)

    session.commit()
    return True


def restrict_account_simulated(
    session: Session,
    bank_code: str,
    account_ref: str,
    reason: str,
    alert_id: Optional[str] = None,
) -> bool:
    """
    Places an account into simulated restricted status and marks the alert as ACCOUNT_RESTRICTED.
    """
    now_str = datetime.now().isoformat()

    # Check if already restricted
    existing = (
        session.query(SimulatedRestrictedAccount)
        .filter_by(bank_code=bank_code, account_ref=account_ref)
        .first()
    )

    if not existing:
        restriction = SimulatedRestrictedAccount(
            bank_code=bank_code,
            account_ref=account_ref,
            restricted_at=now_str,
            reason=reason,
            alert_id=str(alert_id) if alert_id else None,
        )
        session.add(restriction)

    if alert_id:
        warning_int = int(alert_id) if str(alert_id).isdigit() else -1
        alert = (
            session.query(FraudScreeningWarning)
            .filter(
                or_(
                    FraudScreeningWarning.alert_id == str(alert_id),
                    FraudScreeningWarning.warning_id == warning_int,
                )
            )
            .first()
        )
        if alert:
            alert.review_status = "ACCOUNT_RESTRICTED"
            alert.reviewed_at = now_str
            alert.review_notes = f"Simulated account restriction: {reason}"

    session.commit()
    return True


def get_alerts_for_queue(
    session: Session,
    status_filter: str = "Needs Review",
    limit: Optional[int] = None,
) -> List[FraudScreeningWarning]:
    """
    Returns alerts filtered by queue tab:
    - 'Needs Review': review_status == 'NEEDS_REVIEW'
    - 'Escalated': review_status == 'ESCALATED'
    - 'Resolved': review_status in ('LEGITIMATE', 'SUSPICIOUS', 'ACCOUNT_RESTRICTED')
    - 'All Alerts': all alerts
    """
    query = session.query(FraudScreeningWarning).order_by(
        FraudScreeningWarning.warning_id.desc()
    )

    if status_filter == "Needs Review":
        query = query.filter(FraudScreeningWarning.review_status == "NEEDS_REVIEW")
    elif status_filter == "Escalated":
        query = query.filter(FraudScreeningWarning.review_status == "ESCALATED")
    elif status_filter == "Resolved":
        query = query.filter(
            FraudScreeningWarning.review_status.in_(["LEGITIMATE", "SUSPICIOUS", "ACCOUNT_RESTRICTED"])
        )

    if limit is not None and limit > 0:
        query = query.limit(limit)

    return query.all()
