"""
BankFusion Page 1: Fraud Review Queue
=====================================
Operational banking fraud-monitoring triage queue.
Displays active alerts, risk priorities, contextual transaction metadata,
and supports investigator actions with SQLite persistence.
"""

import sys
from pathlib import Path
from datetime import datetime
import streamlit as st
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.database_connection import SessionLocal
from fraud_detection import review_actions
from fraud_detection.save_detection_results import execute_fraud_detection_run


def run_queue_page():
    st.set_page_config(
        page_title="Fraud Review Queue | BankFusion",
        page_icon="🛡️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Custom CSS for dark banking security aesthetic
    st.markdown("""
    <style>
        .metric-card {
            background-color: #1e2430;
            border-radius: 10px;
            padding: 18px 24px;
            border-left: 5px solid #3b82f6;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
            margin-bottom: 12px;
        }
        .metric-card-orange {
            border-left-color: #f59e0b;
        }
        .metric-card-red {
            border-left-color: #ef4444;
        }
        .metric-title {
            font-size: 0.85rem;
            color: #94a3b8;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .metric-value {
            font-size: 2.2rem;
            color: #f8fafc;
            font-weight: 700;
            margin-top: 4px;
        }
        .alert-card {
            background-color: #1a202c;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 16px;
            border: 1px solid #2d3748;
        }
        .alert-high {
            border-left: 6px solid #ef4444 !important;
        }
        .alert-medium {
            border-left: 6px solid #f59e0b !important;
        }
        .alert-review {
            border-left: 6px solid #3b82f6 !important;
        }
        .badge-high {
            background-color: #7f1d1d;
            color: #fca5a5;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 700;
        }
        .badge-medium {
            background-color: #78350f;
            color: #fcd34d;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 700;
        }
        .badge-review {
            background-color: #1e3a8a;
            color: #93c5fd;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 700;
        }
        .badge-resolved {
            background-color: #064e3b;
            color: #6ee7b7;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 700;
        }
        .badge-restricted {
            background-color: #831843;
            color: #fbcfe8;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 700;
        }
    </style>
    """, unsafe_allow_html=True)

    # Header section with title and manual scan button
    col_hdr_left, col_hdr_right = st.columns([3, 1])
    with col_hdr_left:
        st.title("🛡️ Fraud Review Queue")
        st.caption("Operational Multi-Bank Risk Surveillance & Triage Station")

    with col_hdr_right:
        st.write("")
        st.write("")
        if st.button("⚡ Run Fraud Screening", type="primary", use_container_width=True):
            with st.spinner("Executing 4-factor deterministic screening rules..."):
                with SessionLocal() as scan_session:
                    run_result = execute_fraud_detection_run(scan_session)
                if run_result.get("success", False):
                    st.success(
                        f"Screening `{run_result['detection_run_id']}` complete: "
                        f"{run_result['total_flagged_transactions']} flagged across "
                        f"{run_result['total_warnings_generated']} alert entity windows."
                    )
                    st.rerun()
                else:
                    st.error(f"Detection failed: {run_result.get('error_message', 'Unknown error')}")

    # Top summary metrics cards
    with SessionLocal() as db_session:
        summary_counts = review_actions.get_review_queue_summary_metrics(db_session)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="metric-card metric-card-orange">
            <div class="metric-title">Awaiting Review</div>
            <div class="metric-value">{summary_counts['awaiting_review']:,}</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Escalated for Investigation</div>
            <div class="metric-value">{summary_counts['escalated']:,}</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="metric-card metric-card-red">
            <div class="metric-title">Accounts Restricted</div>
            <div class="metric-value">{summary_counts['accounts_restricted']:,}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # Queue Tabs
    tab_needs, tab_all, tab_resolved = st.tabs([
        f"🚨 Needs Review ({summary_counts['awaiting_review']})",
        "📋 All Alerts",
        "✅ Resolved",
    ])

    tab_mapping = [
        (tab_needs, "Needs Review"),
        (tab_all, "All Alerts"),
        (tab_resolved, "Resolved"),
    ]

    for current_tab, tab_filter in tab_mapping:
        with current_tab:
            with SessionLocal() as db_session:
                alerts = review_actions.get_alerts_for_queue(db_session, status_filter=tab_filter)

            if not alerts:
                st.info("ℹ️ No suspicious transactions currently require review in this view.")
                if tab_filter == "Needs Review":
                    st.markdown("""
                    All incoming warehouse transactions have either cleared screening or have been resolved.
                    Click below to screen newly arrived transactions against the four deterministic rules:
                    """)
                    if st.button("▶️ Run Screening on Warehouse Transactions", key=f"run_screen_{tab_filter}"):
                        with st.spinner("Analyzing transaction velocity, shared devices, unusual amounts, and rapid chains..."):
                            with SessionLocal() as run_sess:
                                res = execute_fraud_detection_run(run_sess)
                            if res.get("success", False):
                                st.success(f"Detection Run `{res['detection_run_id']}` finished. Flagged {res['total_flagged_transactions']} transactions.")
                                st.rerun()
                            else:
                                st.error(f"Error: {res.get('error_message')}")
                continue

            for alert in alerts:
                # Determine styling
                prio = alert.review_priority.upper() if alert.review_priority else "MEDIUM"
                border_cls = "alert-high" if prio == "HIGH" else ("alert-medium" if prio == "MEDIUM" else "alert-review")
                badge_cls = "badge-high" if prio == "HIGH" else ("badge-medium" if prio == "MEDIUM" else "badge-review")

                status_label = alert.review_status.replace("_", " ") if alert.review_status else "NEEDS REVIEW"
                status_badge = "badge-resolved" if alert.review_status in ("LEGITIMATE", "SUSPICIOUS") else (
                    "badge-restricted" if alert.review_status == "ACCOUNT_RESTRICTED" else badge_cls
                )

                amt_str = f"₹{alert.amount_paise / 100:,.2f}" if alert.amount_paise else "N/A"
                dev_str = alert.device_token if alert.device_token and alert.device_token != "UNKNOWN_DEVICE" else "Unknown / None"

                # Render Alert Card Container
                with st.container():
                    st.markdown(f"""
                    <div class="alert-card {border_cls}">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <div>
                                <span style="font-size: 1.15rem; font-weight: 700; color: #f8fafc; margin-right: 12px;">
                                    Alert {alert.alert_id or f'ALT-{alert.warning_id:04d}'}
                                </span>
                                <span class="{badge_cls}">{prio} RISK</span>
                                <span class="{status_badge}" style="margin-left: 8px;">{status_label}</span>
                            </div>
                            <div style="font-size: 0.9rem; color: #94a3b8;">
                                ⏱️ {alert.trigger_timestamp}
                            </div>
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 12px; font-size: 0.9rem;">
                            <div>
                                <div style="color: #64748b; font-size: 0.75rem;">ORIGINATING BANK & SENDER</div>
                                <div style="font-weight: 600; color: #e2e8f0;">{alert.originating_bank or 'UNKNOWN'}</div>
                                <div style="color: #cbd5e1; font-family: monospace;">{alert.sender_account_ref or alert.entity_ref}</div>
                            </div>
                            <div>
                                <div style="color: #64748b; font-size: 0.75rem;">DESTINATION BANK & RECEIVER</div>
                                <div style="font-weight: 600; color: #e2e8f0;">{alert.destination_bank or 'INTERBANK'}</div>
                                <div style="color: #cbd5e1; font-family: monospace;">{alert.receiver_account_ref or 'VARIOUS'}</div>
                            </div>
                            <div>
                                <div style="color: #64748b; font-size: 0.75rem;">AMOUNT & METHOD</div>
                                <div style="font-weight: 700; color: #38bdf8; font-size: 1.05rem;">{amt_str}</div>
                                <div style="color: #94a3b8;">{alert.payment_method or 'ELECTRONIC'} • {alert.transaction_status or 'SETTLED'}</div>
                            </div>
                            <div>
                                <div style="color: #64748b; font-size: 0.75rem;">DEVICE TOKEN</div>
                                <div style="color: #e2e8f0; font-family: monospace; font-size: 0.85rem;">{dev_str}</div>
                                <div style="color: #f87171; font-weight: 600;">{alert.verdict}</div>
                            </div>
                        </div>
                        <div style="background-color: #0f172a; padding: 10px 14px; border-radius: 6px; margin-bottom: 12px; font-size: 0.88rem; border-left: 3px solid #64748b;">
                            <strong style="color: #fbbf24;">Triggered Indicators:</strong> {alert.rules_triggered or alert.rule_name}
                            <br/>
                            <strong style="color: #94a3b8;">Evidence:</strong> {alert.evidence_summary}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Expandable details
                    with st.expander(f"🔍 Detailed Evidence & Audit Trail for {alert.alert_id or f'ALT-{alert.warning_id}'}", expanded=False):
                        col_ev1, col_ev2 = st.columns(2)
                        with col_ev1:
                            st.write(f"**Entity Type:** `{alert.entity_type}`")
                            st.write(f"**Entity Identifier:** `{alert.entity_ref}`")
                            st.write(f"**Window Period:** `{alert.window_start}` → `{alert.window_end}`")
                            st.write(f"**Threshold Limit:** `{alert.threshold_value}`")
                            st.write(f"**Observed Value:** `{alert.observed_value}`")
                        with col_ev2:
                            if alert.linked_route_summary:
                                st.write(f"**Interbank Route:** `{alert.linked_route_summary}`")
                            if alert.linked_transaction_ids:
                                st.write(f"**Linked Transaction Keys:** `{alert.linked_transaction_ids}`")
                            if alert.review_notes:
                                st.info(f"📝 **Investigator Notes:** {alert.review_notes}")
                            if alert.reviewed_at:
                                st.caption(f"Last Action Timestamp: {alert.reviewed_at}")

                    # Review action buttons
                    col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)
                    target_alert_id = alert.alert_id or str(alert.warning_id)

                    with col_btn1:
                        if st.button("✅ Mark Legitimate", key=f"btn_leg_{target_alert_id}_{tab_filter}", use_container_width=True):
                            with SessionLocal() as s:
                                review_actions.update_alert_status(s, target_alert_id, "LEGITIMATE", notes="Verified by investigator as benign.")
                            st.toast(f"Alert {target_alert_id} marked as Legitimate.", icon="✅")
                            st.rerun()

                    with col_btn2:
                        if st.button("🚨 Confirm Suspicious", key=f"btn_susp_{target_alert_id}_{tab_filter}", use_container_width=True):
                            with SessionLocal() as s:
                                review_actions.update_alert_status(s, target_alert_id, "SUSPICIOUS", notes="Confirmed fraudulent pattern.")
                            st.toast(f"Alert {target_alert_id} confirmed Suspicious.", icon="🚨")
                            st.rerun()

                    with col_btn3:
                        if st.button("⚠️ Escalate Case", key=f"btn_esc_{target_alert_id}_{tab_filter}", use_container_width=True):
                            with SessionLocal() as s:
                                review_actions.update_alert_status(s, target_alert_id, "ESCALATED", notes="Escalated for senior compliance review.")
                            st.toast(f"Alert {target_alert_id} Escalated.", icon="⚠️")
                            st.rerun()

                    with col_btn4:
                        if st.button("🔒 Restrict Account", key=f"btn_rest_{target_alert_id}_{tab_filter}", use_container_width=True):
                            b_code = alert.originating_bank or (alert.entity_ref.split('-')[0] if '-' in alert.entity_ref else "BANK")
                            with SessionLocal() as s:
                                review_actions.restrict_account_simulated(
                                    session=s,
                                    bank_code=b_code,
                                    account_ref=alert.sender_account_ref or alert.entity_ref,
                                    reason=f"Restricted from Alert {target_alert_id}: {alert.rules_triggered or alert.rule_name}",
                                    alert_id=target_alert_id,
                                )
                            st.toast(f"Account {alert.sender_account_ref or alert.entity_ref} Restricted.", icon="🔒")
                            st.rerun()

                    st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)


if __name__ == "__main__" or True:
    run_queue_page()

