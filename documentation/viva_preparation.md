# BankFusion: Comprehensive Viva Preparation & Examination Guide

This document equips students with detailed, academic, and practical answers for questions commonly asked during a Data Warehousing and Data Mining (DWM) practical examination.

---

## 1. Data Warehousing & Architecture Concepts

### Q1: What is a Data Warehouse, and why do we need one in BankFusion?
**Answer:** A Data Warehouse is a subject-oriented, integrated, time-variant, and non-volatile collection of data designed to support management decision-making. In BankFusion, our three fictional banks operate on completely different database structures (flat payment attempts, event retry logs, and double-entry ledgers). Running analytical queries or fraud screening directly on operational databases would cause lock contention, performance degradation, and complex schema join issues. The warehouse consolidates and standardizes this data into a single analytical repository.

### Q2: What is a Star Schema, and why did you choose it over a Snowflake Schema?
**Answer:** A Star Schema is a dimensional model where a central fact table containing numerical measures is surrounded by de-normalized dimension tables containing descriptive attributes. We chose a Star Schema because:
1. It reduces complex SQL joins (single join from fact to each dimension).
2. It optimizes analytical read performance for OLAP slicing and dicing.
3. It provides an intuitive, easy-to-understand model for business investigators.

### Q3: What is the grain of your Fact Table?
**Answer:** Fact table grain defines what a single row in the fact table represents. In `FactTransaction`, the grain is **one normalized payment attempt** for Bank A and Bank B, or **one valid posted business transfer** represented by a balanced Bank C journal pair.

### Q4: What is a surrogate key, and why did you not use natural business keys?
**Answer:** A surrogate key is an artificial, system-generated integer (e.g., `account_key`, `date_key`) that uniquely identifies a dimension member. We avoided using natural business keys (like source account strings) in the fact table because:
1. Natural keys are variable-length strings, which degrade join and indexing performance.
2. Natural keys can change in operational source systems.
3. Natural keys from different banks can collide (e.g., Bank A and Bank B could both assign an account `ACC-001`). Surrogate keys insulate the analytical warehouse from external changes.

### Q5: How do you identify an account uniquely across different banks?
**Answer:** We enforce a **composite natural identity**: `(bank_key, source_account_ref)`. Never assume accounts are the same person because they share a number or name. In our database, `DimAccount` enforces `UNIQUE(bank_key, source_account_ref)`.

### Q6: What are Conformed Dimensions?
**Answer:** Conformed dimensions are dimension tables that have consistent data across the entire warehouse, allowing facts to be shared and compared across different business processes or sources. In BankFusion, `DimBank`, `DimDate`, `DimTime`, `DimPaymentMethod`, and `DimTransactionStatus` are conformed dimensions used universally across all three banks.

---

## 2. ETL & Grain Reconciliation Concepts

### Q7: What are the stages of your ETL pipeline?
**Answer:** Our pipeline executes 7 distinct stages:
1. **Extract:** Read-only extraction from raw source tables.
2. **Validate:** Schema, range, nullability, and timestamp checking.
3. **Bank C Pairing:** Grouping debit-credit legs and validating balance.
4. **Transform & Map:** Mapping heterogeneous source fields to canonical enums.
5. **Resolve Keys:** Looking up surrogate keys in conformed dimensions.
6. **Load:** Idempotently inserting fact rows into `FactTransaction`.
7. **Reconcile:** Computing dual-equation row balances and monetary decompositions.

### Q8: What is the Bank C grain mismatch, and how does your pipeline solve it?
**Answer:** In Bank A and B, 1 source row represents 1 transaction. In Bank C (TrustLine Bank), double-entry bookkeeping requires two rows (one DEBIT leg and one CREDIT leg) for every transfer. If naively loaded, Bank C would inflate transaction counts by 2x. Our pipeline groups Bank C entries by `journal_id`, confirms that exactly one debit and one credit leg exist, checks that amounts match, verifies reciprocal counterparty references, and outputs **exactly one fact transaction** per valid journal.

### Q9: What happens to invalid or unbalanced Bank C journals?
**Answer:** Any journal where legs are missing, amounts differ, or status is unposted is rejected during pairing and written to `etl_rejected_record` with the explicit reason (e.g. `MISMATCHED_AMOUNTS`, `INVALID_LEG_COUNT`). Quarantined records never enter `FactTransaction`.

