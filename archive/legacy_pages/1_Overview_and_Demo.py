"""
BankFusion Page 1: Overview & Interactive Demonstration
=======================================================
Presents the central architecture and executes the reproducible BF-DEMO-001 viva walkthrough.
"""

import sys
from pathlib import Path
import streamlit as st
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.database_connection import SessionLocal
from warehouse.warehouse_queries import get_warehouse_summary_metrics, get_denormalized_fact_dataframe
from analytics.bank_comparison import generate_bank_comparison_metrics
from demo.run_demo_case import run_complete_demo_scenario, reset_demo_records

st.set_page_config(page_title="Overview & Demo | BankFusion", page_icon="🎯", layout="wide")

st.title("🎯 Page 1: Project Overview & Live Demonstration")
st.caption("BankFusion: Multi-Bank Data Warehouse & Fraud Analytics Platform")

# Architecture Overview
with st.expander("🏗️ View BankFusion Central End-to-End Workflow", expanded=False):
    st.markdown("""
    ```
    Heterogeneous Banking Data (MetroBank, QuickPay Bank, TrustLine Bank)
            ↓
    Programmatic Synthetic Data Generation (Fixed Seed 42, Integer Paise, ISO-8601 IST)
            ↓
    Three Independent Bank Source Systems (Attempts, Retries, Double-Entry Ledgers)
            ↓
    7-Stage ETL Pipeline (Extract -> Validate -> Pair -> Map -> Resolve -> Idempotent Load -> Reconcile)
            ↓
    Common Data Warehouse (Kimball Star Schema: FactTransaction + 7 Conformed Dimensions)
            ↓
    OLAP Multidimensional Engine (Slice, Dice, Drill-down, Roll-up)
            ↓
    Deterministic Fraud Screening (Rolling 5-min Velocity & Rolling 24-hr Shared Device)
            ↓
    Universal Predictions & Logically Separated Ground-Truth Evaluation (Precision, Recall, F1)
    ```
    """)

# Summary Cards
session = SessionLocal()
try:
    df_facts = get_denormalized_fact_dataframe(session)
    comp_df = generate_bank_comparison_metrics(df_facts) if not df_facts.empty else pd.DataFrame()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Facts in Warehouse", f"{len(df_facts):,}")
    with c2:
        total_inr = df_facts["amount_inr"].sum() if not df_facts.empty else 0.0
        st.metric("Total Warehouse Volume", f"₹{total_inr:,.2f}")
    with c3:
        succ_rate = (
            (df_facts["transaction_status"] == "SUCCESS").mean() * 100.0
            if not df_facts.empty
            else 0.0
        )
        st.metric("Global Settlement Rate", f"{succ_rate:.1f}%")
    with c4:
        st.metric("Source Systems", "3 Banks", "Heterogeneous Structures")

    if not comp_df.empty:
        st.subheader("📊 Bank-Wise Performance Summary")
        st.dataframe(comp_df, use_container_width=True, hide_index=True)

finally:
    session.close()

st.markdown("---")

# =============================================================================
# REPRODUCIBLE DEMO SECTION: BF-DEMO-001
# =============================================================================
st.subheader("🚀 Dedicated Viva Demonstration: Scenario `BF-DEMO-001`")
st.markdown("""
This demonstration guides an examiner through the entire pipeline using **actual backend functions**:
1. Ingests raw source records for Banks A, B, and C with distinct schemas.
2. Demonstrates grain reduction (Bank C 2 ledger legs $\\rightarrow$ 1 business transfer).
3. Demonstrates quarantine of a malformed Bank C journal (`C-J-DEMO-ERR` with mismatched amounts).
4. Verifies dual-equation ETL reconciliation.
5. Executes Rule 1 (Velocity Burst: 4 attempts in 110s) and Rule 2 (Shared Device: 3 banks on 1 device).
6. Displays investigator evidence and compares against logically separated ground-truth evaluation.
""")

col_btn1, col_btn2 = st.columns([1, 4])
with col_btn1:
    run_demo = st.button("▶️ Run Scenario BF-DEMO-001", type="primary", use_container_width=True)
with col_btn2:
    reset_demo = st.button("🔄 Reset Demo Records", use_container_width=False)

if reset_demo:
    s = SessionLocal()
    try:
        reset_demo_records(s)
        st.success("Demo records (BATCH-DEMO-001 & RUN-DEMO-001) successfully purged. Production records preserved.")
    finally:
        s.close()

