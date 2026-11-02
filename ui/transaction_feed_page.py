"""
BankFusion Desktop Page 2: Transaction Feed
===========================================
High-performance live multi-bank transaction surveillance feed.
Optimized with:
1. Asynchronous database & pandas loading via FeedLoaderWorker (QThread).
2. Fixed / Interactive column sizing (ResizeToContents completely eliminated).
3. In-memory caching with dirty-flag invalidation to prevent duplicate queries on tab switch.
4. Bulk table update suppression (setUpdatesEnabled(False) + blockSignals(True)).
5. Incremental pagination / "Load More" rendering (100 rows initial display).
6. Non-blocking UI with background progress loading indicators.
"""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QComboBox, QSpinBox, QFrame, QMessageBox, QAbstractItemView,
    QProgressBar
)
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QColor, QBrush

from database.database_connection import SessionLocal
from warehouse.warehouse_queries import get_transaction_feed_dataframe
from ui.transaction_details_dialog import TransactionDetailsDialog
from ui.theme import (
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED,
    COLOR_BORDER, COLOR_PANEL_BG, COLOR_RED, COLOR_GREEN, COLOR_BLUE
)
from workers.transaction_generation_worker import TransactionGenerationWorker
from workers.detection_worker import DetectionWorker
from workers.feed_loader_worker import FeedLoaderWorker


