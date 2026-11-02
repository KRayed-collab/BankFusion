-- BankFusion Common Data Warehouse Schema
-- Star Schema Design (Kimball Methodology)
-- SQLite Database Specification

-- ============================================================================
-- 1. CONFORMED DIMENSIONS
-- ============================================================================

CREATE TABLE IF NOT EXISTS warehouse_dim_bank (
    bank_key INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_code TEXT NOT NULL UNIQUE,      -- BANK_A, BANK_B, BANK_C
    bank_name TEXT NOT NULL,
    bank_type TEXT NOT NULL               -- RETAIL_CORE, DIGITAL_WALLET, LEDGER_CORE
);

CREATE TABLE IF NOT EXISTS warehouse_dim_account (
    account_key INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_key INTEGER NOT NULL REFERENCES warehouse_dim_bank(bank_key),
    source_account_ref TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    account_type TEXT NOT NULL,           -- SAVINGS, CURRENT, WALLET, COMMERCIAL, PERSONAL
    created_at TEXT NOT NULL,
    UNIQUE(bank_key, source_account_ref)  -- Composite natural identity
);

CREATE TABLE IF NOT EXISTS warehouse_dim_date (
    date_key INTEGER PRIMARY KEY,         -- YYYYMMDD (e.g. 20261101)
    full_date TEXT NOT NULL UNIQUE,       -- YYYY-MM-DD
    day_of_month INTEGER NOT NULL,
    month INTEGER NOT NULL,
    month_name TEXT NOT NULL,
    quarter INTEGER NOT NULL,
    year INTEGER NOT NULL,
    is_weekend INTEGER NOT NULL           -- 0 or 1
);

CREATE TABLE IF NOT EXISTS warehouse_dim_time (
    time_key INTEGER PRIMARY KEY,         -- HHMM (e.g. 1430 for 14:30)
    hour INTEGER NOT NULL,
    minute INTEGER NOT NULL,
    time_of_day TEXT NOT NULL             -- Morning, Afternoon, Evening, Night
);

CREATE TABLE IF NOT EXISTS warehouse_dim_payment_method (
    payment_method_key INTEGER PRIMARY KEY AUTOINCREMENT,
    method_code TEXT NOT NULL UNIQUE,     -- UPI, IMPS, NEFT, RTGS, CARD, WALLET, BOOK_TRANSFER
    method_category TEXT NOT NULL         -- INSTANT, BATCH, CARDS, INTERNAL
);

CREATE TABLE IF NOT EXISTS warehouse_dim_transaction_status (
    status_key INTEGER PRIMARY KEY AUTOINCREMENT,
    status_code TEXT NOT NULL UNIQUE,     -- SUCCESS, FAILED, PENDING
    is_terminal INTEGER NOT NULL          -- 1 for terminal, 0 for in-flight
);

CREATE TABLE IF NOT EXISTS warehouse_dim_device (
    device_key INTEGER PRIMARY KEY AUTOINCREMENT,
    device_token TEXT NOT NULL UNIQUE,
    is_known INTEGER NOT NULL DEFAULT 1   -- 0 for surrogate 'UNKNOWN_DEVICE' (key 1)
);

-- ============================================================================
-- 2. CENTRAL FACT TABLE
-- Grain: 1 normalized payment attempt (A, B) or 1 valid posted transfer (C journal)
-- ============================================================================

CREATE TABLE IF NOT EXISTS warehouse_fact_transaction (
    transaction_key INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_key INTEGER NOT NULL REFERENCES warehouse_dim_bank(bank_key),
    date_key INTEGER NOT NULL REFERENCES warehouse_dim_date(date_key),
    time_key INTEGER NOT NULL REFERENCES warehouse_dim_time(time_key),
    source_account_key INTEGER NOT NULL REFERENCES warehouse_dim_account(account_key),
    destination_account_key INTEGER NOT NULL REFERENCES warehouse_dim_account(account_key),
    payment_method_key INTEGER NOT NULL REFERENCES warehouse_dim_payment_method(payment_method_key),
    status_key INTEGER NOT NULL REFERENCES warehouse_dim_transaction_status(status_key),
    device_key INTEGER NOT NULL REFERENCES warehouse_dim_device(device_key),

    source_transaction_id TEXT NOT NULL,  -- A: txn_id, B: event_id, C: journal_id
    source_record_refs TEXT NOT NULL,     -- A: txn_id, B: event_id, C: "C-E-001,C-E-002"
    transaction_timestamp TEXT NOT NULL,  -- ISO-8601 IST string
    epoch_timestamp INTEGER NOT NULL,     -- Unix epoch (seconds) for window evaluations

    amount_paise INTEGER NOT NULL CHECK(amount_paise > 0),
    currency TEXT NOT NULL DEFAULT 'INR',

    source_batch_id TEXT NOT NULL,
    loaded_at TEXT NOT NULL,

    UNIQUE(bank_key, source_transaction_id) -- Database-level Idempotency
);

CREATE INDEX IF NOT EXISTS idx_fact_source_acc_epoch ON warehouse_fact_transaction(source_account_key, epoch_timestamp);
CREATE INDEX IF NOT EXISTS idx_fact_device_epoch ON warehouse_fact_transaction(device_key, epoch_timestamp);
CREATE INDEX IF NOT EXISTS idx_fact_date_key ON warehouse_fact_transaction(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_bank_key ON warehouse_fact_transaction(bank_key);

