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

from database.database_models import FraudScreeningWarning, SimulatedRestrictedAccount


def get_review_queue_summary_metrics(session: Session) -> Dict[str, int]:
    """
    Returns actual counts from SQLite for the top 3 summary cards:
    1. Awaiting Review (unresolved alerts with review_status='NEEDS_REVIEW')
    2. Escalated (alerts escalated for investigation with review_status='ESCALATED')
    3. Accounts Restricted (simulated restrictions)
    """
    awaiting = session.query(FraudScreeningWarning).filter_by(review_status="NEEDS_REVIEW").count()
    escalated = session.query(FraudScreeningWarning).filter_by(review_status="ESCALATED").count()
    restricted = session.query(SimulatedRestrictedAccount).count()

    return {
        "awaiting_review": awaiting,
        "escalated": escalated,
        "accounts_restricted": restricted,
    }


def update_alert_status(
    session: Session,
    alert_id: str,
    new_status: str,
    notes: Optional[str] = None,
) -> bool:
    """
    Updates the review status of an alert in the database.
    Status choices: 'NEEDS_REVIEW', 'LEGITIMATE', 'SUSPICIOUS', 'ESCALATED', 'ACCOUNT_RESTRICTED'
    Supports lookup by alert_id ('ALT-xxxx') or numeric warning_id.
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

    alert.review_status = new_status
    alert.reviewed_at = datetime.now().isoformat()
    if notes:
        alert.review_notes = notes

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
        return query.filter(FraudScreeningWarning.review_status == "NEEDS_REVIEW").all()
    elif status_filter == "Escalated":
        return query.filter(FraudScreeningWarning.review_status == "ESCALATED").all()
    elif status_filter == "Resolved":
        return query.filter(
            FraudScreeningWarning.review_status.in_(["LEGITIMATE", "SUSPICIOUS", "ACCOUNT_RESTRICTED"])
        ).all()
    else:  # All Alerts
        return query.all()
