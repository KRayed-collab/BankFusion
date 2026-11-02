"""
BankFusion Automated Test Suite: Phase 4 OLAP Analytics
=======================================================
Validates Slice, Dice, Roll-up, Drill-down, and Bank Comparison metrics.
"""

from database.database_connection import SessionLocal
from warehouse.warehouse_queries import get_denormalized_fact_dataframe
from analytics.olap_operations import olap_slice, olap_dice, olap_roll_up
from analytics.bank_comparison import generate_bank_comparison_metrics


def test_olap_slice_by_bank():
    """Validates that slicing by bank returns exclusively records for that bank."""
    session = SessionLocal()
    try:
        df = get_denormalized_fact_dataframe(session)
        assert not df.empty

        sliced_a = olap_slice(df, "bank_code", "BANK_A")
        assert not sliced_a.empty
        assert (sliced_a["bank_code"] == "BANK_A").all()

        sliced_b = olap_slice(df, "bank_code", "BANK_B")
        assert not sliced_b.empty
        assert (sliced_b["bank_code"] == "BANK_B").all()
    finally:
        session.close()


def test_olap_dice_multidimensional():
    """Validates that dicing applies simultaneous multi-column conditions."""
    session = SessionLocal()
    try:
        df = get_denormalized_fact_dataframe(session)
        diced = olap_dice(
            df,
            banks=["BANK_A", "BANK_B"],
            statuses=["SUCCESS"],
            min_amount_inr=100.0,
        )

        assert not diced.empty
        assert diced["bank_code"].isin(["BANK_A", "BANK_B"]).all()
        assert (diced["transaction_status"] == "SUCCESS").all()
        assert (diced["amount_inr"] >= 100.0).all()
    finally:
        session.close()


def test_olap_roll_up_and_bank_comparison():
    """Validates temporal aggregation and bank comparison table."""
    session = SessionLocal()
    try:
        df = get_denormalized_fact_dataframe(session)
        daily_roll = olap_roll_up(df, level="daily")
        assert not daily_roll.empty
        assert "full_date" in daily_roll.columns
        assert daily_roll["total_attempts"].sum() == len(df)

        comparison = generate_bank_comparison_metrics(df)
        assert len(comparison) == 3
        bank_codes = set(comparison["Bank Code"])
        assert bank_codes == {"BANK_A", "BANK_B", "BANK_C"}
        for _, row in comparison.iterrows():
            assert row["Total Attempts"] > 0
            assert row["Success Rate (%)"] >= 0.0
    finally:
        session.close()