class TransactionFeedPage(QWidget):
    """Real-time transaction feed monitoring view with controls, pagination, and filters."""

    # Default initial display limit
    DEFAULT_DISPLAY_LIMIT = 100
    LOAD_MORE_INCREMENT = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cached_df = None
        self.current_filtered_df = None
        self.is_dirty = True
        self.display_limit = self.DEFAULT_DISPLAY_LIMIT

        # Background Workers
        self.feed_loader_worker: Optional[FeedLoaderWorker] = None
        self.generation_worker: Optional[TransactionGenerationWorker] = None
        self.detection_worker: Optional[DetectionWorker] = None

        # Simulation Timer
        self.sim_timer = QTimer(self)
        self.sim_timer.timeout.connect(self._on_sim_timer_tick)
        self.sim_interval_sec = 2

        self._build_ui()
        self.load_feed_data(force=True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        # 1. Header and Simulation Controls
        hdr_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title_lbl = QLabel("💳 Transaction Feed")
        title_lbl.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {COLOR_TEXT_PRIMARY};")
        sub_lbl = QLabel("Live Multi-Bank Surveillance Stream with Deterministic 4-Factor Risk Assessment")
        sub_lbl.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_MUTED};")

        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_lbl)
        hdr_layout.addLayout(title_box)
        hdr_layout.addStretch()

        # Controls Toolbar
        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.setToolTip("Reload warehouse transactions from database")
        self.btn_refresh.clicked.connect(lambda: self.load_feed_data(force=True))

        self.btn_start = QPushButton("▶️ Start Simulation")
        self.btn_start.setObjectName("successButton")
        self.btn_start.clicked.connect(self.start_simulation)

        self.btn_pause = QPushButton("⏸️ Pause")
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self.pause_simulation)

        self.btn_stop = QPushButton("⏹️ Stop")
        self.btn_stop.setObjectName("dangerButton")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_simulation)

        self.btn_gen_now = QPushButton("➕ Ingest Txn Now")
        self.btn_gen_now.setObjectName("primaryButton")
        self.btn_gen_now.clicked.connect(self.generate_single_transaction)

        self.btn_rescreen = QPushButton("⚡ Re-Screen")
        self.btn_rescreen.clicked.connect(self.rescreen_warehouse)

        interval_lbl = QLabel("Interval (s):")
        interval_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 30)
        self.interval_spin.setValue(self.sim_interval_sec)
        self.interval_spin.valueChanged.connect(self._on_interval_changed)

        hdr_layout.addWidget(self.btn_refresh)
        hdr_layout.addWidget(self.btn_start)
        hdr_layout.addWidget(self.btn_pause)
        hdr_layout.addWidget(self.btn_stop)
        hdr_layout.addWidget(self.btn_gen_now)
        hdr_layout.addWidget(self.btn_rescreen)
        hdr_layout.addWidget(interval_lbl)
        hdr_layout.addWidget(self.interval_spin)

        layout.addLayout(hdr_layout)

        # 2. KPI Metrics Bar
        self.kpi_frame = QFrame()
        self.kpi_frame.setStyleSheet(f"""
            background-color: {COLOR_PANEL_BG};
            border: 1px solid {COLOR_BORDER};
            border-radius: 8px;
            padding: 8px 16px;
        """)
        kpi_layout = QHBoxLayout(self.kpi_frame)
        kpi_layout.setContentsMargins(10, 4, 10, 4)

        self.lbl_total = self._create_kpi_label("MONITORED TRANSACTIONS", "0", COLOR_TEXT_PRIMARY)
        self.lbl_susp = self._create_kpi_label("FLAGGED SUSPICIOUS", "0", COLOR_RED)
        self.lbl_clean = self._create_kpi_label("CLEARED (NORMAL)", "0", COLOR_GREEN)
        self.lbl_ratio = self._create_kpi_label("FRAUD DETECTION RATIO", "0.0%", "#f59e0b")

        kpi_layout.addWidget(self.lbl_total)
        kpi_layout.addWidget(self.lbl_susp)
        kpi_layout.addWidget(self.lbl_clean)
        kpi_layout.addWidget(self.lbl_ratio)

        layout.addWidget(self.kpi_frame)

        # 3. Filters Toolbar
        filter_panel = QFrame()
        filter_panel.setObjectName("filterPanel")
        filter_layout = QHBoxLayout(filter_panel)
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setSpacing(12)

        self.combo_status = QComboBox()
        self.combo_status.addItems(["All Assessments", "Suspected Fraud Only", "No Alert Only"])
        self.combo_status.currentIndexChanged.connect(self._on_filter_changed)

        self.combo_bank = QComboBox()
        self.combo_bank.addItems(["All Banks", "METROBANK", "QUICKPAY", "TRUSTLINE"])
        self.combo_bank.currentIndexChanged.connect(self._on_filter_changed)

        self.combo_factor = QComboBox()
        self.combo_factor.addItems([
            "All Detection Factors",
            "Velocity Burst",
            "Shared Device",
            "Large Amount",
            "Cross-Bank Movement"
        ])
        self.combo_factor.currentIndexChanged.connect(self._on_filter_changed)

        self.combo_txn_status = QComboBox()
        self.combo_txn_status.addItems(["All Statuses", "SUCCESS", "FAILED", "PENDING"])
        self.combo_txn_status.currentIndexChanged.connect(self._on_filter_changed)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search Account Ref, Txn ID, or Device Token...")
        self.search_edit.textChanged.connect(self._on_filter_changed)

        filter_layout.addWidget(QLabel("Filter:"))
        filter_layout.addWidget(self.combo_status)
        filter_layout.addWidget(self.combo_bank)
        filter_layout.addWidget(self.combo_factor)
        filter_layout.addWidget(self.combo_txn_status)
        filter_layout.addWidget(self.search_edit)

        layout.addWidget(filter_panel)

        # 4. Loading Status Indicator Bar (Non-blocking QProgressBar)
        self.loading_frame = QFrame()
        self.loading_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
            }}
        """)
        loading_layout = QHBoxLayout(self.loading_frame)
        loading_layout.setContentsMargins(10, 4, 10, 4)
        loading_layout.setSpacing(12)

        self.loading_lbl = QLabel("🔄 Loading transactions & screening factors from warehouse in background...")
        self.loading_lbl.setStyleSheet(f"color: {COLOR_BLUE}; font-size: 12px; font-weight: 600; background: transparent;")

        self.loading_progress = QProgressBar()
        self.loading_progress.setRange(0, 0)  # Indeterminate animated bar
        self.loading_progress.setFixedHeight(4)
        self.loading_progress.setTextVisible(False)
        self.loading_progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: #0f172a;
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {COLOR_BLUE};
                border-radius: 2px;
            }}
        """)

        loading_layout.addWidget(self.loading_lbl)
        loading_layout.addWidget(self.loading_progress, 1)
        self.loading_frame.setVisible(False)
        layout.addWidget(self.loading_frame)

        # 5. Table Widget for Transaction Feed
        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels([
            "Timestamp", "Txn ID", "Origin Bank", "Sender Account",
            "Dest Bank", "Receiver Account", "Amount (₹)", "Status",
            "Method", "Risk Result", "Triggered Rules"
        ])

        # PERFORMANCE CRITICAL: Replace ResizeToContents with Interactive & Explicit Column Widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        col_widths = [
            (0, 140),  # Timestamp
            (1, 105),  # Txn ID
            (2, 95),   # Origin Bank
            (3, 130),  # Sender Account
            (4, 95),   # Dest Bank
            (5, 130),  # Receiver Account
            (6, 105),  # Amount (₹)
            (7, 85),   # Status
            (8, 80),   # Method
            (9, 120),  # Risk Result
            (10, 240), # Triggered Rules
        ]
        for col_idx, width in col_widths:
            self.table.setColumnWidth(col_idx, width)
        header.setSectionResizeMode(10, QHeaderView.Stretch)

        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_table_row_double_click)

        layout.addWidget(self.table, 1)

        # 6. Pagination / Load More Controls Footer
        pagination_frame = QFrame()
        pagination_frame.setStyleSheet(f"""
            background-color: {COLOR_PANEL_BG};
            border: 1px solid {COLOR_BORDER};
            border-radius: 6px;
            padding: 4px 12px;
        """)
        pagination_layout = QHBoxLayout(pagination_frame)
        pagination_layout.setContentsMargins(10, 4, 10, 4)
        pagination_layout.setSpacing(12)

        self.lbl_pagination = QLabel("Showing 0 of 0 transactions")
        self.lbl_pagination.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; font-weight: 500;")

        self.btn_load_more = QPushButton("⬇️ Load More (+100)")
        self.btn_load_more.setToolTip("Render next 100 transactions into the table")
        self.btn_load_more.clicked.connect(self._on_load_more_clicked)

        self.btn_show_all = QPushButton("⏬ Show All")
        self.btn_show_all.setToolTip("Render all matching transactions into the table")
        self.btn_show_all.clicked.connect(self._on_show_all_clicked)

        pagination_layout.addWidget(self.lbl_pagination)
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.btn_load_more)
        pagination_layout.addWidget(self.btn_show_all)

        layout.addWidget(pagination_frame)

    def _create_kpi_label(self, title: str, init_val: str, color: str) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(2)

        t = QLabel(title)
        t.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {COLOR_TEXT_MUTED}; background: transparent;")
        v = QLabel(init_val)
        v.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {color}; background: transparent;")

        l.addWidget(t)
        l.addWidget(v)
        w.value_label = v
        return w

    def _on_interval_changed(self, val: int):
        self.sim_interval_sec = val
        if self.sim_timer.isActive():
            self.sim_timer.setInterval(self.sim_interval_sec * 1000)

    # ------------------------------------------------------------------
    # Asynchronous Data Loading
    # ------------------------------------------------------------------
    def load_feed_data(self, force: bool = False):
        """
        Loads transaction feed from data warehouse in background QThread.
        Guards against duplicate loads if data is already cached and not marked dirty.
        """
        # If cache is valid and not forced, avoid duplicate database hits
        if not force and not self.is_dirty and self.cached_df is not None:
            return

        # If a loader is already running in background, let it finish
        if self.feed_loader_worker and self.feed_loader_worker.isRunning():
            return

        self.loading_frame.setVisible(True)
        self.btn_refresh.setEnabled(False)

        self.feed_loader_worker = FeedLoaderWorker(parent=self)
        self.feed_loader_worker.feed_loaded.connect(self._on_feed_loaded)
        self.feed_loader_worker.feed_failed.connect(self._on_feed_failed)
        self.feed_loader_worker.start()

    @Slot(object)
    def _on_feed_loaded(self, df):
        """Main-thread slot executed when background query finishes."""
        self.cached_df = df
        self.is_dirty = False
        self.loading_frame.setVisible(False)
        self.btn_refresh.setEnabled(True)

        self.apply_filters()

    @Slot(str)
    def _on_feed_failed(self, error_message: str):
        """Main-thread slot executed if background query fails."""
        self.loading_frame.setVisible(False)
        self.btn_refresh.setEnabled(True)
        QMessageBox.critical(
            self,
            "Warehouse Load Error",
            f"An error occurred while loading transactions:\n{error_message}"
        )

    def mark_dirty(self):
        """Marks cached data as dirty so subsequent views refresh fresh data."""
        self.is_dirty = True

    def wait_for_load(self, timeout_ms: int = 5000):
        """Blocks up to timeout_ms waiting for background loader to complete (used in tests)."""
        if self.feed_loader_worker and self.feed_loader_worker.isRunning():
            self.feed_loader_worker.wait(timeout_ms)

    # ------------------------------------------------------------------
    # Filtering & KPI Metrics
    # ------------------------------------------------------------------
    def _on_filter_changed(self):
        """Resets display limit to default 100 on new search/filter and applies filters."""
        self.display_limit = self.DEFAULT_DISPLAY_LIMIT
        self.apply_filters()

    def apply_filters(self):
        """Applies UI filters to cached dataframe and updates table rows."""
        if self.cached_df is None or self.cached_df.empty:
            self.table.setRowCount(0)
            self.lbl_pagination.setText("Showing 0 of 0 transactions")
            self.btn_load_more.setEnabled(False)
            self.btn_show_all.setEnabled(False)
            self.lbl_total.value_label.setText("0")
            self.lbl_susp.value_label.setText("0")
            self.lbl_clean.value_label.setText("0")
            self.lbl_ratio.value_label.setText("0.0%")
            return

        df = self.cached_df.copy()

        # 1. Assessment Filter
        stat_choice = self.combo_status.currentText()
        if stat_choice == "Suspected Fraud Only":
            df = df[df["is_predicted_suspicious"] == 1]
        elif stat_choice == "No Alert Only":
            df = df[df["is_predicted_suspicious"] == 0]

        # 2. Bank Filter
        bank_choice = self.combo_bank.currentText()
        if bank_choice != "All Banks":
            df = df[df["bank_code"] == bank_choice]

        # 3. Detection Factor
        factor_choice = self.combo_factor.currentText()
        if factor_choice == "Velocity Burst":
            df = df[df["flagged_by_velocity"] == 1]
        elif factor_choice == "Shared Device":
            df = df[df["flagged_by_device"] == 1]
        elif factor_choice == "Large Amount":
            df = df[df["flagged_by_large_amount"] == 1]
        elif factor_choice == "Cross-Bank Movement":
            df = df[df["flagged_by_cross_bank_movement"] == 1]

        # 4. Status Filter
        status_choice = self.combo_txn_status.currentText()
        if status_choice != "All Statuses":
            df = df[df["transaction_status"] == status_choice]

        # 5. Search
        search = self.search_edit.text().strip()
        if search:
            mask = (
                df["source_transaction_id"].astype(str).str.contains(search, case=False, na=False) |
                df["source_account_ref"].astype(str).str.contains(search, case=False, na=False) |
                df["destination_account_ref"].astype(str).str.contains(search, case=False, na=False) |
                df["device_token"].astype(str).str.contains(search, case=False, na=False)
            )
            df = df[mask]

        # Update KPI metrics based on full warehouse dataset
        total = len(self.cached_df)
        susp = int((self.cached_df["is_predicted_suspicious"] == 1).sum())
        clean = total - susp
        ratio = (susp / total * 100.0) if total > 0 else 0.0

        self.lbl_total.value_label.setText(f"{total:,}")
        self.lbl_susp.value_label.setText(f"{susp:,}")
        self.lbl_clean.value_label.setText(f"{clean:,}")
        self.lbl_ratio.value_label.setText(f"{ratio:.1f}%")

        # Save filtered dataset
        self.current_filtered_df = df.reset_index(drop=True)
        self._populate_table(self.current_filtered_df)

    # ------------------------------------------------------------------
    # Bulk Table Population with Update Suppression & Pagination
    # ------------------------------------------------------------------
    def _populate_table(self, df):
        """
        Populates table rows safely disabling UI updates and signal emission.
        Renders up to self.display_limit rows for high responsiveness.
        """
        total_matching = len(df)
        limit = min(self.display_limit, total_matching)
        sliced_df = df.head(limit)

        # Update pagination indicators
        self.lbl_pagination.setText(
            f"Showing {limit:,} of {total_matching:,} matching transactions (latest first)"
        )
        has_more = limit < total_matching
        self.btn_load_more.setEnabled(has_more)
        self.btn_show_all.setEnabled(has_more)

        # Suppress widget paint events & signals during bulk population
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(limit)

            red_bg = QBrush(QColor("#2d1115"))
            red_fg = QBrush(QColor("#fca5a5"))
            green_bg = QBrush(QColor("#081f18"))
            green_fg = QBrush(QColor("#6ee7b7"))
            cell_fg = QBrush(QColor("#e2e8f0"))

            for row_idx, row in sliced_df.iterrows():
                is_susp = row["is_predicted_suspicious"] == 1
                bg_brush = red_bg if is_susp else green_bg
                fg_brush = red_fg if is_susp else green_fg

                amt_inr = f"₹{row['amount_inr']:,.2f}"
                res_str = "🚨 SUSPICIOUS" if is_susp else "✅ CLEAN"

                items = [
                    row["transaction_timestamp"],
                    str(row["source_transaction_id"]),
                    row["bank_code"],
                    row["source_account_ref"],
                    row["destination_bank"],
                    row["destination_account_ref"],
                    amt_inr,
                    row["transaction_status"],
                    row.get("payment_method", "N/A"),
                    res_str,
                    row["detection_factors"],
                ]

                for col_idx, text in enumerate(items):
                    item = QTableWidgetItem(str(text))
                    item.setBackground(bg_brush)
                    if col_idx == 9:  # Result column
                        item.setForeground(fg_brush)
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                    else:
                        item.setForeground(cell_fg)
                    self.table.setItem(row_idx, col_idx, item)
        finally:
            # Safely re-enable table updates & signals
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)

    def _on_load_more_clicked(self):
        """Loads additional rows into the table."""
        self.display_limit += self.LOAD_MORE_INCREMENT
        if self.current_filtered_df is not None:
            self._populate_table(self.current_filtered_df)

    def _on_show_all_clicked(self):
        """Loads all matching rows into the table."""
        if self.current_filtered_df is not None:
            self.display_limit = len(self.current_filtered_df)
            self._populate_table(self.current_filtered_df)

    def _on_table_row_double_click(self, index):
        row_idx = index.row()
        if self.current_filtered_df is not None and row_idx < len(self.current_filtered_df):
            row_dict = self.current_filtered_df.iloc[row_idx].to_dict()
            dialog = TransactionDetailsDialog(row_dict, self)
            dialog.exec()

    # ------------------------------------------------------------------
    # Simulation & Generation Controls
    # ------------------------------------------------------------------
    def start_simulation(self):
        self.sim_timer.start(self.sim_interval_sec * 1000)
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)

    def pause_simulation(self):
        self.sim_timer.stop()
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)

    def stop_simulation(self):
        self.sim_timer.stop()
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)

    def _on_sim_timer_tick(self):
        self.generate_single_transaction()

    def generate_single_transaction(self):
        if self.generation_worker and self.generation_worker.isRunning():
            return

        self.generation_worker = TransactionGenerationWorker(self)
        self.generation_worker.generation_completed.connect(self._on_tx_generated)
        self.generation_worker.generation_failed.connect(self._on_tx_gen_failed)
        self.generation_worker.start()

    @Slot(str, dict)
    def _on_tx_generated(self, txn_id: str, res: dict):
        self.mark_dirty()
        self.load_feed_data(force=True)

    @Slot(str)
    def _on_tx_gen_failed(self, err: str):
        QMessageBox.warning(self, "Generation Error", f"Failed to ingest transaction:\n{err}")

    def rescreen_warehouse(self):
        if self.detection_worker and self.detection_worker.isRunning():
            return

        self.btn_rescreen.setEnabled(False)
        self.detection_worker = DetectionWorker(self)
        self.detection_worker.detection_completed.connect(self._on_rescreen_done)
        self.detection_worker.detection_failed.connect(self._on_rescreen_failed)
        self.detection_worker.start()

    @Slot(dict)
    def _on_rescreen_done(self, res: dict):
        self.btn_rescreen.setEnabled(True)
        self.mark_dirty()
        self.load_feed_data(force=True)
        QMessageBox.information(
            self,
            "Re-Screen Complete",
            f"Evaluated {res['total_transactions_evaluated']:,} transactions.\n"
            f"Flagged {res['total_flagged_transactions']:,} suspicious across {res['total_warnings_generated']:,} alerts."
        )

    @Slot(str)
    def _on_rescreen_failed(self, err: str):
        self.btn_rescreen.setEnabled(True)
        QMessageBox.critical(self, "Screening Error", err)

    def stop_all_workers(self):
        """Cleanly halts simulation timers and waits for background QThreads."""
        self.stop_simulation()
        if self.feed_loader_worker and self.feed_loader_worker.isRunning():
            self.feed_loader_worker.wait(2000)
        if self.generation_worker and self.generation_worker.isRunning():
            self.generation_worker.wait(2000)
        if self.detection_worker and self.detection_worker.isRunning():
            self.detection_worker.wait(2000)

    def closeEvent(self, event):
        self.stop_all_workers()
        super().closeEvent(event)
