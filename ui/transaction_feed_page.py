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

import logging
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QComboBox, QSpinBox, QFrame, QMessageBox, QAbstractItemView,
    QProgressBar
)
from PySide6.QtCore import Qt, QTimer, Slot, Signal
from PySide6.QtGui import QColor, QBrush

logger = logging.getLogger("BankFusion.TransactionFeed")

from database.database_connection import SessionLocal
from warehouse.warehouse_queries import get_transaction_feed_dataframe
from ui.transaction_details_dialog import TransactionDetailsDialog
from ui.theme import (
    COLOR_BG, COLOR_CARD_BG, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED,
    COLOR_BORDER, COLOR_BORDER_DARK, COLOR_PANEL_BG, COLOR_ACCENT,
    COLOR_CLEAR, COLOR_CLEAR_BG, COLOR_REVIEW, COLOR_REVIEW_BG,
    COLOR_BLOCKED, COLOR_BLOCKED_BG, COLOR_RELEASED, COLOR_RELEASED_BG,
    COLOR_RED, COLOR_GREEN, COLOR_BLUE, COLOR_AMBER
)
from workers.transaction_generation_worker import TransactionGenerationWorker
from workers.detection_worker import DetectionWorker
from workers.feed_loader_worker import FeedLoaderWorker


