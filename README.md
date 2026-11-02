# 🏦 BankFusion: Multi-Bank Data Warehouse & Fraud Analytics Platform

> **College Data Warehousing & Data Mining (DWM) Capstone Project**  
> *A Kimball-style analytical warehouse integrating heterogeneous banking architectures with grain reconciliation, OLAP multidimensional exploration, and explainable rule-based fraud screening.*

---

## 📑 Table of Contents
1. [Project Overview](#project-overview)
2. [Central Architecture & Workflow](#central-architecture--workflow)
3. [The Three Fictional Bank Systems](#the-three-fictional-bank-systems)
4. [Key Data Engineering Decisions](#key-data-engineering-decisions)
5. [Installation & Execution on Windows](#installation--execution-on-windows)
6. [Automated Testing Suite](#automated-testing-suite)
7. [Native Desktop User Interface (PySide6 / Qt 6)](#7-native-desktop-user-interface-pyside6--qt-6)
8. [Demonstrating Scenario BF-DEMO-001](#demonstrating-scenario-bf-demo-001)
9. [Project Folder Structure](#project-folder-structure)
10. [Academic Viva Defense & Worked Trace](#academic-viva-defense--worked-trace)

---

## 1. Project Overview

**BankFusion** demonstrates how heterogeneous transactional systems from three distinct commercial banks are extracted, cleansed, grain-reconciled, and integrated into a unified **Kimball Star Schema Data Warehouse**.

The core technical challenge is **heterogeneous source schema integration and grain reconciliation**:
* **MetroBank (Bank A):** Conventional core banking (1 row = 1 payment attempt).
* **QuickPay Bank (Bank B):** Digital wallet event stream (1 row = 1 payment event with retries).
* **TrustLine Bank (Bank C):** Pacioli double-entry accounting ledger (2 rows = 1 business transfer).

The common warehouse enables genuine **OLAP multidimensional analysis** (Slice, Dice, Roll-up, Drill-down) and powers two **deterministic, explainable fraud-screening rules** with logically separated post-hoc ground-truth evaluation.

---

## 2. Central Architecture & Workflow

```
Heterogeneous Banking Data (MetroBank, QuickPay Bank, TrustLine Bank)
        ↓
Synthetic Data Generation (Reproducible Seed, Integer Paise, ISO-8601 IST)
        ↓
Three Independent Source Schemas (Attempts, Event Logs, Double-Entry Ledgers)
        ↓
7-Stage ETL Pipeline (Extract -> Validate -> Pair -> Map -> Resolve -> Idempotent Load -> Reconcile)
        ↓
Unified Data Warehouse (Kimball Star Schema: FactTransaction + 7 Dimensions)
        ↓
OLAP Multidimensional Engine (Slice, Dice, Drill-down, Roll-up)
        ↓
Rule-Based Fraud Screening (Rolling 5-min Velocity & Rolling 24-hr Shared Device)
        ↓
Universal Predictions & Logically Separated Ground-Truth Evaluation (Precision, Recall, F1)
```

---

## 3. The Three Fictional Bank Systems

| Dimension | Bank A (MetroBank) | Bank B (QuickPay Bank) | Bank C (TrustLine Bank) |
|---|---|---|---|
| **System Type** | Conventional Retail Core | Digital Wallet & Payments | Double-Entry Accounting Ledger |
| **Operational Model** | Flat transaction attempts | Event stream with retries | Reciprocal debit-credit postings |
| **Source Grain** | 1 row = 1 payment attempt | 1 row = 1 payment event | 2 rows = 1 business transfer |
| **Primary Key** | `transaction_id` | `event_id` | `entry_id` |
| **Intent Binding** | Single attempt | `payment_request_ref` | `journal_id` |
| **Amount Field** | `amount_paise INTEGER` | `value_paise INTEGER` | `amount_paise INTEGER` |
| **Terminal Status** | `transaction_status` | `result_code` (mapped to enum) | `entry_status = 'POSTED'` |

---

## 4. Key Data Engineering Decisions

1. **Bank C Debit-Credit Pairing Rule:** Bank C entries are paired by `journal_id`. The pipeline verifies that exactly one `DEBIT` and one `CREDIT` leg exist, amounts match, accounts are reciprocal, and status is `POSTED`. It produces exactly one normalized fact row and retains dual lineage in `source_record_refs` (`"C-E-001,C-E-002"`).
2. **Dual-Equation Grain-Aware Reconciliation:**
   * **Equation 1 (Source Row Balance):** $\text{Total Extracted} = \text{Total Valid} + \text{Total Rejected}$
   * **Equation 2 (Normalized Load Balance):** $\text{Normalized Produced} = \text{Warehouse Inserted} + \text{Duplicate Skipped}$
     *(Where Bank C Valid Journals = Bank C Valid Entries / 2)*
3. **Integer Monetary Precision:** All generation, database storage, and aggregations use integer paise ($1\text{ INR} = 100\text{ paise}$), completely avoiding floating-point rounding errors.
4. **ETL Idempotency:** The fact table enforces `UNIQUE(bank_key, source_transaction_id)`. Re-running ETL produces zero duplicate rows and reports 100% duplicate skips.
5. **Universal Prediction Storage:** Every transaction in the warehouse receives a prediction row in `fraud_transaction_prediction` (`flagged_by_velocity`, `flagged_by_device`, `is_predicted_suspicious`), allowing mathematically valid confusion matrices ($TP$, $FP$, $TN$, $FN$).
6. **Logical Ground-Truth Separation:** Operational detection algorithms query strictly `FactTransaction`. Ground-truth labels in `evaluation_ground_truth` are accessed exclusively during post-detection evaluation.

---

## 5. Installation & Execution on Windows

### Prerequisites
* Python 3.10 to 3.13 installed.
* Windows PowerShell or Command Prompt.

### Step 1: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 2: Initialize Database and Generate Synthetic Data
```powershell
python data_generation/generate_ground_truth.py --seed 42
```
*Creates `bankfusion.db`, bootstraps schemas, and seeds 450+ multi-bank transactions.*

### Step 3: Run the 7-Stage ETL Pipeline
```powershell
python etl/run_etl_pipeline.py
```
*Validates, pairs Bank C journals, resolves surrogate keys, loads facts, and reconciles balances.*

### Step 4: Launch the Native Windows Desktop Application
```powershell
python desktop_main.py
```
*Opens the native PySide6 (Qt 6) desktop window directly on your desktop (no browser, no web server, no localhost URLs).*

### Optional: Build Standalone Windows Executable (.exe)
```powershell
python -m PyInstaller BankFusion.spec --noconfirm
```
*Compiles the application into `dist/BankFusion/BankFusion.exe` for double-click execution.*

---

## 6. Automated Testing Suite

BankFusion includes 34 comprehensive automated tests across all backend rules and desktop UI components:

```powershell
python -m pytest tests/
```

### Test Coverage Summary:
* `test_desktop_gui.py` (5 tests): Native PySide6 widgets, summary metric cards, alert card signals, transaction details dialog, and feed filtering.
* `test_detection_contract_and_ui.py` (6 tests): Desktop application architecture (MainWindow hosting exactly 2 pages), single-source-of-truth detection contract, distinct transaction flag counting without double-counting, failure contract reporting, review queue actions, and feed data consistency.
* `test_data_generation.py` (5 tests): Seed reproducibility, schema constraints, Bank B retry modeling, Bank C pairing, and ground-truth isolation.
* `test_warehouse_schema.py` (4 tests): Date dimension generation, composite account surrogate keys, device fallback, and cache preloading.
* `test_etl_pipeline.py` (3 tests): End-to-end execution, Bank C quarantine, dual-equation reconciliation, and duplicate prevention.
* `test_olap_analytics.py` (3 tests): Slicing by bank, dicing across dimensions, temporal roll-up, and bank comparison summaries.
* `test_fraud_detection.py` (2 tests): Velocity bursts, shared device abuse, universal prediction persistence, and evaluation metrics.
* `test_complete_demo.py` (2 tests): End-to-end BF-DEMO-001 execution and safe replay without duplicate conflicts.
* `test_large_amount_detection.py` (2 tests): Rule 3 baseline calculation (>= 3x median & >= Rs. 50,000) and new account fallback threshold (>= Rs. 1,00,000).
* `test_cross_bank_movement_detection.py` (2 tests): Rule 4 multi-hop chain detection (80%-100% retention within 600s) and negative window expiry cases.

---

## 7. Native Desktop User Interface (PySide6 / Qt 6)

The application provides a dark charcoal banking-security desktop interface with two primary pages:

1. **Page 1: Fraud Review Queue (`ui/fraud_review_page.py`):**
   * **Summary KPI Cards:** Real-time counts for *Awaiting Review*, *Escalated for Investigation*, and *Accounts Restricted* directly from SQLite.
   * **Triage Tabs:** Filter alerts across *Needs Review*, *All Alerts*, and *Resolved*.
   * **Alert Cards:** Displays Alert ID (`ALT-xxxx`), Priority badge (HIGH, MEDIUM, REVIEW), System verdict, Formatted amount in INR, IST timestamps, Origin/Destination banks and accounts, Payment method, Device token, and Triggered Detection Factors.
   * **Investigator Actions:** Dedicated buttons to *Mark as Legitimate*, *Confirm as Suspicious*, *Escalate*, and *Restrict Account* with immediate SQLite persistence.
   * **Deep Evidence Inspection:** Native `AlertDetailsDialog` displaying full context, linked routes, and audit trails.
   * **Empty State:** Shows friendly clear state with a one-click action to run fraud screening across warehouse transactions.

2. **Page 2: Transaction Feed (`ui/transaction_feed_page.py`):**
   * **Live Stream Monitoring:** Color-coded transaction table (Red for suspicious rows, Green for clean/cleared rows).
   * **Granular Multi-Dimensional Filters:** Filter by Risk Assessment (All / Suspicious / Clean), Source Bank, Detection Factor, Status, and search by Account Ref / Txn ID / Device Token.
   * **Non-Blocking Simulation Controls:** Start/Pause/Stop simulated transaction streaming and trigger single live transactions through background `QThread` workers.
   * **Transaction Detail Inspector:** Native `TransactionDetailsDialog` providing deep inspection of dimensional keys, integer paise vs INR amounts, terminal statuses, and exact 4-factor rule breakdown.

---

## 8. Demonstrating Scenario BF-DEMO-001

During a viva examination, use the dedicated demo:
1. Navigate to **Page 1: Overview & Demo**.
2. Click **"▶️ Run Scenario BF-DEMO-001"**.
3. The demo executes all 13 required steps using genuine backend production functions:
   * **Heterogeneous Ingestion:** Loads Bank A (4 attempts), Bank B (2 wallet events), Bank C (4 ledger entries).
   * **Pairing & Quarantine:** Pairs valid journal `C-J-DEMO-01` into 1 normalized transfer; quarantines malformed journal `C-J-DEMO-ERR` (mismatched amounts) to `etl_rejected_record`.
   * **Reconciliation:** Proves Equation 1 ($10 = 8 \text{ valid} + 2 \text{ rejected}$) and Equation 2 ($7 \text{ produced} = 7 \text{ inserted} + 0 \text{ skipped}$).
   * **Rule 1 Velocity Alert:** Flags account `A-ACC-DEMO-01` (4 attempts in 110s, including 2 failures).
   * **Rule 2 Shared Device Alert:** Flags token `SIM-DEVICE-DEMO-SHARED` (used across 3 distinct accounts in 3 banks).
   * **Evaluation:** Displays $TP = 7$, $\text{Precision} = 100\%$, $\text{Recall} = 100\%$.
4. Click **"🔄 Reset Demo Records"** to demonstrate that the demo can be replayed repeatedly without polluting production data.

---

## 9. Project Folder Structure

```
BankFusion/
│
├── main_app.py                            # Streamlit entrypoint routing to pages
├── requirements.txt                       # Streamlit, SQLAlchemy, Pandas, Plotly, pytest
├── README.md                              # Comprehensive project documentation
├── .env.example                           # Configuration defaults
│
├── pages/
│   ├── 1_Overview_and_Demo.py             # Landing page, architecture explanation, BF-DEMO-001 runner
│   ├── 2_Data_Warehouse.py                # Source inspection, ETL runner, DWH explorer, OLAP operations
│   └── 3_Fraud_Intelligence.py             # Velocity & device alerts, false positives, ML-free evaluation
│
├── data_generation/
│   ├── generate_customers_and_accounts.py # Creates master pool of customers, accounts, device tokens
│   ├── generate_bank_a_data.py            # Generates MetroBank payment attempts
│   ├── generate_bank_b_data.py            # Generates QuickPay events (including retry scenarios)
│   ├── generate_bank_c_ledger.py          # Generates TrustLine balanced debit/credit journals + edge cases
│   ├── generate_legitimate_scenarios.py   # Salaried, utility, merchant, family shared devices
│   ├── generate_suspicious_scenarios.py   # Velocity bursts, device spoofing, cross-bank structuring
│   └── generate_ground_truth.py           # Exports ground-truth labels exclusively for post-hoc evaluation
│
├── source_schemas/
│   ├── bank_a_schema.sql                  # Bank A table DDL
│   ├── bank_b_schema.sql                  # Bank B table DDL
│   └── bank_c_schema.sql                  # Bank C table DDL
│
├── database/
│   ├── database_connection.py             # SQLAlchemy engine & session management (SQLite)
│   ├── initialize_database.py             # Bootstraps tables and conformed dimension records
│   └── database_models.py                 # Declarative SQLAlchemy models
│
├── etl/
│   ├── extract_bank_data.py               # Read-only extractor for all 3 source tables
│   ├── validate_source_records.py         # Schema, range, nullability, and timestamp validators
│   ├── pair_bank_c_ledger_entries.py      # Double-entry ledger pairing, grain transformation & quarantine
│   ├── map_bank_fields.py                 # Source-to-canonical schema mapping
│   ├── resolve_dimension_keys.py          # Surrogate key resolution & unknown member fallback
│   ├── load_warehouse.py                  # Idempotent batch insertion into FactTransaction
│   ├── reconcile_etl_results.py           # Audit ledger computation and validation
│   └── run_etl_pipeline.py                # Master ETL orchestrator
│
├── warehouse/
│   ├── create_warehouse_tables.sql        # Full DWH schema DDL
│   └── warehouse_queries.py               # Fact/dimension analytical join builders
│
├── analytics/
│   ├── bank_comparison.py                 # Volume, attempt vs success, failure rate by bank
│   ├── transaction_trends.py              # Time-series analysis (hourly, daily, weekly)
│   ├── olap_operations.py                 # Dynamic Slice, Dice, Drill-down, and Roll-up engine
│   └── transaction_summaries.py           # Payment method and status distributions
│
├── fraud_detection/
│   ├── detect_transaction_velocity.py     # Rolling 5-minute window account velocity detector
│   ├── detect_shared_device_usage.py      # Rolling 24-hour window multi-account device detector
│   ├── save_detection_results.py          # Persists flagged warnings to fraud_screening_warning
│   └── evaluate_detection_results.py      # Compares alerts vs ground truth (Confusion Matrix, F1)
│
├── demo/
│   ├── demo_data.py                       # Predefined deterministic scenario BF-DEMO-001 records
│   └── run_demo_case.py                   # Complete programmatic pipeline runner for the live viva demo
│
├── config/
│   ├── bank_field_mapping.json            # Declarative field mappings for all 3 source banks
│   └── detection_thresholds.json          # Configurable window sizes and alert thresholds
│
├── tests/
│   ├── test_data_generation.py            # Verifies reproducible synthetic records
│   ├── test_warehouse_schema.py           # Verifies star schema joins & surrogate keys
│   ├── test_etl_pipeline.py               # Validates ETL reconciliation & duplicate prevention
│   ├── test_olap_analytics.py             # Validates Slice, Dice, and Roll-up operations
│   ├── test_fraud_detection.py            # Tests rolling window detection & predictions
│   └── test_complete_demo.py              # End-to-end integration test of BF-DEMO-001
│
└── documentation/
    ├── project_architecture.md            # Detailed system design & component diagrams
    ├── database_design.md                 # Star schema dictionary & ER diagram
    └── viva_preparation.md                # 25+ academic Q&As for practical exams
```

---

## 10. Academic Viva Defense & Worked Trace

For detailed answers to over 25 technical examination questions, refer to [`documentation/viva_preparation.md`](documentation/viva_preparation.md).

### Summary Trace of a Single Payment Attempt:
1. **Source Generation:** Bank A generates payment attempt `A-TXN-DEMO-001` with sender `A-ACC-DEMO-01`, receiver `B-ACC-DEMO-02`, amount 500,000 paise (₹5,000), and device `SIM-DEVICE-DEMO-SHARED`.
2. **ETL Extraction & Validation:** Extracted by `extract_bank_data.py`. Confirmed positive amount, valid ISO timestamp, and recognized UPI payment mode.
3. **Surrogate Key Resolution:** Converted to `bank_key = 1`, `date_key = 20261101`, `time_key = 1500`, `source_account_key`, and `device_key`.
4. **Idempotent Ingestion:** Loaded into `warehouse_fact_transaction` with audit batch `BATCH-DEMO-001`. Lineage preserved in `source_transaction_id` and `source_record_refs`.
5. **Reconciliation:** Accounted for in `etl_batch_log` across row balances and integer paise sums.
6. **Rule Evaluation:** Account makes 3 rapid subsequent attempts in 110s $\rightarrow$ triggers Rule 1. Device is used by 3 banks $\rightarrow$ triggers Rule 2. Elevated to **`HIGH_PRIORITY_REVIEW`**.
7. **Ground-Truth Evaluation:** Joined against `evaluation_ground_truth` and verified as **True Positive (TP)** in the confusion matrix.

