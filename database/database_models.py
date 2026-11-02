"""
BankFusion Database Models
==========================
Defines all SQLAlchemy ORM models for:
1. Source Bank Systems (bank_a_transactions, bank_b_events, bank_c_ledger_entries)
2. Common Data Warehouse Star Schema (dimensions + FactTransaction)
3. ETL Audit & Quality Tables (etl_batch_log, etl_rejected_record)
4. Fraud Intelligence & Evaluation (fraud_detection_run, fraud_screening_warning,
   fraud_transaction_prediction, evaluation_ground_truth)
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    Index,
)
from sqlalchemy.orm import relationship
from database.database_connection import Base


# ============================================================================
# 1. SOURCE SYSTEM MODELS
# ============================================================================

class BankATransaction(Base):
    """
    Bank A (MetroBank) Source Record
    Grain: 1 row = 1 payment attempt
    """
    __tablename__ = "bank_a_transactions"

    transaction_id = Column(String, primary_key=True)
    transaction_timestamp = Column(String, nullable=False, index=True)
    sender_account_ref = Column(String, nullable=False, index=True)
    receiver_account_ref = Column(String, nullable=False)
    receiver_bank_code = Column(String, nullable=False)
    amount_paise = Column(Integer, nullable=False)
    payment_mode = Column(String, nullable=False)
    transaction_status = Column(String, nullable=False)
    device_token = Column(String, nullable=True, index=True)

    __table_args__ = (
        CheckConstraint("amount_paise > 0", name="chk_bank_a_amount_positive"),
    )


class BankBEvent(Base):
    """
    Bank B (QuickPay Bank) Source Event
    Grain: 1 row = 1 payment event/attempt (retries allowed under payment_request_ref)
    """
    __tablename__ = "bank_b_events"

    event_id = Column(String, primary_key=True)
    payment_request_ref = Column(String, nullable=False, index=True)
    event_timestamp = Column(String, nullable=False, index=True)
    sender_wallet_ref = Column(String, nullable=False, index=True)
    beneficiary_account_ref = Column(String, nullable=False)
    beneficiary_bank_code = Column(String, nullable=False)
    value_paise = Column(Integer, nullable=False)
    channel_code = Column(String, nullable=False)
    result_code = Column(String, nullable=False)
    device_token = Column(String, nullable=True, index=True)

    __table_args__ = (
        CheckConstraint("value_paise > 0", name="chk_bank_b_value_positive"),
    )


class BankCLedgerEntry(Base):
    """
    Bank C (TrustLine Bank) Double-Entry Ledger
    Grain: 2 rows = 1 business transfer (1 DEBIT leg, 1 CREDIT leg sharing journal_id)
    Strictly internal book transfers (counterparty_bank_code = 'BANK_C')
    """
    __tablename__ = "bank_c_ledger_entries"

    entry_id = Column(String, primary_key=True)
    journal_id = Column(String, nullable=False, index=True)
    posting_timestamp = Column(String, nullable=False, index=True)
    ledger_account_ref = Column(String, nullable=False, index=True)
    counterparty_account_ref = Column(String, nullable=False)
    counterparty_bank_code = Column(String, nullable=False, default="BANK_C")
    entry_side = Column(String, nullable=False)  # 'DEBIT' or 'CREDIT'
    amount_paise = Column(Integer, nullable=False)
    currency = Column(String, nullable=False, default="INR")
    transfer_type = Column(String, nullable=False)  # 'BOOK_TRANSFER', 'INTERNAL_LEDGER_TRANSFER'
    entry_status = Column(String, nullable=False)   # 'POSTED', 'UNPOSTED', 'REJECTED'
    device_token = Column(String, nullable=True, index=True)

    __table_args__ = (
        CheckConstraint("amount_paise > 0", name="chk_bank_c_amount_positive"),
        CheckConstraint("entry_side IN ('DEBIT', 'CREDIT')", name="chk_bank_c_side_valid"),
    )


# ============================================================================
# 2. COMMON DATA WAREHOUSE (STAR SCHEMA)
# ============================================================================

class DimBank(Base):
    """Bank Dimension"""
    __tablename__ = "warehouse_dim_bank"

    bank_key = Column(Integer, primary_key=True, autoincrement=True)
    bank_code = Column(String, nullable=False, unique=True)
    bank_name = Column(String, nullable=False)
    bank_type = Column(String, nullable=False)


class DimAccount(Base):
    """
    Account Dimension
    Natural composite identity: (bank_key, source_account_ref)
    """
    __tablename__ = "warehouse_dim_account"

    account_key = Column(Integer, primary_key=True, autoincrement=True)
    bank_key = Column(Integer, ForeignKey("warehouse_dim_bank.bank_key"), nullable=False)
    source_account_ref = Column(String, nullable=False)
    customer_id = Column(String, nullable=False)
    account_type = Column(String, nullable=False)
    created_at = Column(String, nullable=False)

    bank = relationship("DimBank")

    __table_args__ = (
        UniqueConstraint("bank_key", "source_account_ref", name="uq_account_bank_ref"),
        Index("idx_dim_account_ref", "bank_key", "source_account_ref"),
    )


class DimDate(Base):
    """Date Dimension (Role: Transaction Calendar)"""
    __tablename__ = "warehouse_dim_date"

    date_key = Column(Integer, primary_key=True)  # YYYYMMDD
    full_date = Column(String, nullable=False, unique=True)
    day_of_month = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    month_name = Column(String, nullable=False)
    quarter = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    is_weekend = Column(Integer, nullable=False)


class DimTime(Base):
    """Time Dimension (Role: Clock Hour/Minute)"""
    __tablename__ = "warehouse_dim_time"

    time_key = Column(Integer, primary_key=True)  # HHMM
    hour = Column(Integer, nullable=False)
    minute = Column(Integer, nullable=False)
    time_of_day = Column(String, nullable=False)  # Morning, Afternoon, Evening, Night


class DimPaymentMethod(Base):
    """Payment Method Dimension"""
    __tablename__ = "warehouse_dim_payment_method"

    payment_method_key = Column(Integer, primary_key=True, autoincrement=True)
    method_code = Column(String, nullable=False, unique=True)
    method_category = Column(String, nullable=False)


class DimTransactionStatus(Base):
    """Transaction Status Dimension"""
    __tablename__ = "warehouse_dim_transaction_status"

    status_key = Column(Integer, primary_key=True, autoincrement=True)
    status_code = Column(String, nullable=False, unique=True)
    is_terminal = Column(Integer, nullable=False)


class DimDevice(Base):
    """
    Device Dimension
    device_key = 0 corresponds to surrogate 'UNKNOWN_DEVICE'
    """
    __tablename__ = "warehouse_dim_device"

    device_key = Column(Integer, primary_key=True, autoincrement=True)
    device_token = Column(String, nullable=False, unique=True)
    is_known = Column(Integer, nullable=False, default=1)


class FactTransaction(Base):
    """
    Central Fact Table
    Grain: 1 normalized payment attempt (A, B) or 1 valid posted transfer (C journal pair)
    """
    __tablename__ = "warehouse_fact_transaction"

    transaction_key = Column(Integer, primary_key=True, autoincrement=True)
    bank_key = Column(Integer, ForeignKey("warehouse_dim_bank.bank_key"), nullable=False)
    date_key = Column(Integer, ForeignKey("warehouse_dim_date.date_key"), nullable=False)
    time_key = Column(Integer, ForeignKey("warehouse_dim_time.time_key"), nullable=False)
    source_account_key = Column(Integer, ForeignKey("warehouse_dim_account.account_key"), nullable=False)
    destination_account_key = Column(Integer, ForeignKey("warehouse_dim_account.account_key"), nullable=False)
    payment_method_key = Column(Integer, ForeignKey("warehouse_dim_payment_method.payment_method_key"), nullable=False)
    status_key = Column(Integer, ForeignKey("warehouse_dim_transaction_status.status_key"), nullable=False)
    device_key = Column(Integer, ForeignKey("warehouse_dim_device.device_key"), nullable=False)

    source_transaction_id = Column(String, nullable=False)  # A: txn_id, B: event_id, C: journal_id
    source_record_refs = Column(String, nullable=False)     # A: txn_id, B: event_id, C: "C-E-001,C-E-002"
    transaction_timestamp = Column(String, nullable=False)
    epoch_timestamp = Column(Integer, nullable=False, index=True)

    amount_paise = Column(Integer, nullable=False)
    currency = Column(String, nullable=False, default="INR")

    source_batch_id = Column(String, nullable=False, index=True)
    loaded_at = Column(String, nullable=False)

    # Relationships for fast object traversal
    bank = relationship("DimBank", foreign_keys=[bank_key])
    date = relationship("DimDate", foreign_keys=[date_key])
    time = relationship("DimTime", foreign_keys=[time_key])
    source_account = relationship("DimAccount", foreign_keys=[source_account_key])
    destination_account = relationship("DimAccount", foreign_keys=[destination_account_key])
    payment_method = relationship("DimPaymentMethod", foreign_keys=[payment_method_key])
    status = relationship("DimTransactionStatus", foreign_keys=[status_key])
    device = relationship("DimDevice", foreign_keys=[device_key])

    __table_args__ = (
        UniqueConstraint("bank_key", "source_transaction_id", name="uq_fact_bank_source_txn"),
        Index("idx_fact_source_acc_epoch", "source_account_key", "epoch_timestamp"),
        Index("idx_fact_device_epoch", "device_key", "epoch_timestamp"),
    )


# ============================================================================
# 3. ETL AUDIT & RECONCILIATION TABLES
# ============================================================================

class ETLBatchLog(Base):
    """
    ETL Batch Execution & Grain-Aware Reconciliation Log
    Tracks both row balances and complete monetary decompositions in integer paise.
    """
    __tablename__ = "etl_batch_log"

    batch_id = Column(String, primary_key=True)
    batch_timestamp = Column(String, nullable=False)
    status = Column(String, nullable=False)  # 'STARTED', 'COMPLETED', 'FAILED'

    # Bank A Row Counters
    bank_a_rows_extracted = Column(Integer, nullable=False, default=0)
    bank_a_rows_valid = Column(Integer, nullable=False, default=0)
    bank_a_rows_rejected = Column(Integer, nullable=False, default=0)

    # Bank B Row Counters
    bank_b_rows_extracted = Column(Integer, nullable=False, default=0)
    bank_b_rows_valid = Column(Integer, nullable=False, default=0)
    bank_b_rows_rejected = Column(Integer, nullable=False, default=0)

    # Bank C Entry & Journal Counters
    bank_c_entries_extracted = Column(Integer, nullable=False, default=0)
    bank_c_entries_valid = Column(Integer, nullable=False, default=0)
    bank_c_entries_rejected = Column(Integer, nullable=False, default=0)
    bank_c_valid_journals = Column(Integer, nullable=False, default=0)

    # Aggregated Row Reconciliation
    total_source_rows_extracted = Column(Integer, nullable=False, default=0)
    total_valid_source_rows = Column(Integer, nullable=False, default=0)
    total_rejected_source_rows = Column(Integer, nullable=False, default=0)

    # Warehouse Loading Counters
    normalized_warehouse_transactions_produced = Column(Integer, nullable=False, default=0)
    warehouse_rows_inserted = Column(Integer, nullable=False, default=0)
    duplicate_rows_skipped = Column(Integer, nullable=False, default=0)

    # Complete Monetary Reconciliation (Integer Paise)
    normalized_amount_paise_produced = Column(Integer, nullable=False, default=0)
    warehouse_amount_paise_inserted = Column(Integer, nullable=False, default=0)
    duplicate_amount_paise_skipped = Column(Integer, nullable=False, default=0)

    # Status Breakdown: Newly Inserted
    successful_amount_paise_inserted = Column(Integer, nullable=False, default=0)
    failed_amount_paise_inserted = Column(Integer, nullable=False, default=0)
    pending_amount_paise_inserted = Column(Integer, nullable=False, default=0)

    # Status Breakdown: Duplicate Skipped
    successful_amount_paise_skipped = Column(Integer, nullable=False, default=0)
    failed_amount_paise_skipped = Column(Integer, nullable=False, default=0)
    pending_amount_paise_skipped = Column(Integer, nullable=False, default=0)

    execution_duration_sec = Column(Float, nullable=False, default=0.0)


class ETLRejectedRecord(Base):
    """
    Quarantine Table for Invalid or Unpaired Source Records
    """
    __tablename__ = "etl_rejected_record"

    rejection_id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String, nullable=False, index=True)
    source_bank_code = Column(String, nullable=False)
    source_record_id = Column(String, nullable=False)
    rejection_stage = Column(String, nullable=False)  # 'VALIDATE', 'PAIRING', 'TRANSFORM'
    rejection_reason = Column(String, nullable=False)
    raw_payload = Column(String, nullable=False)
    recorded_at = Column(String, nullable=False)


# ============================================================================
# 4. FRAUD DETECTION RUNS, WARNINGS & PREDICTIONS
# ============================================================================

class FraudDetectionRun(Base):
    """Tracks each execution of the fraud detection screening rules"""
    __tablename__ = "fraud_detection_run"

    detection_run_id = Column(String, primary_key=True)
    run_timestamp = Column(String, nullable=False)
    evaluated_batch_id = Column(String, nullable=True)  # Specific batch or 'ALL'
    total_transactions_evaluated = Column(Integer, nullable=False, default=0)
    total_warnings_generated = Column(Integer, nullable=False, default=0)
    total_transactions_flagged = Column(Integer, nullable=False, default=0)
    execution_duration_sec = Column(Float, nullable=False, default=0.0)


class FraudScreeningWarning(Base):
    """Entity-level alerts generated for investigator review and review queue actions"""
    __tablename__ = "fraud_screening_warning"

    warning_id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String, nullable=True, unique=True, index=True) # e.g. ALT-0001
    detection_run_id = Column(String, ForeignKey("fraud_detection_run.detection_run_id"), nullable=False, index=True)
    rule_name = Column(String, nullable=False)         # 'VELOCITY_BURST', 'SHARED_DEVICE', 'LARGE_AMOUNT', 'CROSS_BANK_MOVEMENT'
    review_priority = Column(String, nullable=False)   # 'REVIEW', 'MEDIUM', 'HIGH'
    verdict = Column(String, nullable=False, default="POTENTIALLY SUSPICIOUS") # 'POTENTIALLY SUSPICIOUS'
    entity_type = Column(String, nullable=False)       # 'ACCOUNT', 'DEVICE', 'TRANSFER_CHAIN'
    entity_ref = Column(String, nullable=False)
    trigger_timestamp = Column(String, nullable=False)
    window_start = Column(String, nullable=False)
    window_end = Column(String, nullable=False)
    threshold_value = Column(Integer, nullable=False, default=0)
    observed_value = Column(Integer, nullable=False, default=0)
    evidence_summary = Column(String, nullable=False)

    # Operational queue & transaction context metadata
    originating_bank = Column(String, nullable=True)
    destination_bank = Column(String, nullable=True)
    sender_account_ref = Column(String, nullable=True)
    receiver_account_ref = Column(String, nullable=True)
    amount_paise = Column(Integer, nullable=True)
    payment_method = Column(String, nullable=True)
    transaction_status = Column(String, nullable=True)
    device_token = Column(String, nullable=True)
    rules_triggered = Column(String, nullable=True) # e.g. "Velocity, Shared Device"
    linked_route_summary = Column(String, nullable=True) # e.g. "Bank A -> Bank B -> Bank C"
    linked_transaction_ids = Column(String, nullable=True) # comma-separated IDs

    # Review actions persistence
    review_status = Column(String, nullable=False, default="NEEDS_REVIEW") # 'NEEDS_REVIEW', 'LEGITIMATE', 'SUSPICIOUS', 'ESCALATED', 'ACCOUNT_RESTRICTED'
    review_notes = Column(String, nullable=True)
    reviewed_at = Column(String, nullable=True)

    run = relationship("FraudDetectionRun")


class SimulatedRestrictedAccount(Base):
    """Tracks accounts placed in simulated restricted state by reviewers"""
    __tablename__ = "simulated_restricted_account"

    restriction_id = Column(Integer, primary_key=True, autoincrement=True)
    bank_code = Column(String, nullable=False)
    account_ref = Column(String, nullable=False)
    restricted_at = Column(String, nullable=False)
    reason = Column(String, nullable=False)
    alert_id = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("bank_code", "account_ref", name="uq_restricted_bank_account"),
    )


class FraudTransactionPrediction(Base):
    """
    Transaction-level prediction output: exactly one row per evaluated transaction per run.
    Enables rigorous Confusion Matrix computation without double-counting.
    """
    __tablename__ = "fraud_transaction_prediction"

    prediction_id = Column(Integer, primary_key=True, autoincrement=True)
    detection_run_id = Column(String, ForeignKey("fraud_detection_run.detection_run_id"), nullable=False, index=True)
    transaction_key = Column(Integer, ForeignKey("warehouse_fact_transaction.transaction_key"), nullable=False)
    source_bank_code = Column(String, nullable=False)
    source_transaction_id = Column(String, nullable=False)
    flagged_by_velocity = Column(Integer, nullable=False, default=0)
    flagged_by_device = Column(Integer, nullable=False, default=0)
    flagged_by_large_amount = Column(Integer, nullable=False, default=0)
    flagged_by_cross_bank_movement = Column(Integer, nullable=False, default=0)
    is_predicted_suspicious = Column(Integer, nullable=False, default=0)
    evaluated_at = Column(String, nullable=False)

    run = relationship("FraudDetectionRun")
    transaction = relationship("FactTransaction")

    __table_args__ = (
        UniqueConstraint("detection_run_id", "transaction_key", name="uq_run_txn_prediction"),
        Index("idx_pred_run_bank_source", "detection_run_id", "source_bank_code", "source_transaction_id"),
    )


# ============================================================================
# 5. SEPARATE EVALUATION GROUND TRUTH (LOGICAL ISOLATION)
# ============================================================================

class EvaluationGroundTruth(Base):
    """
    Ground-truth labels stored strictly for post-hoc academic evaluation.
    Operational screening modules never read or join this table.
    """
    __tablename__ = "evaluation_ground_truth"

    ground_truth_id = Column(Integer, primary_key=True, autoincrement=True)
    scenario_type = Column(String, nullable=False)
    source_bank_code = Column(String, nullable=False)
    source_transaction_id = Column(String, nullable=False)
    source_record_refs = Column(String, nullable=False)
    account_ref = Column(String, nullable=False)
    device_token = Column(String, nullable=True)
    is_suspicious = Column(Integer, nullable=False)  # 1 = Suspicious, 0 = Legitimate
    notes = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("source_bank_code", "source_transaction_id", name="uq_gt_bank_source_txn"),
    )

