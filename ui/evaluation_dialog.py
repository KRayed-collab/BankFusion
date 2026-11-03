"""
BankFusion UI Component: Dual Evaluation Dialog
===============================================
Presents two independent evaluation regimes:
1. Overall Fraud Detection Performance (Detector Quality: Precision, Recall, F1, Confusion Matrix)
2. Automatic Blocking Performance (Policy Quality: Block Precision, Block Recall, Triage vs Misses, Releases)
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QFrame, QGridLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy
)
from PySide6.QtCore import Qt

from database.database_connection import SessionLocal
from fraud_detection.evaluate_detection_results import (
    evaluate_overall_fraud_detection,
    evaluate_automatic_blocking,
)
from ui.theme import (
    COLOR_BG, COLOR_PANEL_BG, COLOR_CARD_BG, COLOR_BORDER,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED,
    COLOR_BLUE, COLOR_GREEN, COLOR_RED, COLOR_AMBER, DARK_THEME_QSS
)


class EvaluationDialog(QDialog):
    """Modal dialog displaying dual evaluation performance metrics."""

    def __init__(self, parent=None, detection_run_id=None):
        super().__init__(parent)
        self.detection_run_id = detection_run_id
        self.setWindowTitle("BankFusion — Model & Policy Performance Evaluation")
        self.resize(880, 680)
        self.setMinimumSize(780, 560)
        self.setStyleSheet(DARK_THEME_QSS)

        self._build_ui()
        self._load_metrics()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header
        hdr = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        t_lbl = QLabel("📊 Separate Model & Policy Performance Evaluation")
        t_lbl.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {COLOR_TEXT_PRIMARY};")
        sub_lbl = QLabel("Independent verification of algorithmic detection vs automated enforcement policy")
        sub_lbl.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_MUTED};")
        title_box.addWidget(t_lbl)
        title_box.addWidget(sub_lbl)

        hdr.addLayout(title_box)
        hdr.addStretch()

        btn_close = QPushButton("✕ Close")
        btn_close.setObjectName("secondaryButton")
        btn_close.clicked.connect(self.accept)
        hdr.addWidget(btn_close)

        layout.addLayout(hdr)

        # Tabs
        self.tabs = QTabWidget()
        self.tab_detection = QWidget()
        self.tab_blocking = QWidget()

        self.tabs.addTab(self.tab_detection, "🎯 1. Overall Fraud Detection Performance")
        self.tabs.addTab(self.tab_blocking, "🚫 2. Automatic Blocking Policy Performance")

        layout.addWidget(self.tabs)

        self._build_detection_tab()
        self._build_blocking_tab()

    def _build_detection_tab(self):
        layout = QVBoxLayout(self.tab_detection)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Description banner
        banner = QLabel(
            "<b>Algorithmic Detection Evaluation:</b> Evaluates whether the 4 deterministic rules "
            "successfully flagged suspicious transactions against ground-truth labels. "
            "Evaluated independently of whether an alert was auto-blocked or sent for operator triage."
        )
        banner.setWordWrap(True)
        banner.setStyleSheet(f"background-color: {COLOR_CARD_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 6px; padding: 10px; font-size: 11px; color: {COLOR_TEXT_SECONDARY};")
        layout.addWidget(banner)

        # Metric KPI cards
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(12)

        self.kpi_det_precision = self._create_kpi_card("Precision", "0.0%", "TP / (TP + FP)")
        self.kpi_det_recall = self._create_kpi_card("Recall", "0.0%", "TP / (TP + FN)")
        self.kpi_det_f1 = self._create_kpi_card("F1-Score", "0.00", "Harmonic Mean")
        self.kpi_det_acc = self._create_kpi_card("Accuracy", "0.0%", "All Correct / Total")

        kpi_grid.addWidget(self.kpi_det_precision, 0, 0)
        kpi_grid.addWidget(self.kpi_det_recall, 0, 1)
        kpi_grid.addWidget(self.kpi_det_f1, 0, 2)
        kpi_grid.addWidget(self.kpi_det_acc, 0, 3)
        layout.addLayout(kpi_grid)

        # Confusion Matrix Table
        cm_lbl = QLabel("Confusion Matrix (Ground Truth vs Algorithmic Flag)")
        cm_lbl.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {COLOR_TEXT_PRIMARY};")
        layout.addWidget(cm_lbl)

        self.cm_table = QTableWidget(2, 2)
        self.cm_table.setHorizontalHeaderLabels(["Predicted Suspicious (1)", "Predicted Clean (0)"])
        self.cm_table.setVerticalHeaderLabels(["Actual Fraud (1)", "Actual Legitimate (0)"])
        self.cm_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cm_table.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cm_table.setFixedHeight(110)
        layout.addWidget(self.cm_table)

        # Academic / Viva Notice
        viva_box = QLabel(
            "<b>🎓 Academic Evaluation Note (DWM Viva / Defense):</b> "
            "Our synthetic dataset evaluates rule correctness against seeded behavioral scenarios. "
            "High test metrics demonstrate that deterministic velocity, shared-device, amount, and cross-bank "
            "algorithms execute faithfully according to banking logic specifications without ground-truth leakage."
        )
        viva_box.setWordWrap(True)
        viva_box.setStyleSheet(f"background-color: #F8FAFC; border: 1px solid {COLOR_BORDER}; border-radius: 6px; padding: 10px; font-size: 11px; color: {COLOR_TEXT_SECONDARY};")
        layout.addWidget(viva_box)
        layout.addStretch()

    def _build_blocking_tab(self):
        layout = QVBoxLayout(self.tab_blocking)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Policy Description banner
        banner = QLabel(
            "<b>Enforcement Policy Evaluation:</b> Measures the effectiveness of the 3-tier risk threshold "
            "(Tier 3: >= 3 distinct factors -> AUTO_BLOCKED). Evaluates automated intervention precision, "
            "customer friction (legitimate auto-blocks), and safe routing of borderline cases to human triage."
        )
        banner.setWordWrap(True)
        banner.setStyleSheet(f"background-color: {COLOR_CARD_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 6px; padding: 10px; font-size: 11px; color: {COLOR_TEXT_SECONDARY};")
        layout.addWidget(banner)

        # Metric KPI cards
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(12)

        self.kpi_blk_prec = self._create_kpi_card("Block Precision", "0.0%", "Auto-Blocked & Fraud / Total Auto-Blocked")
        self.kpi_blk_recall = self._create_kpi_card("Block Recall", "0.0%", "Auto-Blocked / Total Fraud")
        self.kpi_blk_rate = self._create_kpi_card("Auto-Block Rate", "0.0%", "Auto-Blocked / Total Volume")
        self.kpi_blk_val = self._create_kpi_card("Blocked Value", "₹0.00", "Total Value of Auto-Blocks")

        kpi_grid.addWidget(self.kpi_blk_prec, 0, 0)
        kpi_grid.addWidget(self.kpi_blk_recall, 0, 1)
        kpi_grid.addWidget(self.kpi_blk_rate, 0, 2)
        kpi_grid.addWidget(self.kpi_blk_val, 0, 3)
        layout.addLayout(kpi_grid)

        # Critical Triage Clarification Box
        self.lbl_triage_clarification = QLabel(
            "<b>⚡ Crucial Evaluation Distinction:</b><br>"
            "• <b>Suspicious Routed to Manual Review:</b> <span id='triage_count'>0</span> transactions triggered 1-2 factors and were sent to human triage.<br>"
            "  <i>These are <u>NOT</u> detector false negatives or misses! They were correctly caught by the detector and intentionally assigned to Tier 2 human review to prevent wrongful auto-blocking.</i><br>"
            "• <b>Legitimate Auto-Blocked (False Blocks):</b> <span id='false_block_count'>0</span> clean transactions subjected to automated block (friction).<br>"
            "• <b>Unflagged Misses (True False Negatives):</b> <span id='miss_count'>0</span> fraudulent transactions with 0 triggered factors.<br>"
            "• <b>Operator Overrides / Releases:</b> <span id='release_count'>0</span> auto-blocked transactions released after investigation."
        )
        self.lbl_triage_clarification.setTextFormat(Qt.RichText)
        self.lbl_triage_clarification.setWordWrap(True)
        self.lbl_triage_clarification.setStyleSheet(f"background-color: {COLOR_CARD_BG}; border: 1px solid {COLOR_AMBER}; border-radius: 6px; padding: 12px; font-size: 11px; color: {COLOR_TEXT_PRIMARY};")
        layout.addWidget(self.lbl_triage_clarification)

        layout.addStretch()

    def _create_kpi_card(self, title: str, value: str, subtitle: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_CARD_BG};
                border: 1px solid {COLOR_BORDER};
                border-radius: 8px;
                padding: 12px;
            }}
        """)
        l = QVBoxLayout(card)
        l.setContentsMargins(4, 4, 4, 4)
        l.setSpacing(4)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {COLOR_TEXT_MUTED};")

        v_lbl = QLabel(value)
        v_lbl.setObjectName("kpi_value")
        v_lbl.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {COLOR_TEXT_PRIMARY};")

        s_lbl = QLabel(subtitle)
        s_lbl.setStyleSheet(f"font-size: 10px; color: {COLOR_TEXT_MUTED};")

        l.addWidget(t_lbl)
        l.addWidget(v_lbl)
        l.addWidget(s_lbl)
        return card

    def _load_metrics(self):
        with SessionLocal() as session:
            det = evaluate_overall_fraud_detection(session, self.detection_run_id)
            blk = evaluate_automatic_blocking(session, self.detection_run_id)

        # Update Detection Tab
        self.kpi_det_precision.findChild(QLabel, "kpi_value").setText(f"{det['precision'] * 100:.1f}%")
        self.kpi_det_recall.findChild(QLabel, "kpi_value").setText(f"{det['recall'] * 100:.1f}%")
        self.kpi_det_f1.findChild(QLabel, "kpi_value").setText(f"{det['f1']:.3f}")
        self.kpi_det_acc.findChild(QLabel, "kpi_value").setText(f"{det['accuracy'] * 100:.1f}%")

        # Confusion Matrix items
        tp_item = QTableWidgetItem(f"TP: {det['tp']}")
        tp_item.setTextAlignment(Qt.AlignCenter)
        tp_item.setForeground(Qt.green)

        fn_item = QTableWidgetItem(f"FN: {det['fn']}")
        fn_item.setTextAlignment(Qt.AlignCenter)
        fn_item.setForeground(Qt.red)

        fp_item = QTableWidgetItem(f"FP: {det['fp']}")
        fp_item.setTextAlignment(Qt.AlignCenter)
        fp_item.setForeground(Qt.yellow)

        tn_item = QTableWidgetItem(f"TN: {det['tn']}")
        tn_item.setTextAlignment(Qt.AlignCenter)
        tn_item.setForeground(Qt.white)

        self.cm_table.setItem(0, 0, tp_item)
        self.cm_table.setItem(0, 1, fn_item)
        self.cm_table.setItem(1, 0, fp_item)
        self.cm_table.setItem(1, 1, tn_item)

        # Update Blocking Tab
        self.kpi_blk_prec.findChild(QLabel, "kpi_value").setText(f"{blk['block_precision'] * 100:.1f}%")
        self.kpi_blk_recall.findChild(QLabel, "kpi_value").setText(f"{blk['block_recall'] * 100:.1f}%")
        self.kpi_blk_rate.findChild(QLabel, "kpi_value").setText(f"{blk['auto_block_rate'] * 100:.1f}%")
        self.kpi_blk_val.findChild(QLabel, "kpi_value").setText(f"₹{blk['blocked_amount_inr']:,.2f}")

        # Update Triage clarification text
        t_count = blk.get("routed_to_review_suspicious", 0)
        fb_count = blk.get("legitimate_auto_blocked", 0)
        miss_count = blk.get("unflagged_suspicious", 0)
        rel_count = blk.get("released_auto_blocks", 0)

        clarif_html = (
            "<b>⚡ Crucial Evaluation Distinction:</b><br>"
            f"• <b>Suspicious Routed to Manual Review:</b> <b style='color:#f59e0b;'>{t_count}</b> transactions triggered 1-2 factors and were routed for human triage.<br>"
            "  <i>These are <u>NOT</u> detector false negatives or detection failures! They were successfully identified by the multi-bank screening engine and intentionally directed to Tier 2 human investigation.</i><br>"
            f"• <b>Legitimate Auto-Blocked (False Blocks / Friction):</b> <b style='color:#ef4444;'>{fb_count}</b> clean transactions incorrectly auto-blocked.<br>"
            f"• <b>Unflagged Misses (True False Negatives):</b> <b style='color:#ef4444;'>{miss_count}</b> fraudulent transactions with 0 triggered factors.<br>"
            f"• <b>Operator Overrides / Releases:</b> <b style='color:#3b82f6;'>{rel_count}</b> auto-blocks inspected and released by operators with audited justification."
        )
        self.lbl_triage_clarification.setText(clarif_html)

