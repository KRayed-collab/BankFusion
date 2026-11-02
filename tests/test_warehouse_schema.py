"""
BankFusion Automated Test Suite: Phase 2 Warehouse Star Schema
==============================================================
Validates dimensional surrogate key resolution, date generation,
and star schema query integrity.
"""

from datetime import datetime, timezone, timedelta
from database.database_connection import SessionLocal
from database.initialize_database import initialize_database
from database.database_models import (
    DimBank,
    DimAccount,
    DimDate,
    DimDevice,
    FactTransaction,
)
from warehouse.warehouse_queries import (
    ensure_dim_date,
    resolve_account_key,
    resolve_device_key,
    load_dimension_cache,
    get_warehouse_summary_metrics,
)

IST = timezone(timedelta(hours=5, minutes=30))


def test_ensure_dim_date_creates_valid_member():
    """Validates that ensure_dim_date dynamically creates correctly formatted dates."""
    session = SessionLocal()
    try:
        dt = datetime(2026, 11, 15, 14, 30, tzinfo=IST)
        date_key = ensure_dim_date(session, dt)

        assert date_key == 20261115
        dim_d = session.query(DimDate).filter_by(date_key=date_key).first()
        assert dim_d is not None
        assert dim_d.full_date == "2026-11-15"
        assert dim_d.day_of_month == 15
        assert dim_d.month == 11
        assert dim_d.month_name == "November"
        assert dim_d.quarter == 4
        assert dim_d.year == 2026
        assert dim_d.is_weekend == 1  # Nov 15, 2026 is Sunday
    finally:
        session.close()


def test_account_resolution_composite_identity():
    """Validates that account resolution preserves composite uniqueness (bank_key, source_account_ref)."""
    session = SessionLocal()
    try:
        bank_a = session.query(DimBank).filter_by(bank_code="BANK_A").first()
        bank_b = session.query(DimBank).filter_by(bank_code="BANK_B").first()

        # Same account string 'ACC-9999' in Bank A vs Bank B must yield DIFFERENT surrogate keys
        key_a = resolve_account_key(session, bank_a.bank_key, "ACC-9999", "CUST-01", "SAVINGS")
        key_b = resolve_account_key(session, bank_b.bank_key, "ACC-9999", "CUST-02", "WALLET")

        assert key_a != key_b
        # Re-resolving key_a must return the same surrogate key (idempotent lookup)
        key_a_repeat = resolve_account_key(session, bank_a.bank_key, "ACC-9999")
        assert key_a == key_a_repeat
    finally:
        session.close()


def test_device_resolution_and_unknown_fallback():
    """Validates device surrogate keys and unknown device handling."""
    session = SessionLocal()
    try:
        # None or empty string maps to surrogate 'UNKNOWN_DEVICE'
        key_null = resolve_device_key(session, None)
        key_empty = resolve_device_key(session, "")
        assert key_null == key_empty

        dev_unknown = session.query(DimDevice).filter_by(device_key=key_null).first()
        assert dev_unknown.device_token == "UNKNOWN_DEVICE"
        assert dev_unknown.is_known == 0

        # Named token
        key_dev1 = resolve_device_key(session, "SIM-DEVICE-TEST-99")
        assert key_dev1 != key_null
        dev_named = session.query(DimDevice).filter_by(device_key=key_dev1).first()
        assert dev_named.is_known == 1
    finally:
        session.close()


def test_dimension_cache_loader():
    """Validates that cache dictionary preloads all expected dimension maps."""
    session = SessionLocal()
    try:
        cache = load_dimension_cache(session)
        assert "BANK_A" in cache["banks"]
        assert "BANK_B" in cache["banks"]
        assert "BANK_C" in cache["banks"]
        assert "UPI" in cache["methods"]
        assert "SUCCESS" in cache["statuses"]
        assert "UNKNOWN_DEVICE" in cache["devices"]
    finally:
        session.close()