class TransactionFeedPage(QWidget):
    """Real-time transaction feed monitoring view with controls, pagination, and filters."""

    screening_completed = Signal(dict)

    # Default initial display limit
    DEFAULT_DISPLAY_LIMIT = 100
    LOAD_MORE_INCREMENT = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cached_df = None
        self.current_filtered_df = None
        self.is_dirty = True
        self.display_limit = self.DEFAULT_DISPLAY_LIMIT

        # Simulation state
        self.is_simulating = False
        self.sim_batches_count = 0
        self.sim_txns_count = 0

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
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # 1. Header Row (Title, Subtitle, Live Status Indicator)
        hdr_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title_lbl = QLabel("Transaction Feed")
        title_lbl.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {COLOR_TEXT_PRIMARY};")
        sub_lbl = QLabel("Live Multi-Bank Surveillance Stream with Deterministic 4-Factor Risk Assessment")
        sub_lbl.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_SECONDARY};")

        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_lbl)
        hdr_layout.addLayout(title_box)
        hdr_layout.addStretch()

        # Simulation Live Status Badge
        self.lbl_sim_status = QLabel("● Simulation: Idle")
        self.lbl_sim_status.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {COLOR_TEXT_MUTED};")
        self.lbl_sim_counters = QLabel("Batches: 0 | Ingested: 0 txns")
        self.lbl_sim_counters.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_MUTED};")
        hdr_layout.addWidget(self.lbl_sim_status)
        hdr_layout.addSpacing(16)
        hdr_layout.addWidget(self.lbl_sim_counters)
        layout.addLayout(hdr_layout)

        # 2. Distinct Dual-Group Operational Toolbars
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(12)

        # Group A: Simulation Controls Frame
        group_a_frame = QFrame()
        group_a_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #FFFFFF;
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                padding: 4px 10px;
            }}
        """)
        group_a_layout = QHBoxLayout(group_a_frame)
        group_a_layout.setContentsMargins(6, 4, 6, 4)
        group_a_layout.setSpacing(8)

        lbl_sim_grp = QLabel("SIMULATION:")
        lbl_sim_grp.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {COLOR_TEXT_SECONDARY}; letter-spacing: 0.5px;")
        group_a_layout.addWidget(lbl_sim_grp)

        self.btn_start = QPushButton("▶ Start Simulation")
        self.btn_start.setObjectName("primaryButton")
        self.btn_start.clicked.connect(self.start_simulation)

        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_pause.setObjectName("secondaryButton")
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self.pause_simulation)

        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.setObjectName("dangerButton")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_simulation)

        interval_lbl = QLabel("Interval:")
        interval_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px; font-weight: 600;")

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 30)
        self.interval_spin.setValue(self.sim_interval_sec)
        self.interval_spin.setSuffix("s")
        self.interval_spin.valueChanged.connect(self._on_interval_changed)

        self.btn_batch_100 = QPushButton("⚡ Ingest Batch 100")
        self.btn_batch_100.setObjectName("secondaryButton")
        self.btn_batch_100.setToolTip("Generates a balanced 100-transaction simulation batch (80% Clear, 15% Review, 5% Auto-Block)")
        self.btn_batch_100.clicked.connect(self.generate_batch_100)

        group_a_layout.addWidget(self.btn_start)
        group_a_layout.addWidget(self.btn_pause)
        group_a_layout.addWidget(self.btn_stop)
        group_a_layout.addWidget(interval_lbl)
        group_a_layout.addWidget(self.interval_spin)
        group_a_layout.addWidget(self.btn_batch_100)

        toolbar_layout.addWidget(group_a_frame)

        # Group B: Feed & Screening Operations Frame
        group_b_frame = QFrame()
        group_b_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #FFFFFF;
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                padding: 4px 10px;
            }}
        """)
        group_b_layout = QHBoxLayout(group_b_frame)
        group_b_layout.setContentsMargins(6, 4, 6, 4)
        group_b_layout.setSpacing(8)

        lbl_ops_grp = QLabel("OPERATIONS:")
        lbl_ops_grp.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {COLOR_TEXT_SECONDARY}; letter-spacing: 0.5px;")
        group_b_layout.addWidget(lbl_ops_grp)

        self.btn_refresh = QPushButton("🔄 Refresh Feed")
        self.btn_refresh.setObjectName("secondaryButton")
        self.btn_refresh.setToolTip("Reload warehouse transactions from database")
        self.btn_refresh.clicked.connect(lambda: self.load_feed_data(force=True))

        self.btn_gen_now = QPushButton("➕ Ingest Single Txn")
        self.btn_gen_now.setObjectName("secondaryButton")
        self.btn_gen_now.clicked.connect(self.generate_single_transaction)

        self.btn_demo_autoblock = QPushButton("🚨 Demo Auto-Block")
        self.btn_demo_autoblock.setObjectName("dangerButton")
        self.btn_demo_autoblock.setToolTip("Trigger reproducible 3-factor fraud pattern (Velocity + Device + Large Amount)")
        self.btn_demo_autoblock.clicked.connect(self.trigger_demo_auto_block)

        self.btn_rescreen = QPushButton("⚡ Re-Screen")
        self.btn_rescreen.setObjectName("secondaryButton")
        self.btn_rescreen.clicked.connect(self.rescreen_warehouse)

        group_b_layout.addWidget(self.btn_refresh)
        group_b_layout.addWidget(self.btn_gen_now)
        group_b_layout.addWidget(self.btn_demo_autoblock)
        group_b_layout.addWidget(self.btn_rescreen)

        toolbar_layout.addWidget(group_b_frame)
        toolbar_layout.addStretch()
        layout.addLayout(toolbar_layout)

        # 3. KPI Metrics Bar
        self.kpi_frame = QWidget()
        kpi_layout = QHBoxLayout(self.kpi_frame)
        kpi_layout.setContentsMargins(0, 0, 0, 0)
        kpi_layout.setSpacing(12)

        self.lbl_total = self._create_kpi_label("MONITORED TRANSACTIONS", "0", COLOR_TEXT_PRIMARY)
        self.lbl_susp = self._create_kpi_label("FLAGGED SUSPICIOUS", "0", COLOR_BLOCKED)
        self.lbl_clean = self._create_kpi_label("CLEARED (NORMAL)", "0", COLOR_CLEAR)
        self.lbl_ratio = self._create_kpi_label("FRAUD DETECTION RATIO", "0.0%", COLOR_REVIEW)

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
        self.combo_status.addItems([
            "All Enforcement States",
            "Clear (Green)",
            "Review Pending (Amber)",
            "Auto-Blocked (Red)",
            "Manually Blocked (Red)",
            "Released (Blue)"
        ])
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
                background-color: #FFFFFF;
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                padding: 6px 12px;
            }}
        """)
        loading_layout = QHBoxLayout(self.loading_frame)
        loading_layout.setContentsMargins(10, 4, 10, 4)
        loading_layout.setSpacing(12)

        self.loading_lbl = QLabel("🔄 Loading transactions & screening factors from warehouse in background...")
        self.loading_lbl.setStyleSheet(f"color: {COLOR_ACCENT}; font-size: 12px; font-weight: 600; background: transparent;")

        self.loading_progress = QProgressBar()
        self.loading_progress.setRange(0, 0)  # Indeterminate animated bar
        self.loading_progress.setFixedHeight(4)
        self.loading_progress.setTextVisible(False)
        self.loading_progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: #E2E8F0;
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {COLOR_ACCENT};
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
            (6, 110),  # Amount (₹)
            (7, 85),   # Status
            (8, 80),   # Method
            (9, 130),  # Risk Result
            (10, 240), # Triggered Rules
        ]
        for col_idx, width in col_widths:
            self.table.setColumnWidth(col_idx, width)
        header.setSectionResizeMode(10, QHeaderView.Stretch)

        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._on_table_row_double_click)

        layout.addWidget(self.table, 1)

        # 6. Pagination / Load More Controls Footer
        pagination_frame = QFrame()
        pagination_frame.setStyleSheet(f"""
            background-color: #FFFFFF;
            border: 1px solid {COLOR_BORDER};
            border-radius: 6px;
            padding: 4px 12px;
        """)
        pagination_layout = QHBoxLayout(pagination_frame)
        pagination_layout.setContentsMargins(10, 4, 10, 4)
        pagination_layout.setSpacing(12)

        self.lbl_pagination = QLabel("Showing 0 of 0 transactions")
        self.lbl_pagination.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; font-weight: 500;")

        self.btn_load_more = QPushButton("⬇ Load More (+100)")
        self.btn_load_more.setObjectName("secondaryButton")
        self.btn_load_more.setToolTip("Render next 100 transactions into the table")
        self.btn_load_more.clicked.connect(self._on_load_more_clicked)

        self.btn_show_all = QPushButton("⏬ Show All")
        self.btn_show_all.setObjectName("secondaryButton")
        self.btn_show_all.setToolTip("Render all matching transactions into the table")
        self.btn_show_all.clicked.connect(self._on_show_all_clicked)

        pagination_layout.addWidget(self.lbl_pagination)
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.btn_load_more)
        pagination_layout.addWidget(self.btn_show_all)

        layout.addWidget(pagination_frame)

    def _create_kpi_label(self, title: str, init_val: str, color: str) -> QWidget:
        w = QFrame()
        w.setStyleSheet(f"""
            QFrame {{
                background-color: #FFFFFF;
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                padding: 6px 12px;
            }}
        """)
        l = QVBoxLayout(w)
        l.setContentsMargins(4, 2, 4, 2)
        l.setSpacing(2)

        t = QLabel(title.upper())
        t.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {COLOR_TEXT_SECONDARY}; letter-spacing: 0.4px; background: transparent;")
        v = QLabel(init_val)
        v.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {color}; background: transparent;")

        l.addWidget(t)
        l.addWidget(v)
        w.value_label = v
        return w

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

        # 1. Enforcement State Filter
        stat_choice = self.combo_status.currentText()
        if stat_choice == "Clear (Green)":
            df = df[df["enforcement_status"] == "CLEAR"]
        elif stat_choice == "Review Pending (Amber)":
            df = df[df["enforcement_status"] == "REVIEW_PENDING"]
        elif stat_choice == "Auto-Blocked (Red)":
            df = df[df["enforcement_status"] == "AUTO_BLOCKED"]
        elif stat_choice == "Manually Blocked (Red)":
            df = df[df["enforcement_status"] == "MANUALLY_BLOCKED"]
        elif stat_choice == "Released (Blue)":
            df = df[df["enforcement_status"] == "RELEASED"]

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

            clear_bg = QBrush(QColor(COLOR_CLEAR_BG))
            clear_fg = QBrush(QColor(COLOR_CLEAR))
            review_bg = QBrush(QColor(COLOR_REVIEW_BG))
            review_fg = QBrush(QColor(COLOR_REVIEW))
            blocked_bg = QBrush(QColor(COLOR_BLOCKED_BG))
            blocked_fg = QBrush(QColor(COLOR_BLOCKED))
            released_bg = QBrush(QColor(COLOR_RELEASED_BG))
            released_fg = QBrush(QColor(COLOR_RELEASED))
            text_fg = QBrush(QColor(COLOR_TEXT_PRIMARY))
            sec_fg = QBrush(QColor(COLOR_TEXT_SECONDARY))

            for row_idx, row in sliced_df.iterrows():
                enf_st = str(row.get("enforcement_status", "CLEAR"))
                if enf_st in ("AUTO_BLOCKED", "MANUALLY_BLOCKED"):
                    badge_bg = blocked_bg
                    badge_fg = blocked_fg
                    res_str = "AUTO-BLOCKED" if enf_st == "AUTO_BLOCKED" else "MANUALLY BLOCKED"
                elif enf_st == "RELEASED":
                    badge_bg = released_bg
                    badge_fg = released_fg
                    res_str = "RELEASED"
                elif enf_st == "REVIEW_PENDING":
                    badge_bg = review_bg
                    badge_fg = review_fg
                    res_str = "REVIEW PENDING"
                else:
                    badge_bg = clear_bg
                    badge_fg = clear_fg
                    res_str = "CLEAR"

                amt_inr = f"₹{row['amount_inr']:,.2f}"

                items = [
                    (row["transaction_timestamp"], Qt.AlignLeft),
                    (str(row["source_transaction_id"]), Qt.AlignLeft),
                    (row["bank_code"], Qt.AlignCenter),
                    (row["source_account_ref"], Qt.AlignLeft),
                    (row["destination_bank"], Qt.AlignCenter),
                    (row["destination_account_ref"], Qt.AlignLeft),
                    (amt_inr, Qt.AlignRight),
                    (row["transaction_status"], Qt.AlignCenter),
                    (row.get("payment_method", "N/A"), Qt.AlignCenter),
                    (res_str, Qt.AlignCenter),
                    (row["detection_factors"], Qt.AlignLeft),
                ]

                for col_idx, (text, alignment) in enumerate(items):
                    item = QTableWidgetItem(str(text))
                    item.setTextAlignment(alignment | Qt.AlignVCenter)
                    item.setToolTip(str(text))
                    if col_idx == 9:  # Result column with compact colored badge
                        item.setBackground(badge_bg)
                        item.setForeground(badge_fg)
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                    elif col_idx == 6:  # Amount column
                        item.setForeground(text_fg)
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                    elif col_idx in (1, 3, 5):  # ID / Accounts
                        item.setForeground(text_fg)
                    else:
                        item.setForeground(sec_fg)
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
    def _update_sim_status_badge(self, state: str):
        if state == "RUNNING":
            self.lbl_sim_status.setText("● Simulation: Active (Live Multi-Bank Stream)")
            self.lbl_sim_status.setStyleSheet(f"font-size: 12px; font-weight: 800; color: {COLOR_GREEN};")
        elif state == "PAUSED":
            self.lbl_sim_status.setText("● Simulation: Paused")
            self.lbl_sim_status.setStyleSheet(f"font-size: 12px; font-weight: 800; color: {COLOR_AMBER};")
        else:
            self.lbl_sim_status.setText("● Simulation: Idle")
            self.lbl_sim_status.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {COLOR_TEXT_MUTED};")

        self.lbl_sim_counters.setText(
            f"Batches: {self.sim_batches_count} | Multi-Bank Ingested: {self.sim_txns_count} txns"
        )

    def start_simulation(self):
        logger.info("[SIMULATION] Start requested")
        if self.is_simulating:
            return

        self.is_simulating = True
        self.sim_timer.start(self.sim_interval_sec * 1000)
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self._update_sim_status_badge("RUNNING")

        # Immediately launch first batch if worker is not already running
        if not (self.generation_worker and self.generation_worker.isRunning()):
            self.generate_single_transaction()

    def pause_simulation(self):
        self.sim_timer.stop()
        self.is_simulating = False
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._update_sim_status_badge("PAUSED")

    def stop_simulation(self):
        self.sim_timer.stop()
        self.is_simulating = False
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self._update_sim_status_badge("IDLE")

        # Safely clean up worker reference without leaving stale threads
        if self.generation_worker and self.generation_worker.isRunning():
            self.generation_worker.stop()
            self.generation_worker.wait(1000)
        self.generation_worker = None

    def _on_sim_timer_tick(self):
        # Prevent spawning overlapping simulation workers
        if self.generation_worker and self.generation_worker.isRunning():
            return
        self.generate_single_transaction()

    def generate_single_transaction(self):
        if self.generation_worker and self.generation_worker.isRunning():
            return

        self.generation_worker = TransactionGenerationWorker(mode="NORMAL", batch_size=3, parent=self)
        self.generation_worker.generation_completed.connect(self._on_tx_generated)
        self.generation_worker.generation_failed.connect(self._on_tx_gen_failed)
        self.generation_worker.start()

    def generate_batch_100(self):
        """Generates a balanced 100-transaction simulation batch (80% Clear, 15% Review, 5% Auto-Block)."""
        if self.generation_worker and self.generation_worker.isRunning():
            return

        if hasattr(self, "btn_batch_100"):
            self.btn_batch_100.setEnabled(False)

        self.generation_worker = TransactionGenerationWorker(mode="NORMAL", batch_size=100, parent=self)
        self.generation_worker.generation_completed.connect(self._on_batch_100_completed)
        self.generation_worker.generation_failed.connect(self._on_tx_gen_failed)
        self.generation_worker.start()

    @Slot(dict)
    def _on_batch_100_completed(self, res: dict):
        if hasattr(self, "btn_batch_100"):
            self.btn_batch_100.setEnabled(True)

        self.sim_batches_count += 1
        gen_ids = res.get("generated_ids", [])
        self.sim_txns_count += len(gen_ids) if gen_ids else 100
        self._update_sim_status_badge("RUNNING" if self.is_simulating else "IDLE")

        self.mark_dirty()
        self.load_feed_data(force=True)
        self.screening_completed.emit(res)
        logger.info("[SIMULATION] Transaction Feed refreshed (100-Txn Batch)")

        counts = res.get("counts", {})
        pcts = res.get("percentages", {})
        tgts = res.get("targets", {})
        devs = res.get("deviations", {})
        factors = res.get("factors", {})

        c_cnt = counts.get("CLEAR", 0)
        c_pct = pcts.get("CLEAR", 0.0)
        r_cnt = counts.get("REVIEW_PENDING", 0)
        r_pct = pcts.get("REVIEW_PENDING", 0.0)
        b_cnt = counts.get("AUTO_BLOCKED", 0)
        b_pct = pcts.get("AUTO_BLOCKED", 0.0)

        f0 = factors.get("0_factors", 0)
        f1 = factors.get("1_factor", 0)
        f2 = factors.get("2_factors", 0)
        f3 = factors.get("3_factors", 0)
        f4 = factors.get("4_factors", 0)

        run_id = res.get("detection", {}).get("detection_run_id", "N/A")
        batch_slug = res.get("batch_slug", "N/A")

        summary_msg = (
            f"100-Transaction Balanced Simulation Batch Ingested!\n\n"
            f"Batch ID: {batch_slug} | Detection Run: {run_id}\n\n"
            f"Enforcement Classification Breakdown:\n"
            f"• CLEAR: {c_cnt} txns ({c_pct:.1f}% vs Target {tgts.get('CLEAR', 80.0):.1f}%, Dev: {'+' if devs.get('CLEAR', 0)>=0 else ''}{devs.get('CLEAR', 0):.1f}%)\n"
            f"• REVIEW_PENDING: {r_cnt} txns ({r_pct:.1f}% vs Target {tgts.get('REVIEW_PENDING', 15.0):.1f}%, Dev: {'+' if devs.get('REVIEW_PENDING', 0)>=0 else ''}{devs.get('REVIEW_PENDING', 0):.1f}%)\n"
            f"• AUTO_BLOCKED: {b_cnt} txns ({b_pct:.1f}% vs Target {tgts.get('AUTO_BLOCKED', 5.0):.1f}%, Dev: {'+' if devs.get('AUTO_BLOCKED', 0)>=0 else ''}{devs.get('AUTO_BLOCKED', 0):.1f}%)\n"
            f"• Total Evaluated: {counts.get('TOTAL', 100)} txns\n\n"
            f"Triggered Factors:\n"
            f"• 0 Factors (Clean): {f0}\n"
            f"• 1 Factor (Review):  {f1}\n"
            f"• 2 Factors (Review): {f2}\n"
            f"• 3 Factors (Blocked): {f3}\n"
            f"• 4 Factors (Blocked): {f4}\n\n"
            f"All transactions have been screened before simulated completion."
        )

        QMessageBox.information(
            self,
            "100-Transaction Batch Completed",
            summary_msg
        )

    def trigger_demo_auto_block(self):
        """Launches controlled 3-factor fraud scenario to verify automatic blocking."""
        if self.generation_worker and self.generation_worker.isRunning():
            return

        self.btn_demo_autoblock.setEnabled(False)
        self.generation_worker = TransactionGenerationWorker(mode="DEMO_AUTO_BLOCK", parent=self)
        self.generation_worker.generation_completed.connect(self._on_demo_completed)
        self.generation_worker.generation_failed.connect(self._on_tx_gen_failed)
        self.generation_worker.start()

    @Slot(dict)
    def _on_demo_completed(self, res: dict):
        self.btn_demo_autoblock.setEnabled(True)
        self.mark_dirty()
        self.load_feed_data(force=True)
        self.screening_completed.emit(res)
        logger.info("[SIMULATION] Transaction Feed refreshed (Demo Auto-Block)")

        details = res.get("details", {})
        txn_id = res.get("target_transaction_id", details.get("target_transaction_id", "DEMO-TARGET"))
        amt = details.get("amount_inr", 150000.0)
        fc = details.get("triggered_factor_count", 3)
        summary = details.get("triggered_factors_summary", "Velocity, Device, Amount")
        st = details.get("enforcement_status", "AUTO_BLOCKED")
        fact_st = details.get("fact_status", "PENDING")

        QMessageBox.information(
            self,
            "Auto-Block Scenario Injected",
            f"Controlled 3-factor fraud pattern successfully verified!\n\n"
            f"• Target Transaction: {txn_id}\n"
            f"• Amount: ₹{amt:,.2f}\n"
            f"• Triggered Rules ({fc}): {summary}\n"
            f"• Enforcement Decision: {st} (Tier 3)\n"
            f"• Lifecycle State: {fact_st} (Held from simulated completion)\n"
            f"• Active Auto-Block: Persisted to database\n\n"
            f"You can now inspect and release it in the 'Automatically Blocked Transactions' page."
        )

    @Slot(dict)
    def _on_tx_generated(self, res: dict):
        self.sim_batches_count += 1
        gen_ids = res.get("generated_ids", [])
        self.sim_txns_count += len(gen_ids) if gen_ids else 3
        self._update_sim_status_badge("RUNNING" if self.is_simulating else "IDLE")

        self.mark_dirty()
        self.load_feed_data(force=True)
        self.screening_completed.emit(res)
        logger.info("[SIMULATION] Transaction Feed refreshed")

    @Slot(dict)
    def _on_tx_gen_failed(self, err_data: dict):
        # Stop simulation timer immediately on error to avoid repeated alert loops
        self.stop_simulation()
        if hasattr(self, "btn_demo_autoblock"):
            self.btn_demo_autoblock.setEnabled(True)
        if hasattr(self, "btn_batch_100"):
            self.btn_batch_100.setEnabled(True)

        stage = err_data.get("failing_stage", "UNKNOWN")
        exc_type = err_data.get("exception_type", "Exception")
        msg = err_data.get("error_message", "Unknown error")
        db = err_data.get("database_path", "N/A")
        cfg = err_data.get("config_path", "N/A")

        logger.error(f"[SIMULATION] Failure in stage '{stage}': {exc_type}: {msg}")

        dialog_text = (
            f"Simulation failed during stage: <b>{stage}</b><br><br>"
            f"<b>Exception:</b> {exc_type}: {msg}<br><br>"
            f"<b>Active Database:</b><br><code>{db}</code><br><br>"
            f"<b>Configuration Path:</b><br><code>{cfg}</code><br><br>"
            f"The simulation timer has been safely stopped. Detailed traceback recorded in application logs."
        )
        QMessageBox.critical(self, f"Simulation Error — {stage}", dialog_text)

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
        self.screening_completed.emit(res)
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
