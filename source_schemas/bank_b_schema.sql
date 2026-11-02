-- Bank B (QuickPay Bank) Source Schema
-- Operational Model: Event-Driven Digital Wallet & Instant Payments
-- Grain: One row represents one payment event. Multiple events may share the same
-- payment_request_ref due to user retry attempts or timeouts.

CREATE TABLE IF NOT EXISTS bank_b_events (
    event_id TEXT PRIMARY KEY,               -- Unique event identifier (e.g. B-EVT-001)
    payment_request_ref TEXT NOT NULL,       -- Intent grouping retries (e.g. B-REQ-001)
    event_timestamp TEXT NOT NULL,           -- ISO-8601 IST: YYYY-MM-DDTHH:MM:SS+05:30
    sender_wallet_ref TEXT NOT NULL,         -- Source wallet account in Bank B (e.g. B-ACC-0001)
    beneficiary_account_ref TEXT NOT NULL,   -- Destination account
    beneficiary_bank_code TEXT NOT NULL,     -- BANK_A, BANK_B, or BANK_C
    value_paise INTEGER NOT NULL CHECK(value_paise > 0), -- Amount in integer paise
    channel_code TEXT NOT NULL,              -- WALLET_TRANSFER, QR_SCAN, UPI_DIRECT
    result_code TEXT NOT NULL,               -- RC_00_SUCCESS, RC_05_FAILED, RC_99_PENDING
    device_token TEXT                        -- Hardware identifier token
);

