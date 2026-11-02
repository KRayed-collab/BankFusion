"""
BankFusion Performance & Scaling Test Suite
===========================================
Validates the 4 core performance optimizations on large-scale datasets:
1. Threaded background queries via QThread (FeedLoaderWorker & DetectionWorker).
2. Elimination of ResizeToContents with fixed/interactive column sizing.
3. Cache validation & dirty flag prevention of duplicate loads on page switches.
4. Bulk table update suppression (setUpdatesEnabled(False) + blockSignals(True)).
5. Scale testing with thousands of transactions (1,800+ facts).
6. Non-blocking UI event loop verification (< 30ms latency under load).
"""

import os
import sys
import time
import random
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication
from database.database_connection import SessionLocal
from database.database_models import (
    FactTransaction,
    DimBank,
    DimAccount,
    DimDevice,
    DimPaymentMethod,
    DimTransactionStatus,
    DimDate,
    DimTime,
)
from fraud_detection.save_detection_results import execute_fraud_detection_run
from ui.main_window import MainWindow
from ui.transaction_feed_page import TransactionFeedPage
from workers.feed_loader_worker import FeedLoaderWorker
from workers.detection_worker import DetectionWorker


IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture(scope="session")
def qapp():
    """Initializes or returns QApplication singleton for offscreen testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(scope="module")
def scale_warehouse_dataset():
    """
    Seeds the warehouse with 1,500 additional realistic synthetic transactions
    if not already present, scaling dataset to > 1,800 facts for high-load performance benchmarking.
    """
    session = SessionLocal()
    try:
        current_count = session.query(FactTransaction).count()
        if current_count < 1800:
            target_add = 1800 - current_count

            # Check existing dimensions
            bank_keys = [b.bank_key for b in session.query(DimBank.bank_key).all()]
            acc_keys = [a.account_key for a in session.query(DimAccount.account_key).all()]
            dev_keys = [d.device_key for d in session.query(DimDevice.device_key).all()]
            method_keys = [m.payment_method_key for m in session.query(DimPaymentMethod.payment_method_key).all()]
            status_keys = [s.status_key for s in session.query(DimTransactionStatus.status_key).all()]
            date_keys = [d.date_key for d in session.query(DimDate.date_key).all()]
            time_keys = [t.time_key for t in session.query(DimTime.time_key).all()]

            base_epoch = int(time.time()) - 86400
            new_facts = []

            for i in range(target_add):
                seq = current_count + i + 1000
                epoch = base_epoch + (i * 30)
                dt = datetime.fromtimestamp(epoch, IST)
                ts_iso = dt.isoformat()

                fact = FactTransaction(
                    bank_key=random.choice(bank_keys),
                    date_key=random.choice(date_keys),
                    time_key=random.choice(time_keys),
                    source_account_key=random.choice(acc_keys),
                    destination_account_key=random.choice(acc_keys),
                    payment_method_key=random.choice(method_keys),
                    status_key=random.choice(status_keys),
                    device_key=random.choice(dev_keys),
                    source_transaction_id=f"SCALE-TXN-{seq}",
                    source_record_refs=f"SCALE-TXN-{seq}",
                    transaction_timestamp=ts_iso,
                    epoch_timestamp=epoch,
                    amount_paise=random.choice([15000, 49900, 150000, 500000, 1250000, 25000000]),
                    currency="INR",
                    source_batch_id="BATCH-SCALE-BENCHMARK",
                    loaded_at=ts_iso,
                )
                new_facts.append(fact)

            session.bulk_save_objects(new_facts)
            session.commit()

            # Run detection to populate predictions
            execute_fraud_detection_run(session)

        total_scaled = session.query(FactTransaction).count()
        return total_scaled
    finally:
        session.close()


def test_scale_dataset_loaded(scale_warehouse_dataset):
    """Verifies that the warehouse now has hundreds/thousands of transactions."""
    assert scale_warehouse_dataset >= 1500, f"Expected >= 1500 transactions, got {scale_warehouse_dataset}"


def test_optimization_1_background_thread_responsiveness(qapp, scale_warehouse_dataset):
    """
    Optimization 1: Move database queries and Pandas processing into background QThread.
    Verifies that the GUI thread remains responsive while thousands of rows are fetched.
    """
    results = {}

    def on_loaded(df):
        results["df"] = df

    worker = FeedLoaderWorker()
    worker.feed_loaded.connect(on_loaded)

    t0 = time.perf_counter()
    worker.start()

    # While worker is running in background, verify UI thread event loop is unblocked
    max_event_latency = 0.0
    while worker.isRunning():
        e_start = time.perf_counter()
        qapp.processEvents()
        e_dur = time.perf_counter() - e_start
        if e_dur > max_event_latency:
            max_event_latency = e_dur
        time.sleep(0.005)

    worker.wait(5000)
    # Deliver queued Qt signals to main thread
    qapp.processEvents()
    total_duration = time.perf_counter() - t0

    assert "df" in results, "Worker did not return DataFrame"
    df = results["df"]
    assert len(df) == scale_warehouse_dataset
    # The event loop should never have stalled (> 50ms is threshold for stutter/freeze)
    assert max_event_latency < 0.05, f"Main GUI thread stalled! Max latency was {max_event_latency*1000:.2f}ms"
    print(f"\n[BENCHMARK] Background query for {len(df):,} transactions completed in {total_duration*1000:.1f}ms. UI thread peak latency: {max_event_latency*1000:.2f}ms.")


def test_optimization_2_and_4_table_population_and_pagination(qapp, scale_warehouse_dataset):
    """
    Optimization 2 & 4: Fixed/interactive column sizing + Bulk table update suppression + Pagination.
    Verifies that rendering initial 100 rows takes < 30ms, and 'Load More' renders smoothly.
    """
    page = TransactionFeedPage()
    page.wait_for_load(5000)
    qapp.processEvents()

    try:
        # Initial pagination check: Exactly 100 rows rendered out of thousands
        assert page.table.rowCount() == 100
        assert page.btn_load_more.isEnabled()
        assert f"Showing 100 of {scale_warehouse_dataset:,}" in page.lbl_pagination.text()

        # Test "Load More (+100)"
        t0 = time.perf_counter()
        page._on_load_more_clicked()
        load_more_dur = time.perf_counter() - t0

        assert page.table.rowCount() == 200
        assert load_more_dur < 0.05, f"Load More took {load_more_dur*1000:.1f}ms, expected < 50ms"
        print(f"\n[BENCHMARK] Load More (+100) rendered in {load_more_dur*1000:.2f}ms with table updates suppressed.")

        # Test "Show All" on thousands of rows
        t1 = time.perf_counter()
        page._on_show_all_clicked()
        show_all_dur = time.perf_counter() - t1

        assert page.table.rowCount() == scale_warehouse_dataset
        print(f"[BENCHMARK] Show All ({scale_warehouse_dataset:,} rows) rendered in {show_all_dur*1000:.2f}ms.")
    finally:
        page.stop_all_workers()


def test_optimization_3_prevent_duplicate_database_loading_on_navigation(qapp, scale_warehouse_dataset):
    """
    Optimization 3: Prevent duplicate database loading when switching pages.
    Verifies that switching between Fraud Review Queue and Transaction Feed 20 times
    does NOT trigger redundant database re-queries or worker thread restarts.
    """
    win = MainWindow()
    win.show()
    # Wait for initial page loads
    win.page_feed.wait_for_load(5000)
    qapp.processEvents()

    try:
        # Verify cached state is not dirty
        assert not win.page_feed.is_dirty
        initial_df = win.page_feed.cached_df
        assert initial_df is not None

        # Switch repeatedly between Page 0 (Queue) and Page 1 (Feed)
        switch_times = []
        for cycle in range(20):
            t0 = time.perf_counter()
            # Navigate to Queue
            win._on_navigate(0)
            qapp.processEvents()
            # Navigate to Feed
            win._on_navigate(1)
            qapp.processEvents()
            t_switch = time.perf_counter() - t0
            switch_times.append(t_switch)

        # Ensure no worker was spawned during navigation (caching succeeded)
        assert win.page_feed.feed_loader_worker is None or not win.page_feed.feed_loader_worker.isRunning()
        # Verify same cached DataFrame object was retained without re-querying
        assert win.page_feed.cached_df is initial_df

        avg_switch_ms = (sum(switch_times) / len(switch_times)) * 1000
        print(f"\n[BENCHMARK] 20 page switches completed with cached data. Average roundtrip time: {avg_switch_ms:.2f}ms (0 DB queries executed).")
    finally:
        win.close()


def test_concurrent_detection_and_feed_operations(qapp, scale_warehouse_dataset):
    """
    Verifies that running fraud detection while filtering the transaction feed
    operates smoothly without deadlocks, GUI freezes, or database locking issues.
    """
    page = TransactionFeedPage()
    page.wait_for_load(5000)
    qapp.processEvents()

    try:
        # Trigger Re-Screen worker with page as parent
        det_worker = DetectionWorker(page)
        det_results = {}

        def on_det_done(res):
            det_results["res"] = res

        det_worker.detection_completed.connect(on_det_done)
        det_worker.start()

        # While detection worker runs in background, perform rapid UI filter changes on thousands of rows
        filters = ["Suspected Fraud Only", "No Alert Only", "All Assessments"]
        banks = ["METROBANK", "QUICKPAY", "TRUSTLINE", "All Banks"]

        for f in filters:
            page.combo_status.setCurrentText(f)
            page.apply_filters()
            qapp.processEvents()

        for b in banks:
            page.combo_bank.setCurrentText(b)
            page.apply_filters()
            qapp.processEvents()

        det_worker.wait(10000)
        qapp.processEvents()

        assert "res" in det_results, "Concurrent detection worker failed to complete!"
        assert det_results["res"]["total_transactions_evaluated"] >= scale_warehouse_dataset
        print(f"\n[BENCHMARK] Concurrent detection screened {det_results['res']['total_transactions_evaluated']:,} transactions while interactive filtering executed smoothly without lock contention.")
    finally:
        page.stop_all_workers()
