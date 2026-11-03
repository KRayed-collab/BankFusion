"""
BankFusion Database Initialization
==================================
Creates all tables across source, warehouse, audit, and evaluation layers.
Seeds constant dimension records:
- DimBank (BANK_A, BANK_B, BANK_C)
- DimPaymentMethod (UPI, IMPS, NEFT, RTGS, CARD, WALLET, BOOK_TRANSFER)
- DimTransactionStatus (SUCCESS, FAILED, PENDING)
- DimDevice (Surrogate 'UNKNOWN_DEVICE')
- DimTime (Full 24-hour cycle: 1,440 minute dimension members)
"""

import sys
import argparse
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.orm import Session
from database.database_connection import engine, SessionLocal, Base
from database.migrations import run_database_migrations, get_active_sqlite_db_path
from database.database_models import (
    DimBank,
    DimPaymentMethod,
    DimTransactionStatus,
    DimDevice,
    DimTime,
)


def seed_fixed_dimensions(session: Session) -> None:
    """Seeds static, conformed dimensions if not already present."""

    # 1. Banks
    banks = [
        {"bank_code": "BANK_A", "bank_name": "MetroBank", "bank_type": "RETAIL_CORE"},
        {"bank_code": "BANK_B", "bank_name": "QuickPay Bank", "bank_type": "DIGITAL_WALLET"},
        {"bank_code": "BANK_C", "bank_name": "TrustLine Bank", "bank_type": "LEDGER_CORE"},
    ]
    for b in banks:
        if not session.query(DimBank).filter_by(bank_code=b["bank_code"]).first():
            session.add(DimBank(**b))

    # 2. Payment Methods
    methods = [
        {"method_code": "UPI", "method_category": "INSTANT"},
        {"method_code": "IMPS", "method_category": "INSTANT"},
        {"method_code": "NEFT", "method_category": "BATCH"},
        {"method_code": "RTGS", "method_category": "BATCH"},
        {"method_code": "CARD", "method_category": "CARDS"},
        {"method_code": "WALLET", "method_category": "INSTANT"},
        {"method_code": "BOOK_TRANSFER", "method_category": "INTERNAL"},
    ]
    for m in methods:
        if not session.query(DimPaymentMethod).filter_by(method_code=m["method_code"]).first():
            session.add(DimPaymentMethod(**m))

    # 3. Transaction Statuses
    statuses = [
        {"status_code": "SUCCESS", "is_terminal": 1},
        {"status_code": "FAILED", "is_terminal": 1},
        {"status_code": "PENDING", "is_terminal": 0},
    ]
    for s in statuses:
        if not session.query(DimTransactionStatus).filter_by(status_code=s["status_code"]).first():
            session.add(DimTransactionStatus(**s))

    # 4. Surrogate Unknown Device (device_key for NULL or unavailable devices)
    if not session.query(DimDevice).filter_by(device_token="UNKNOWN_DEVICE").first():
        session.add(DimDevice(device_token="UNKNOWN_DEVICE", is_known=0))

    # 5. Time Dimension (24 hours x 60 minutes = 1440 rows)
    existing_time_count = session.query(DimTime).count()
    if existing_time_count < 1440:
        time_members = []
        for hour in range(24):
            for minute in range(60):
                time_key = hour * 100 + minute
                if 5 <= hour < 12:
                    time_of_day = "Morning"
                elif 12 <= hour < 17:
                    time_of_day = "Afternoon"
                elif 17 <= hour < 21:
                    time_of_day = "Evening"
                else:
                    time_of_day = "Night"

                time_members.append(
                    DimTime(
                        time_key=time_key,
                        hour=hour,
                        minute=minute,
                        time_of_day=time_of_day,
                    )
                )
        session.bulk_save_objects(time_members)

    session.commit()


def initialize_database(reset: bool = False) -> None:
    """Initializes the database schema and populates base dimensions."""
    if reset:
        print("[INIT] Dropping all existing database tables...")
        Base.metadata.drop_all(bind=engine)

    print("[INIT] Creating tables according to database models...")
    Base.metadata.create_all(bind=engine)
    run_database_migrations(get_active_sqlite_db_path())

    session = SessionLocal()
    try:
        print("[INIT] Seeding fixed dimensions (Banks, Methods, Statuses, Device, Time)...")
        seed_fixed_dimensions(session)
        print("[INIT] Database initialized successfully.")
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize BankFusion SQLite Database")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables")
    args = parser.parse_args()

    initialize_database(reset=args.reset)
