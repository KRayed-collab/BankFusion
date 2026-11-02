-- Bank A (MetroBank) Source Schema
-- Operational Model: Conventional Retail Core Banking
-- Grain: One row represents one payment attempt (successful, failed, or pending)

CREATE TABLE IF NOT EXISTS bank_a_transactions (
    transaction_id TEXT PRIMARY KEY,
    transaction_timestamp TEXT NOT NULL,      -- ISO-8601 IST: YYYY-MM-DDTHH:MM:SS+05:30
    sender_account_ref TEXT NOT NULL,         -- Source account in Bank A (e.g. A-ACC-0001)
    receiver_account_ref TEXT NOT NULL,       -- Destination account
    receiver_bank_code TEXT NOT NULL,         -- BANK_A, BANK_B, or BANK_C
    amount_paise INTEGER NOT NULL CHECK(amount_paise > 0), -- Stored in integer paise (1 INR = 100 paise)
    payment_mode TEXT NOT NULL,               -- UPI, NEFT, IMPS, RTGS, CARD
    transaction_status TEXT NOT NULL,         -- SUCCESS, FAILED, PENDING
    device_token TEXT                         -- Hardware identifier token (e.g. SIM-DEVICE-001)
);

