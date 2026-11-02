"""
BankFusion Automated Test Suite: End-to-End Demo BF-DEMO-001
============================================================
Validates end-to-end demonstration execution and repeatable replayability.
"""

from demo.run_demo_case import run_complete_demo_scenario, reset_demo_records
from database.database_connection import SessionLocal
from database.database_models import FactTransaction


def test_complete_demo_scenario_execution():
    """Validates that BF-DEMO-001 runs all 13 steps and returns expected metrics."""
    res = run_complete_demo_scenario(demo_batch_id="TEST-DEMO-B1", demo_run_id="TEST-DEMO-R1")

    assert res["status"] == "DEMO_COMPLETED_SUCCESSFULLY"
    assert res["warehouse_rows_inserted"] == 7
    assert res["reconciliation"]["equation_1_source_balanced"] is True
    assert res["reconciliation"]["equation_2_load_balanced"] is True
    assert len(res["warnings"]) >= 2
    assert res["evaluation"]["precision"] == 1.0
    assert res["evaluation"]["recall"] == 1.0


def test_demo_replayability_without_duplicates():
    """Validates that replaying the demo runs cleanly without duplicate key violations."""
    # Replay 1
    res1 = run_complete_demo_scenario(demo_batch_id="TEST-DEMO-B1", demo_run_id="TEST-DEMO-R1")
    assert res1["status"] == "DEMO_COMPLETED_SUCCESSFULLY"

    # Replay 2
    res2 = run_complete_demo_scenario(demo_batch_id="TEST-DEMO-B1", demo_run_id="TEST-DEMO-R1")
    assert res2["status"] == "DEMO_COMPLETED_SUCCESSFULLY"
    assert res2["warehouse_rows_inserted"] == 7

    # Cleanup test demo batch
    session = SessionLocal()
    try:
        reset_demo_records(session, demo_batch_id="TEST-DEMO-B1", demo_run_id="TEST-DEMO-R1")
    finally:
        session.close()