### Q10: What is ETL Idempotency, and how is it implemented?
**Answer:** An idempotent ETL pipeline can be executed multiple times on the same input data without producing duplicate records or changing the analytical state beyond the initial run. In BankFusion, `FactTransaction` enforces a composite unique constraint: `UNIQUE(bank_key, source_transaction_id)`. During loading, the pipeline detects existing keys and skips them, recording the skipped rows and skipped monetary amounts in `etl_batch_log`.

### Q11: Explain your Dual-Equation Reconciliation logic.
**Answer:** Naive reconciliation fails when source systems have different grains. We use two equations:
* **Equation 1 (Source Row Balance):** 
  $$\text{Total Extracted} = \text{Total Valid Source Rows} + \text{Total Rejected Source Rows}$$
* **Equation 2 (Normalized Load Balance):**
  $$\text{Normalized Produced} = \text{Warehouse Rows Inserted} + \text{Duplicate Rows Skipped}$$
  Where $\text{Normalized Produced} = N_{\text{Valid\_Bank\_A}} + N_{\text{Valid\_Bank\_B}} + \frac{1}{2} N_{\text{Valid\_Bank\_C\_entries}}$.

### Q12: Why do you store monetary values in integer paise instead of floating-point numbers?
**Answer:** Floating-point representations (`FLOAT`/`REAL`) suffer from IEEE-754 binary rounding errors (e.g., $0.1 + 0.2 = 0.30000000000000004$). In financial systems, small rounding discrepancies cause reconciliation assertions to fail. We store all monetary values as integer paise ($1\text{ INR} = 100\text{ paise}$) and convert to Rupees only when displaying in the user interface.

---

## 3. OLAP Concepts

### Q13: What is the difference between OLTP and OLAP?
**Answer:** 
* **OLTP (Online Transaction Processing):** Focuses on fast, concurrent day-to-day transaction execution (inserts, updates). Highly normalized (3NF) to eliminate redundancy.
* **OLAP (Online Analytical Processing):** Focuses on complex read-heavy analytical queries and multidimensional aggregations over historical data. Uses de-normalized star or snowflake schemas.

### Q14: Explain the four core OLAP operations in BankFusion.
**Answer:**
1. **Slice:** Fastens one dimension to a single coordinate value (e.g. filter where `bank_code = 'BANK_A'`).
2. **Dice:** Isolates a sub-cube by filtering across multiple dimensions simultaneously (e.g. `Bank IN ('BANK_A', 'BANK_B')` AND `Method = 'UPI'` AND `Status = 'SUCCESS'`).
3. **Roll-up:** Climbs up the dimensional hierarchy to aggregate detailed data into coarser summaries (e.g. Hourly $\rightarrow$ Daily $\rightarrow$ Monthly).
4. **Drill-down:** Navigates down the dimensional hierarchy from summary figures into finer details (e.g. Annual volume down to monthly breakdowns).

---

## 4. Data Mining & Fraud Analytics

### Q15: Why did you use deterministic rules instead of Machine Learning models?
**Answer:** 
1. **Explainability:** Regulated financial systems require transparent, explainable alerts. Investigators must know the exact boundary violated (e.g. "4 attempts in 110s"), not an opaque probability score from a black-box model.
2. **Academic Focus:** The primary objective of BankFusion is data integration, grain alignment, and ETL reconciliation. Simple deterministic rules allow us to isolate and evaluate data flow without the compounding complexities of model hyperparameter tuning.

### Q16: How does Rule 1 (Transaction Velocity) work?
**Answer:** Rule 1 detects automated rapid payment attempts. It slides an inclusive 300-second (5-minute) rolling window across each account's payment attempts:
$$\text{Attempts in window} = \{ \text{txn} \mid t_1 \le \text{txn.epoch\_timestamp} \le t_1 + 300 \}$$
If $\ge 4$ attempts occur in that window, an alert is raised. For Banks A and B, it counts all attempts including failures.

### Q17: How does Rule 2 (Shared-Device Usage) work?
**Answer:** Rule 2 detects hardware multiplexing or emulator farms. It slides an inclusive 24-hour (86,400s) rolling window across transactions associated with each physical device token. If $\ge 3$ distinct sending accounts use the same device token within 24 hours, an alert is generated. The surrogate `UNKNOWN_DEVICE` is strictly excluded.

