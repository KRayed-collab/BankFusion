"""
BankFusion Database Migration Engine
====================================
Idempotent, safe schema migrations for BankFusion SQLite databases.
Ensures that all tables and columns expected by SQLAlchemy models exist
before any application, service, or worker queries are executed.

Features:
- Column addition for existing tables (e.g. triggered_factor_count).
- Safe historical backfill computing factor counts from existing boolean rule flags.
- Handles NULL values safely as 0.
- Table creation for new enforcement and audit models.
- Idempotent: safe to run repeatedly across application restarts.
- Resolves and verifies the exact SQLite file being opened.
"""

import os
import sys
import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger("BankFusion.Migrations")


class DatabaseMigrationError(Exception):
    """Raised when an automated database migration fails."""
    pass


def get_active_sqlite_db_path() -> Path:
    """
    Resolves the exact absolute filesystem path of the SQLite database currently in use.
    Handles environment variable DATABASE_URL, PyInstaller %APPDATA%, and dev project root.
    """
    from database.database_connection import DEFAULT_DB_PATH, engine

    # Inspect the engine's active URL
    engine_url = str(engine.url)
    if engine_url.startswith("sqlite:///"):
        raw_path = engine_url[len("sqlite:///"):]
        return Path(raw_path).resolve()

    return DEFAULT_DB_PATH.resolve()


