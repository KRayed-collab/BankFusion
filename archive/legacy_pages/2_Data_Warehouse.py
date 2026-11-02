"""
BankFusion Page 2: Data Warehouse, ETL & OLAP Engine
====================================================
Provides source inspection, ETL execution controls, Star Schema exploration,
and interactive OLAP Slice, Dice, Roll-up, and Drill-down operations.
"""

import sys
from pathlib import Path
import streamlit as st
import pandas as pd
import plotly.express as px

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.database_connection import SessionLocal
from database.database_models import (
    BankATransaction,
    BankBEvent,
    BankCLedgerEntry,
    FactTransaction,
    ETLBatchLog,
    ETLRejectedRecord,
)
from data_generation.generate_ground_truth import generate_and_load_full_source_data
from etl.run_etl_pipeline import execute_full_etl_pipeline
from warehouse.warehouse_queries import get_denormalized_fact_dataframe
from analytics.olap_operations import olap_slice, olap_dice, olap_roll_up, olap_drill_down
from analytics.transaction_trends import get_hourly_activity_profile
from analytics.transaction_summaries import get_payment_method_distribution

st.set_page_config(page_title="Data Warehouse | BankFusion", page_icon="🏢", layout="wide")

st.title("🏢 Page 2: Data Warehouse, ETL & OLAP Operations")
st.caption("Inspect Sources, Execute ETL Pipeline, Explore Star Schema & Perform Multidimensional Analysis")

tab_gen, tab_etl, tab_wh, tab_olap = st.tabs([
    "1. Source Systems & Generation",
    "2. ETL Pipeline & Quarantine",
    "3. Star Schema Explorer",
    "4. OLAP Operations (Slice / Dice / Roll-up)",
])

session = SessionLocal()