if run_demo:
    with st.spinner("Executing BF-DEMO-001 via production ETL and Detection engines..."):
        demo_output = run_complete_demo_scenario()

    st.success("✅ Scenario BF-DEMO-001 Executed Successfully!")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "1. Raw Source Systems",
        "2. ETL Pairing & Quarantine",
        "3. Reconciliation Balance",
        "4. Fraud Screening Alerts",
        "5. Ground-Truth Evaluation",
    ])

    with tab1:
        st.markdown("#### Step 1: Heterogeneous Source Grain Inspection")
        st.markdown("""
        * **Bank A:** Stores payment attempts as single flat rows (`amount_paise`, `transaction_status`).
        * **Bank B:** Stores payment events (`value_paise`, `result_code`). Contains retries for request `B-REQ-DEMO-01`.
        * **Bank C:** Stores double-entry ledger legs (`DEBIT`/`CREDIT` sharing `journal_id`).
        """)
        raw_c = demo_output["raw_counts"]
        st.info(f"Extracted: Bank A = {raw_c['bank_a_extracted']} rows | Bank B = {raw_c['bank_b_extracted']} events | Bank C = {raw_c['bank_c_extracted']} ledger entries (Total: {raw_c['total_extracted']} rows)")

    with tab2:
        st.markdown("#### Step 2: Bank C Grain Transformation & Quarantine")
        st.markdown(f"""
        * Bank C Entries Extracted: 4 entries across 2 journals.
        * **Valid Balanced Journal:** `C-J-DEMO-01` (DEBIT C-ACC-DEMO-03 ₹10,000 | CREDIT C-ACC-DEMO-04 ₹10,000) $\\rightarrow$ **1 Normalized Transfer**.
        * **Dual Lineage Preserved:** Fact row records `source_record_refs = 'C-E-DEMO-001,C-E-DEMO-002'`.
        * **Quarantined Journal:** `C-J-DEMO-ERR` has mismatched amounts (Debit ₹3,000 vs Credit ₹2,500) $\\rightarrow$ **Quarantined to `etl_rejected_record`**.
        """)
        if demo_output["quarantined_records"]:
            st.error("🚨 Quarantined Source Entries Detected during Pairing:")
            st.dataframe(pd.DataFrame(demo_output["quarantined_records"])[["source_bank_code", "source_record_id", "rejection_stage", "rejection_reason"]], hide_index=True)

    with tab3:
        st.markdown("#### Step 3: Grain-Aware Dual-Equation Reconciliation")
        rec = demo_output["reconciliation"]
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            st.write("**Equation 1: Source Row Balance**")
            st.code(f"Total Extracted ({rec['total_source_extracted']}) == Valid ({rec['total_source_valid']}) + Rejected ({rec['total_source_rejected']}) -> {rec['equation_1_source_balanced']}")
        with col_r2:
            st.write("**Equation 2: Normalized Load Balance**")
            st.code(f"Normalized Produced ({rec['normalized_produced']}) == Inserted ({rec['warehouse_inserted']}) + Skipped ({rec['duplicates_skipped']}) -> {rec['equation_2_load_balanced']}")
        st.write(f"**Monetary Volume Reconciled:** ₹{rec['normalized_amount_paise'] / 100:,.2f} strictly in integer paise.")

    with tab4:
        st.markdown("#### Step 4: Deterministic Fraud Screening Alerts")
        st.markdown("Both rules evaluated on the standardized warehouse facts without ML black-boxes:")
        warns = demo_output["warnings"]
        if warns:
            for w in warns:
                with st.chat_message("warning"):
                    st.write(f"**Rule Triggered:** `{w['Rule']}` | **Priority:** `{w['Priority']}` | **Entity:** `{w['Entity']}`")
                    st.write(f"**Evidence:** {w['Evidence']}")
        else:
            st.info("No warnings triggered.")

    with tab5:
        st.markdown("#### Step 5: Isolated Ground-Truth Evaluation")
        ev = demo_output["evaluation"]
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Precision", f"{ev['precision'] * 100:.1f}%")
        with m2:
            st.metric("Recall", f"{ev['recall'] * 100:.1f}%")
        with m3:
            st.metric("F1-Score", f"{ev['f1']:.3f}")
        with m4:
            st.metric("Accuracy", f"{ev['accuracy'] * 100:.1f}%")

        st.subheader("Confusion Matrix")
        st.table(pd.DataFrame(ev["confusion_matrix"]["matrix"]))
        st.caption(f"ℹ️ {ev['viva_note']}")

