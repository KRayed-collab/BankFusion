-- Bank C (TrustLine Bank) Source Schema
-- Operational Model: Double-Entry Accounting Ledger
-- Grain: Two rows represent one business transfer (one DEBIT leg, one CREDIT leg).
-- Both legs share the same journal_id and must match in amount, currency, and posted status.
-- Scope: Strictly internal TrustLine book transfers (counterparty_bank_code = 'BANK_C').

CREATE TABLE IF NOT EXISTS bank_c_ledger_entries (
    entry_id TEXT PRIMARY KEY,               -- Unique ledger entry (e.g. C-E-001)
    journal_id TEXT NOT NULL,                -- Identifier binding paired legs (e.g. C-J-1001)
    posting_timestamp TEXT NOT NULL,         -- ISO-8601 IST: YYYY-MM-DDTHH:MM:SS+05:30
    ledger_account_ref TEXT NOT NULL,        -- Posting account for this leg (e.g. C-ACC-0001)
    counterparty_account_ref TEXT NOT NULL,  -- Reciprocal account
    counterparty_bank_code TEXT NOT NULL DEFAULT 'BANK_C',
    entry_side TEXT NOT NULL CHECK(entry_side IN ('DEBIT', 'CREDIT')),
    amount_paise INTEGER NOT NULL CHECK(amount_paise > 0), -- Amount in integer paise
    currency TEXT NOT NULL DEFAULT 'INR',
    transfer_type TEXT NOT NULL CHECK(transfer_type IN ('BOOK_TRANSFER', 'INTERNAL_LEDGER_TRANSFER')),
    entry_status TEXT NOT NULL,              -- POSTED, UNPOSTED, REJECTED
    device_token TEXT                        -- Optional hardware identifier token
);