try:
    # =========================================================================
    # TAB 1: SOURCE SYSTEMS & DATA GENERATION
    # =========================================================================
    with tab_gen:
        st.subheader("⚙️ Programmatic Synthetic Data Generation")
        col_g1, col_g2 = st.columns([1, 3])
        with col_g1:
            seed_val = st.number_input("Random Seed", value=42, step=1)
            gen_btn = st.button("🔄 Generate & Seed Full Dataset", type="primary")

        if gen_btn:
            with st.spinner("Generating reproducible multi-bank dataset..."):
                gen_res = generate_and_load_full_source_data(random_seed=seed_val, reset_tables=True)
            st.success(f"Generated: Bank A = {gen_res['bank_a_records_generated']} | Bank B = {gen_res['bank_b_events_generated']} | Bank C = {gen_res['bank_c_entries_generated']}")

        st.markdown("---")
        st.subheader("🔍 Inspect Raw Operational Source Systems")
        src_tab_a, src_tab_b, src_tab_c = st.tabs(["Bank A (MetroBank)", "Bank B (QuickPay)", "Bank C (TrustLine)"])

        with src_tab_a:
            st.caption("MetroBank: Flat Transaction-Per-Attempt Grain")
            a_records = session.query(BankATransaction).limit(50).all()
            if a_records:
                df_a = pd.DataFrame([r.__dict__ for r in a_records]).drop(columns=["_sa_instance_state"], errors="ignore")
                df_a["amount_inr"] = df_a["amount_paise"] / 100.0
                st.dataframe(df_a, use_container_width=True, hide_index=True)
            else:
                st.info("No records in bank_a_transactions. Click 'Generate & Seed Full Dataset'.")

        with src_tab_b:
            st.caption("QuickPay Bank: Payment Event Stream Grain (Includes Retries under payment_request_ref)")
            b_records = session.query(BankBEvent).limit(50).all()
            if b_records:
                df_b = pd.DataFrame([r.__dict__ for r in b_records]).drop(columns=["_sa_instance_state"], errors="ignore")
                df_b["value_inr"] = df_b["value_paise"] / 100.0
                st.dataframe(df_b, use_container_width=True, hide_index=True)
            else:
                st.info("No records in bank_b_events.")

        with src_tab_c:
            st.caption("TrustLine Bank: Double-Entry Ledger Grain (2 Legs per journal_id: 1 DEBIT + 1 CREDIT)")
            c_records = session.query(BankCLedgerEntry).limit(50).all()
            if c_records:
                df_c = pd.DataFrame([r.__dict__ for r in c_records]).drop(columns=["_sa_instance_state"], errors="ignore")
                df_c["amount_inr"] = df_c["amount_paise"] / 100.0
                st.dataframe(df_c, use_container_width=True, hide_index=True)
            else:
                st.info("No records in bank_c_ledger_entries.")

    # =========================================================================
    # TAB 2: ETL PIPELINE & RECONCILIATION
    # =========================================================================
    with tab_etl:
        st.subheader("🚀 Execute 7-Stage ETL Pipeline")
        st.markdown("Extracts source tables, validates ranges, pairs Bank C journals, maps fields, resolves surrogate keys, loads facts, and reconciles balances.")

        if st.button("▶️ Run Full ETL Pipeline Now", type="primary"):
            with st.spinner("Executing 7-stage ETL pipeline..."):
                etl_summary = execute_full_etl_pipeline()
            st.success(f"ETL Batch {etl_summary['batch_id']} Completed! Inserted: {etl_summary['warehouse_inserted']} | Skipped Duplicates: {etl_summary['duplicates_skipped']}")

        st.markdown("---")
        st.subheader("📋 ETL Batch Audit Log History")
        batch_logs = session.query(ETLBatchLog).order_by(ETLBatchLog.batch_timestamp.desc()).all()
        if batch_logs:
            df_logs = pd.DataFrame([b.__dict__ for b in batch_logs]).drop(columns=["_sa_instance_state"], errors="ignore")
            df_logs["warehouse_volume_inr"] = df_logs["warehouse_amount_paise_inserted"] / 100.0
            st.dataframe(
                df_logs[[
                    "batch_id", "status", "total_source_rows_extracted", "total_valid_source_rows",
                    "total_rejected_source_rows", "normalized_warehouse_transactions_produced",
                    "warehouse_rows_inserted", "duplicate_rows_skipped", "warehouse_volume_inr", "execution_duration_sec"
                ]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No ETL batches executed yet.")

        st.subheader("🚨 Quarantined Source Records (etl_rejected_record)")
        rejections = session.query(ETLRejectedRecord).limit(50).all()
        if rejections:
            df_rej = pd.DataFrame([r.__dict__ for r in rejections]).drop(columns=["_sa_instance_state"], errors="ignore")
            st.dataframe(df_rej[["rejection_id", "source_bank_code", "source_record_id", "rejection_stage", "rejection_reason", "recorded_at"]], use_container_width=True, hide_index=True)
        else:
            st.success("No rejected records found in current batch.")

    # =========================================================================
    # TAB 3: STAR SCHEMA EXPLORER
    # =========================================================================
    with tab_wh:
        st.subheader("⭐ Common Star Schema Fact Table Explorer")
        st.markdown("""
        **Fact Grain:** 1 normalized payment attempt (Bank A & B) or 1 valid posted transfer (Bank C pair).  
        **Lineage:** `source_transaction_id` and `source_record_refs` guarantee complete backward auditability to raw source rows.
        """)

        df_facts = get_denormalized_fact_dataframe(session)
        if not df_facts.empty:
            st.dataframe(
                df_facts[[
                    "transaction_key", "bank_code", "source_transaction_id", "source_record_refs",
                    "transaction_timestamp", "source_account_ref", "destination_account_ref",
                    "amount_inr", "payment_method", "transaction_status", "device_token"
                ]].head(100),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Fact table is empty. Run ETL in Tab 2.")

    # =========================================================================
    # TAB 4: OLAP MULTIDIMENSIONAL OPERATIONS
    # =========================================================================
    with tab_olap:
        st.subheader("🎲 Interactive OLAP Operations")
        if df_facts.empty:
            st.warning("Please load warehouse facts first via Tab 2 (ETL).")
        else:
            olap_mode = st.radio("Select OLAP Operation:", ["1. Slice", "2. Dice", "3. Roll-up & Drill-down"], horizontal=True)

            if olap_mode == "1. Slice":
                st.markdown("#### OLAP Slice: Pinning the Bank Dimension")
                slice_bank = st.selectbox("Select Bank to Slice By:", ["BANK_A", "BANK_B", "BANK_C"])
                sliced_df = olap_slice(df_facts, "bank_code", slice_bank)
                st.info(f"Sliced Sub-Cube: {len(sliced_df)} transactions belonging exclusively to {slice_bank}.")
                st.dataframe(sliced_df[["transaction_key", "source_transaction_id", "source_account_ref", "destination_account_ref", "amount_inr", "payment_method", "transaction_status"]].head(50), use_container_width=True, hide_index=True)

            elif olap_mode == "2. Dice":
                st.markdown("#### OLAP Dice: Multi-Dimensional Sub-Cube Filtering")
                col_d1, col_d2, col_d3 = st.columns(3)
                with col_d1:
                    d_banks = st.multiselect("Filter Banks:", options=sorted(df_facts["bank_code"].unique()), default=sorted(df_facts["bank_code"].unique()))
                with col_d2:
                    d_methods = st.multiselect("Filter Methods:", options=sorted(df_facts["payment_method"].unique()), default=sorted(df_facts["payment_method"].unique()))
                with col_d3:
                    d_statuses = st.multiselect("Filter Statuses:", options=sorted(df_facts["transaction_status"].unique()), default=["SUCCESS"])

                min_val = float(df_facts["amount_inr"].min())
                max_val = float(df_facts["amount_inr"].max())
                amt_range = st.slider("Filter Amount Range (₹):", min_val, max_val, (min_val, max_val))

                diced_df = olap_dice(df_facts, banks=d_banks, methods=d_methods, statuses=d_statuses, min_amount_inr=amt_range[0], max_amount_inr=amt_range[1])
                st.info(f"Diced Sub-Cube: {len(diced_df)} matching transactions across selected dimension coordinates.")
                st.dataframe(diced_df[["transaction_key", "bank_code", "source_account_ref", "destination_account_ref", "amount_inr", "payment_method", "transaction_status"]].head(50), use_container_width=True, hide_index=True)

            elif olap_mode == "3. Roll-up & Drill-down":
                st.markdown("#### OLAP Roll-up: Climbing the Temporal Hierarchy")
                roll_level = st.selectbox("Select Aggregation Grain:", ["daily", "hourly", "monthly", "quarterly"])
                rolled_df = olap_roll_up(df_facts, level=roll_level)
                st.dataframe(rolled_df, use_container_width=True, hide_index=True)

                st.subheader("📈 Hourly Activity Distribution (OLAP Profile)")
                hourly_df = get_hourly_activity_profile(df_facts)
                if not hourly_df.empty:
                    fig_hour = px.bar(hourly_df, x="hour", y="transaction_count", title="Transaction Frequency by Hour of Day", labels={"hour": "Clock Hour (0-23)", "transaction_count": "Transactions"})
                    st.plotly_chart(fig_hour, use_container_width=True)

finally:
    session.close()