### Q18: What is the difference between an entity warning and a transaction prediction?
**Answer:** 
* **Entity Warning:** High-level summary for human investigators (e.g. "Account A-ACC-0040 initiated 5 attempts in 175s").
* **Transaction Prediction:** Low-level boolean prediction recorded for **every single transaction** in the warehouse (`flagged_by_velocity`, `flagged_by_device`, `is_predicted_suspicious`). Universal predictions are required to compute True Negatives ($TN$) and False Positives ($FP$) in the confusion matrix.

### Q19: How is ground truth logically separated from operational screening?
**Answer:** Operational screening functions accept only `FactTransaction` DataFrames and have zero code imports or SQL queries pointing to `evaluation_ground_truth`. Ground truth is queried strictly post-detection in the evaluation module to compute Precision, Recall, and F1.

### Q20: Why are your precision and recall scores high on this dataset?
**Answer:** The dataset is programmatically synthesized with controlled target patterns designed to test our rule boundaries. High precision and recall validate that our algorithmic implementation of sliding windows and thresholds is correct. However, in real-world banking, adversaries adapt to thresholds, resulting in lower recall and higher false positives.

---

## 5. End-to-End Payment Trace (Worked Example)

### Q21: Walk through the complete lifecycle of a single payment from source table to screening result.

**Example: Bank A Payment Attempt `A-TXN-DEMO-001`**

1. **Source Generation:**
   * Generated as a raw payment attempt: `transaction_id = 'A-TXN-DEMO-001'`, `sender = 'A-ACC-DEMO-01'`, `receiver = 'B-ACC-DEMO-02'`, `amount_paise = 500000` (₹5,000), `device = 'SIM-DEVICE-DEMO-SHARED'`, `timestamp = '2026-11-01T15:00:10+05:30'`.
   * Stored in `bank_a_transactions`.

2. **ETL Extraction & Validation:**
   * Extracted by `extract_bank_data.py`.
   * Validated by `validate_source_records.py`: checks that amount > 0, timestamp is valid ISO-8601, status is recognized. Passes validation.

3. **ETL Mapping & Dimension Resolution:**
   * Mapped to canonical format: `payment_mode` 'UPI' $\rightarrow$ conformed enum 'UPI', status 'SUCCESS' $\rightarrow$ conformed status 'SUCCESS'.
   * Surrogate keys resolved:
     * `bank_key` $\rightarrow$ 1 (`BANK_A`)
     * `date_key` $\rightarrow$ 20261101
     * `time_key` $\rightarrow$ 1500
     * `source_account_key` $\rightarrow$ resolved for `(BANK_A, A-ACC-DEMO-01)`
     * `destination_account_key` $\rightarrow$ resolved for `(BANK_B, B-ACC-DEMO-02)`
     * `device_key` $\rightarrow$ resolved for `'SIM-DEVICE-DEMO-SHARED'`

4. **Warehouse Loading & Reconciliation:**
   * Loaded into `warehouse_fact_transaction` with surrogate keys.
   * `source_transaction_id = 'A-TXN-DEMO-001'`, `source_record_refs = 'A-TXN-DEMO-001'`.
   * Reconciliation verifies that the extracted row is accounted for in `etl_batch_log`.

5. **Fraud Screening (Rule 1 & Rule 2):**
   * Account `A-ACC-DEMO-01` makes 3 subsequent attempts within 110 seconds.
   * `detect_transaction_velocity.py` evaluates the 300s rolling window, finds 4 attempts, and flags `A-TXN-DEMO-001`.
   * `detect_shared_device_usage.py` evaluates `SIM-DEVICE-DEMO-SHARED`, finds 3 distinct accounts using it within 24 hours, and flags `A-TXN-DEMO-001`.
   * Dual trigger elevated to **`HIGH_PRIORITY_REVIEW`**.

6. **Evaluation Join:**
   * `evaluate_detection_results.py` joins the prediction (`is_predicted_suspicious = 1`) with `evaluation_ground_truth` (`is_suspicious = 1`).
   * Counted as **True Positive (TP)** in the confusion matrix.