def run_database_migrations(db_path: Optional[Path | str] = None) -> Dict[str, Any]:
    """
    Executes all pending database migrations against the specified SQLite database file.
    If db_path is None, migrates the active database returned by get_active_sqlite_db_path().

    Returns a summary dictionary:
    {
        "success": True,
        "db_path": str(resolved_path),
        "applied_migrations": List[str],
        "rows_backfilled": int,
    }
    """
    if db_path is None:
        target_path = get_active_sqlite_db_path()
    else:
        target_path = Path(db_path).resolve()

    if not target_path.exists():
        # Parent directory must exist
        target_path.parent.mkdir(parents=True, exist_ok=True)

    applied = []
    rows_backfilled = 0

    print(f"[MIGRATION] Checking database schema at: {target_path}")

    # Connect directly with sqlite3
    conn = sqlite3.connect(str(target_path), timeout=30.0)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys = OFF;")  # Allow table alters safely during migration

        # ----------------------------------------------------------------------
        # Migration 1: triggered_factor_count in fraud_transaction_prediction
        # ----------------------------------------------------------------------
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fraud_transaction_prediction'")
        if cur.fetchone():
            # Table exists; inspect columns
            cur.execute("PRAGMA table_info(fraud_transaction_prediction)")
            columns = [col[1] for col in cur.fetchall()]

            if "triggered_factor_count" not in columns:
                print("[MIGRATION] Adding column 'triggered_factor_count' to fraud_transaction_prediction...")
                cur.execute(
                    "ALTER TABLE fraud_transaction_prediction "
                    "ADD COLUMN triggered_factor_count INTEGER NOT NULL DEFAULT 0;"
                )

                # Backfill historical factor counts safely handling NULLs
                print("[MIGRATION] Backfilling triggered_factor_count for historical prediction records...")
                cur.execute("""
                    UPDATE fraud_transaction_prediction
                    SET triggered_factor_count = (
                        CASE WHEN coalesce(flagged_by_velocity, 0) != 0 THEN 1 ELSE 0 END +
                        CASE WHEN coalesce(flagged_by_device, 0) != 0 THEN 1 ELSE 0 END +
                        CASE WHEN coalesce(flagged_by_large_amount, 0) != 0 THEN 1 ELSE 0 END +
                        CASE WHEN coalesce(flagged_by_cross_bank_movement, 0) != 0 THEN 1 ELSE 0 END
                    );
                """)
                cur.execute("SELECT changes();")
                rows_backfilled = cur.fetchone()[0]
                applied.append(f"Add triggered_factor_count column ({rows_backfilled} rows backfilled)")
                print(f"[MIGRATION] Successfully backfilled {rows_backfilled} historical prediction records.")
            else:
                # Column exists; ensure any rows with NULL or 0 that have active flags are properly updated
                cur.execute("""
                    UPDATE fraud_transaction_prediction
                    SET triggered_factor_count = (
                        CASE WHEN coalesce(flagged_by_velocity, 0) != 0 THEN 1 ELSE 0 END +
                        CASE WHEN coalesce(flagged_by_device, 0) != 0 THEN 1 ELSE 0 END +
                        CASE WHEN coalesce(flagged_by_large_amount, 0) != 0 THEN 1 ELSE 0 END +
                        CASE WHEN coalesce(flagged_by_cross_bank_movement, 0) != 0 THEN 1 ELSE 0 END
                    )
                    WHERE triggered_factor_count IS NULL
                       OR (triggered_factor_count = 0 AND is_predicted_suspicious = 1);
                """)
                repaired = cur.rowcount
                if repaired > 0:
                    applied.append(f"Synchronized {repaired} factor count values")

        # ----------------------------------------------------------------------
        # Migration 2: transaction_enforcement_record table
        # ----------------------------------------------------------------------
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transaction_enforcement_record'")
        if not cur.fetchone():
            print("[MIGRATION] Creating table 'transaction_enforcement_record'...")
            cur.execute("""
                CREATE TABLE transaction_enforcement_record (
                    enforcement_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_key INTEGER NOT NULL REFERENCES warehouse_fact_transaction(transaction_key),
                    source_bank_code TEXT NOT NULL,
                    source_transaction_id TEXT NOT NULL,
                    detection_run_id TEXT NOT NULL REFERENCES fraud_detection_run(detection_run_id),
                    enforcement_status TEXT NOT NULL DEFAULT 'CLEAR',
                    risk_tier TEXT NOT NULL DEFAULT 'CLEAR',
                    triggered_factor_count INTEGER NOT NULL DEFAULT 0,
                    triggered_factors_summary TEXT NOT NULL DEFAULT 'None',
                    blocking_reason TEXT,
                    is_active_block INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    blocked_at TEXT,
                    released_at TEXT,
                    released_by TEXT,
                    release_reason TEXT,
                    CONSTRAINT uq_run_txn_enforcement UNIQUE (detection_run_id, transaction_key)
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_enf_status_active ON transaction_enforcement_record (enforcement_status, is_active_block);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_enf_txn_key ON transaction_enforcement_record (transaction_key);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_enf_src_txn_id ON transaction_enforcement_record (source_transaction_id);")
            applied.append("Create transaction_enforcement_record table")

        # ----------------------------------------------------------------------
        # Migration 3: enforcement_audit_log table
        # ----------------------------------------------------------------------
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='enforcement_audit_log'")
        if not cur.fetchone():
            print("[MIGRATION] Creating table 'enforcement_audit_log'...")
            cur.execute("""
                CREATE TABLE enforcement_audit_log (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_key INTEGER NOT NULL REFERENCES warehouse_fact_transaction(transaction_key),
                    source_transaction_id TEXT NOT NULL,
                    detection_run_id TEXT,
                    previous_status TEXT NOT NULL,
                    new_status TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    operator_id TEXT NOT NULL DEFAULT 'SYSTEM',
                    action_reason TEXT,
                    timestamp TEXT NOT NULL
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_txn_key ON enforcement_audit_log (transaction_key);")
            applied.append("Create enforcement_audit_log table")

        conn.commit()
        cur.execute("PRAGMA foreign_keys = ON;")

    except Exception as exc:
        conn.rollback()
        error_msg = f"Failed to execute schema migrations on '{target_path}': {exc}"
        print(f"[ERROR] {error_msg}")
        raise DatabaseMigrationError(error_msg) from exc
    finally:
        conn.close()

    print(f"[MIGRATION] Migration completed successfully on {target_path}. Applied: {applied or ['Schema up to date']}")
    return {
        "success": True,
        "db_path": str(target_path),
        "applied_migrations": applied,
        "rows_backfilled": rows_backfilled,
    }


if __name__ == "__main__":
    res = run_database_migrations()
    print("[MIGRATION RUNNER RESULT]", res)

