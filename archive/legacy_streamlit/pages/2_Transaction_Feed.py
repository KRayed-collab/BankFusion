"""
BankFusion Page 2: Transaction Feed
===================================
Real-time multi-bank transaction surveillance feed.
Displays incoming transactions with deterministic 4-factor risk assessment,
granular filters, dimensional context, and interactive transaction inspector.
"""

import sys
import time
import random
from pathlib import Path
from datetime import datetime, timezone, timedelta
import streamlit as st
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.database_connection import SessionLocal
from database.database_models import (
    BankATransaction,
    BankBEvent,
    DimAccount,
    DimDevice,
    FactTransaction,
    FraudTransactionPrediction,
    FraudDetectionRun,
)
from warehouse.warehouse_queries import get_transaction_feed_dataframe
from fraud_detection.save_detection_results import execute_fraud_detection_run
from etl.run_etl_pipeline import execute_full_etl_pipeline

IST = timezone(timedelta(hours=5, minutes=30))


def simulate_new_incoming_transaction() -> str:
    """
    Simulates a single realistic live transaction and ingests it through the ETL pipeline.
    """
    now = datetime.now(IST)
    now_iso = now.isoformat()
    epoch_now = int(now.timestamp())
    rand_id = f"SIM-{int(time.time() * 1000) % 1000000}"

    with SessionLocal() as s:
        # Pick existing accounts or fallback
        metro_accs = [a.source_account_ref for a in s.query(DimAccount).filter(DimAccount.bank_key == 1).limit(10).all()]
        qpay_accs = [a.source_account_ref for a in s.query(DimAccount).filter(DimAccount.bank_key == 2).limit(10).all()]
        devices = [d.device_token for d in s.query(DimDevice).filter(DimDevice.device_token != "UNKNOWN_DEVICE").limit(10).all()]

        sender = random.choice(metro_accs) if metro_accs else "METRO-ACC-001"
        receiver = random.choice(qpay_accs) if qpay_accs else "QPAY-ACC-002"
        dev = random.choice(devices) if devices else "DEV-TOKEN-001"
        amt_paise = random.choice([45000, 120000, 250000, 750000, 1500000, 12000000])
        mode = random.choice(["UPI", "IMPS", "NEFT"])
        stat = random.choice(["SUCCESS", "SUCCESS", "SUCCESS", "FAILED"])

        new_record = BankATransaction(
            transaction_id=f"A-TXN-{rand_id}",
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

    # Ingest through ETL pipeline into warehouse
    execute_full_etl_pipeline()

    # Execute screening
    with SessionLocal() as s:
        execute_fraud_detection_run(s)

    return f"A-TXN-{rand_id}"


def run_feed_page():
    st.set_page_config(
        page_title="Transaction Feed | BankFusion",
        page_icon="💳",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Custom styling
    st.markdown("""
    <style>
        .metric-card {
            background-color: #1e2430;
            border-radius: 10px;
            padding: 16px 20px;
            border-left: 5px solid #3b82f6;
            margin-bottom: 12px;
        }
        .metric-card-green { border-left-color: #10b981; }
        .metric-card-red { border-left-color: #ef4444; }
        .metric-card-amber { border-left-color: #f59e0b; }
        .metric-title {
            font-size: 0.8rem;
            color: #94a3b8;
            font-weight: 600;
            text-transform: uppercase;
        }
        .metric-value {
            font-size: 1.8rem;
            color: #f8fafc;
            font-weight: 700;
        }
        .feed-suspicious-row {
            background-color: rgba(239, 68, 68, 0.15) !important;
            color: #fca5a5 !important;
            font-weight: 600;
        }
        .feed-clean-row {
            background-color: rgba(16, 185, 129, 0.12) !important;
            color: #6ee7b7 !important;
        }
    </style>
    """, unsafe_allow_html=True)

    # Header and controls
    col_hdr, col_act1, col_act2 = st.columns([2.5, 1, 1])
    with col_hdr:
        st.title("💳 Transaction Feed")
        st.caption("Live Multi-Bank Transaction Stream & Deterministic Risk Surveillance")

    with col_act1:
        st.write("")
        st.write("")
        if st.button("➕ Ingest Simulated Txn", type="primary", use_container_width=True):
            with st.spinner("Injecting live multi-bank transaction through ETL & screening..."):
                new_id = simulate_new_incoming_transaction()
            st.success(f"Ingested & screened `{new_id}`!")
            st.rerun()

    with col_act2:
        st.write("")
        st.write("")
        if st.button("⚡ Re-Screen Warehouse", use_container_width=True):
            with st.spinner("Running 4-factor deterministic detector across all facts..."):
                with SessionLocal() as sess:
                    res = execute_fraud_detection_run(sess)
                if res.get("success", False):
                    st.success(f"Detection `{res['detection_run_id']}` complete: {res['total_flagged_transactions']} flagged.")
                    st.rerun()
                else:
                    st.error(f"Detection failed: {res.get('error_message')}")

    # Fetch feed dataframe
    with SessionLocal() as db_session:
        df_feed = get_transaction_feed_dataframe(db_session)

    if df_feed.empty:
        st.warning("⚠️ No transactions found in the Data Warehouse. Run ETL on source records or simulate an incoming transaction.")
        return

    # Summary Metrics
    total_txns = len(df_feed)
    susp_count = int((df_feed["is_predicted_suspicious"] == 1).sum())
    clean_count = total_txns - susp_count
    fraud_pct = (susp_count / total_txns * 100.0) if total_txns > 0 else 0.0

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Monitored Transactions</div>
            <div class="metric-value">{total_txns:,}</div>
        </div>
        """, unsafe_allow_html=True)
    with m2:
        st.markdown(f"""
        <div class="metric-card metric-card-red">
            <div class="metric-title">Flagged Suspicious</div>
            <div class="metric-value">{susp_count:,}</div>
        </div>
        """, unsafe_allow_html=True)
    with m3:
        st.markdown(f"""
        <div class="metric-card metric-card-green">
            <div class="metric-title">Cleared (Clean)</div>
            <div class="metric-value">{clean_count:,}</div>
        </div>
        """, unsafe_allow_html=True)
    with m4:
        st.markdown(f"""
        <div class="metric-card metric-card-amber">
            <div class="metric-title">Active Fraud Ratio</div>
            <div class="metric-value">{fraud_pct:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # Filter Controls Section
    with st.expander("🔎 Feed Filters & Search Controls", expanded=True):
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)

        with f_col1:
            filter_status = st.selectbox(
                "Risk Assessment:",
                ["All Transactions", "Suspected Fraud Only", "No Alert Only"],
                index=0,
            )

        with f_col2:
            bank_options = ["All Banks"] + sorted(list(df_feed["bank_code"].unique()))
            filter_bank = st.selectbox("Source Bank:", bank_options, index=0)

        with f_col3:
            filter_factor = st.selectbox(
                "Detection Factor:",
                [
                    "All Factors",
                    "Velocity Burst",
                    "Shared Device",
                    "Large Amount",
                    "Cross-Bank Movement",
                ],
                index=0,
            )

        with f_col4:
            status_options = ["All Statuses"] + sorted(list(df_feed["transaction_status"].unique()))
            filter_txn_status = st.selectbox("Transaction Status:", status_options, index=0)

        search_query = st.text_input(
            "Search Account Reference, Device Token or Transaction ID:",
            value="",
            placeholder="e.g. METRO-ACC-001, DEV-001, or A-TXN-...",
        ).strip()

    # Apply Filters
    df_filtered = df_feed.copy()

    if filter_status == "Suspected Fraud Only":
        df_filtered = df_filtered[df_filtered["is_predicted_suspicious"] == 1]
    elif filter_status == "No Alert Only":
        df_filtered = df_filtered[df_filtered["is_predicted_suspicious"] == 0]

    if filter_bank != "All Banks":
        df_filtered = df_filtered[df_filtered["bank_code"] == filter_bank]

    if filter_factor == "Velocity Burst":
        df_filtered = df_filtered[df_filtered["flagged_by_velocity"] == 1]
    elif filter_factor == "Shared Device":
        df_filtered = df_filtered[df_filtered["flagged_by_device"] == 1]
    elif filter_factor == "Large Amount":
        df_filtered = df_filtered[df_filtered["flagged_by_large_amount"] == 1]
    elif filter_factor == "Cross-Bank Movement":
        df_filtered = df_filtered[df_filtered["flagged_by_cross_bank_movement"] == 1]

    if filter_txn_status != "All Statuses":
        df_filtered = df_filtered[df_filtered["transaction_status"] == filter_txn_status]

    if search_query:
        mask = (
            df_filtered["source_transaction_id"].astype(str).str.contains(search_query, case=False, na=False)
            | df_filtered["source_account_ref"].astype(str).str.contains(search_query, case=False, na=False)
            | df_filtered["destination_account_ref"].astype(str).str.contains(search_query, case=False, na=False)
            | df_filtered["device_token"].astype(str).str.contains(search_query, case=False, na=False)
        )
        df_filtered = df_filtered[mask]

    st.caption(f"Showing **{len(df_filtered):,}** matching transactions (ordered latest first):")

    if df_filtered.empty:
        st.info("No transactions match the selected filter criteria.")
        return

    # Format Display DataFrame
    display_df = df_filtered[[
        "transaction_timestamp",
        "source_transaction_id",
        "bank_code",
        "source_account_ref",
        "destination_bank",
        "destination_account_ref",
        "amount_inr",
        "transaction_status",
        "is_predicted_suspicious",
        "detection_factors",
    ]].copy()

    display_df["amount_formatted"] = display_df["amount_inr"].apply(lambda v: f"₹{v:,.2f}")
    display_df["assessment"] = display_df["is_predicted_suspicious"].apply(
        lambda s: "🚨 SUSPICIOUS" if s == 1 else "✅ CLEAN"
    )

    display_table = display_df[[
        "transaction_timestamp",
        "source_transaction_id",
        "bank_code",
        "source_account_ref",
        "destination_bank",
        "destination_account_ref",
        "amount_formatted",
        "transaction_status",
        "assessment",
        "detection_factors",
    ]].rename(columns={
        "transaction_timestamp": "Timestamp",
        "source_transaction_id": "Txn ID",
        "bank_code": "Origin Bank",
        "source_account_ref": "Sender Account",
        "destination_bank": "Dest Bank",
        "destination_account_ref": "Receiver Account",
        "amount_formatted": "Amount (₹)",
        "transaction_status": "Status",
        "assessment": "Screening Result",
        "detection_factors": "Triggered Rule(s)",
    })

    # Styling helper: red for suspicious, green for clean
    def highlight_rows(row):
        if "SUSPICIOUS" in str(row["Screening Result"]):
            return ["background-color: rgba(239, 68, 68, 0.2); color: #fca5a5; font-weight: 600;"] * len(row)
        else:
            return ["background-color: rgba(16, 185, 129, 0.12); color: #6ee7b7;"] * len(row)

    styled_df = display_table.head(100).style.apply(highlight_rows, axis=1)
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    # Transaction Details Inspector
    st.markdown("---")
    st.subheader("🔍 Transaction Detail Inspector")
    st.caption("Select any transaction from the active filtered feed to inspect its dimensional keys, lineage, and rule triggers:")

    txn_options = df_filtered["source_transaction_id"].head(50).tolist()
    selected_txn_id = st.selectbox("Choose Transaction ID to Inspect:", txn_options, index=0)

    selected_row = df_filtered[df_filtered["source_transaction_id"] == selected_txn_id].iloc[0]

    col_ctx1, col_ctx2, col_ctx3 = st.columns(3)
    with col_ctx1:
        st.write(f"**Transaction Key:** `{selected_row['transaction_key']}`")
        st.write(f"**Source Lineage Ref:** `{selected_row.get('source_record_refs', 'N/A')}`")
        st.write(f"**Origin Bank:** `{selected_row['bank_code']}` ({selected_row.get('bank_name', '')})")
        st.write(f"**Destination Bank:** `{selected_row['destination_bank']}`")
        st.write(f"**Sender Account:** `{selected_row['source_account_ref']}`")
        st.write(f"**Receiver Account:** `{selected_row['destination_account_ref']}`")

    with col_ctx2:
        st.write(f"**Monetary Amount (INR):** ₹{selected_row['amount_inr']:,.2f}")
        st.write(f"**Integer Paise:** `{int(selected_row['amount_paise']):,}` paise")
        st.write(f"**Payment Method:** `{selected_row.get('payment_method', 'N/A')}`")
        st.write(f"**Transaction Status:** `{selected_row.get('transaction_status', 'N/A')}`")
        st.write(f"**Device Token:** `{selected_row.get('device_token') or 'UNKNOWN_DEVICE'}`")
        st.write(f"**Timestamp (IST):** `{selected_row['transaction_timestamp']}`")

    with col_ctx3:
        st.write(f"**Final Assessment:** {'🚨 SUSPICIOUS' if selected_row['is_predicted_suspicious'] == 1 else '✅ CLEAN'}")
        st.write(f"**Rule 1 (Velocity Burst):** {'🚨 FLAGGED' if selected_row['flagged_by_velocity'] == 1 else '✅ Clear'}")
        st.write(f"**Rule 2 (Shared Device):** {'🚨 FLAGGED' if selected_row['flagged_by_device'] == 1 else '✅ Clear'}")
        st.write(f"**Rule 3 (Large Amount):** {'🚨 FLAGGED' if selected_row['flagged_by_large_amount'] == 1 else '✅ Clear'}")
        st.write(f"**Rule 4 (Cross-Bank):** {'🚨 FLAGGED' if selected_row['flagged_by_cross_bank_movement'] == 1 else '✅ Clear'}")
        if selected_row["is_predicted_suspicious"] == 1:
            st.error(f"⚠️ Flagged Factors: **{selected_row['detection_factors']}**")
            st.info("💡 To triage this alert, navigate to the **Fraud Review Queue** in the sidebar.")
        else:
            st.success("✅ Transaction satisfies all deterministic sanity thresholds.")


if __name__ == "__main__" or True:
    run_feed_page()

