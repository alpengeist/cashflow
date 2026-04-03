from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

if __package__ in {None, ""}:
    from cashflow.database import Database
    from cashflow.formatting import format_amount
    from cashflow.pdf_importer import PdfImportService
    from cashflow.reports import InOutReportTab
    from cashflow.settings import AppSettings, SettingsStore
else:
    from .database import Database
    from .formatting import format_amount
    from .pdf_importer import PdfImportService
    from .reports import InOutReportTab
    from .settings import AppSettings, SettingsStore


APP_ROOT = Path(__file__).resolve().parents[2]


class ImportWorker(QThread):
    progress = Signal(str)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        *,
        pdf_paths: list[Path],
        db_path: Path,
        model_name: str,
        api_key: str,
        extra_rules: str,
    ) -> None:
        super().__init__()
        self.pdf_paths = pdf_paths
        self.db_path = db_path
        self.model_name = model_name
        self.api_key = api_key
        self.extra_rules = extra_rules

    def run(self) -> None:
        try:
            service = PdfImportService(
                self.db_path,
                self.model_name,
                self.api_key,
                self.extra_rules,
            )
            total_items = 0
            for index, pdf_path in enumerate(self.pdf_paths, start=1):
                self.progress.emit(
                    f"Importing {pdf_path.name} ({index}/{len(self.pdf_paths)})..."
                )
                total_items += service.import_pdf(pdf_path)
            self.succeeded.emit(
                f"Imported {total_items} line items from {len(self.pdf_paths)} PDF(s)."
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ImportTab(QWidget):
    import_succeeded = Signal()
    MODEL_INPUT_WIDTH = 220
    SEARCH_INPUT_CHARS = 50
    BUTTON_WIDTH = 140
    CONTROLS_MARGIN = 10
    DOCUMENT_COLUMN = 5

    def __init__(self, database: Database, settings_store: SettingsStore) -> None:
        super().__init__()
        self.table_limit = 500
        self.search_debounce_ms = 300
        self.db_path = APP_ROOT / "cashflow.db"
        self.database = database
        self.settings_store = settings_store
        self.settings = self.settings_store.load()
        self.worker: ImportWorker | None = None
        self.progress_dialog: QProgressDialog | None = None
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(self.search_debounce_ms)
        self.search_timer.timeout.connect(self.refresh_table)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(0)
        layout.addLayout(header_row)

        self.import_button = QPushButton("Import PDFs")
        self.import_button.setFixedWidth(self.BUTTON_WIDTH)
        self.import_button.setStyleSheet(
            """
            QPushButton {
                background-color: #2563eb;
                color: white;
                border: 1px solid #1d4ed8;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:pressed {
                background-color: #1e40af;
            }
            QPushButton:disabled {
                background-color: #93c5fd;
                border-color: #93c5fd;
                color: #eff6ff;
            }
            """
        )
        self.import_button.clicked.connect(self.import_pdfs)
        header_row.addWidget(self.import_button)
        header_row.addStretch(1)

        controls_row = QWidget()
        controls_row.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        controls = QHBoxLayout(controls_row)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(self.CONTROLS_MARGIN)
        layout.addWidget(
            controls_row,
            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

        controls.addWidget(QLabel("Model"))
        self.model_input = QLineEdit(self.settings.openai_model or "gpt-4o-mini")
        self.model_input.setPlaceholderText("gpt-4o-mini")
        self.model_input.setFixedWidth(self.MODEL_INPUT_WIDTH)
        controls.addWidget(self.model_input)

        controls.addWidget(QLabel("Search"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter descriptions")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedWidth(
            self.search_input.fontMetrics().horizontalAdvance(
                "M" * self.SEARCH_INPUT_CHARS
            )
            + 24
        )
        self.search_input.textChanged.connect(self._schedule_search_refresh)
        self.search_input.returnPressed.connect(self._run_search_now)
        controls.addWidget(self.search_input)

        self.rules_toggle = QToolButton()
        self.rules_toggle.setText("Extra Categorization Rules")
        self.rules_toggle.setCheckable(True)
        self.rules_toggle.setChecked(False)
        self.rules_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.rules_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.rules_toggle.toggled.connect(self._toggle_rules_editor)
        layout.addWidget(self.rules_toggle)

        self.rules_container = QFrame()
        self.rules_container.setVisible(False)
        rules_layout = QVBoxLayout(self.rules_container)
        rules_layout.setContentsMargins(0, 0, 0, 0)
        rules_layout.setSpacing(6)

        rules_hint = QLabel(
            "Add freeform rules that should be appended to the OpenAI instructions "
            "for line item categorization."
        )
        rules_hint.setWordWrap(True)
        rules_layout.addWidget(rules_hint)

        self.rules_editor = QPlainTextEdit()
        self.rules_editor.setPlaceholderText(
            'Examples:\n- If description contains "spotify", categorize as "entertainment".\n'
            '- If description contains "miete", categorize as "rent".'
        )
        self.rules_editor.setPlainText(self.settings.categorization_rules or "")
        self.rules_editor.textChanged.connect(self._save_categorization_rules)
        rules_layout.addWidget(self.rules_editor)
        layout.addWidget(self.rules_container)

        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)

        self.status_label = QLabel("Ready.")
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [
                "Booked",
                "Description",
                "Amount",
                "Currency",
                "Category",
                "Document",
            ]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.cellClicked.connect(self._handle_table_click)
        layout.addWidget(self.table, stretch=1)

        self.refresh_table()

    def import_pdfs(self) -> None:
        initial_directory = self._get_initial_pdf_directory()
        pdf_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select ING PDFs",
            str(initial_directory),
            "PDF Files (*.pdf)",
        )
        if not pdf_paths:
            return

        self._save_last_pdf_directory(Path(pdf_paths[0]).parent)
        model_name = self.model_input.text().strip() or "gpt-4o-mini"
        self._save_openai_settings(model_name)

        self._set_busy(True)
        self.status_label.setText("Preparing import...")
        self._show_progress_dialog("Preparing import...")

        self.worker = ImportWorker(
            pdf_paths=[Path(path) for path in pdf_paths],
            db_path=self.db_path,
            model_name=model_name,
            api_key=self.settings.openai_api_key or "",
            extra_rules=self.rules_editor.toPlainText(),
        )
        self.worker.progress.connect(self._update_progress)
        self.worker.succeeded.connect(self._handle_success)
        self.worker.failed.connect(self._handle_failure)
        self.worker.start()

    def refresh_table(self, _text: str | None = None) -> None:
        search_text = self.search_input.text().strip()
        rows = self.database.fetch_line_items(
            self.table_limit,
            search_text=search_text or None,
        )
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            values = [
                row["booking_date"],
                row["description"],
                format_amount(row["amount_cents"]),
                row["currency"],
                row["category"] or "",
                row["file_name"],
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column_index == 2:
                    item.setTextAlignment(
                        int(
                            Qt.AlignmentFlag.AlignRight
                            | Qt.AlignmentFlag.AlignVCenter
                        )
                    )
                if column_index == self.DOCUMENT_COLUMN:
                    item.setData(Qt.ItemDataRole.UserRole, row["file_path"])
                    item.setToolTip(row["file_path"])
                self.table.setItem(row_index, column_index, item)

        self.table.setSortingEnabled(True)
        total_items = self.database.count_line_items()
        if search_text:
            matching_items = self.database.count_line_items(search_text)
            summary = (
                f"Database: {total_items} imported line items. "
                f"Found {matching_items} match(es)"
            )
            if matching_items > len(rows):
                summary += f", showing first {len(rows)}."
            else:
                summary += "."
        else:
            summary = f"Database: {total_items} imported line items"
            if total_items > len(rows):
                summary += f", showing latest {len(rows)}."
        self.summary_label.setText(summary)

    def _schedule_search_refresh(self, _text: str) -> None:
        self.search_timer.start()

    def _run_search_now(self) -> None:
        self.search_timer.stop()
        self.refresh_table()

    def _handle_table_click(self, row: int, column: int) -> None:
        if column != self.DOCUMENT_COLUMN:
            return
        item = self.table.item(row, column)
        if item is None:
            return
        document_path = item.data(Qt.ItemDataRole.UserRole)
        if not document_path:
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(document_path))):
            QMessageBox.warning(
                self,
                "Open document failed",
                f"Could not open:\n{document_path}",
            )

    def _handle_success(self, message: str) -> None:
        self._set_busy(False)
        self._close_progress_dialog()
        self.status_label.setText(message)
        self.refresh_table()
        self.import_succeeded.emit()

    def _handle_failure(self, message: str) -> None:
        self._set_busy(False)
        self._close_progress_dialog()
        self.status_label.setText(f"Import failed: {message}")
        QMessageBox.critical(self, "Import failed", message)

    def _set_busy(self, busy: bool) -> None:
        self.import_button.setEnabled(not busy)
        self.model_input.setEnabled(not busy)
        self.rules_toggle.setEnabled(not busy)
        self.rules_editor.setEnabled(not busy)

    def _get_initial_pdf_directory(self) -> Path:
        if self.settings.last_pdf_directory:
            directory = Path(self.settings.last_pdf_directory)
            if directory.is_dir():
                return directory
        return Path.home()

    def _save_last_pdf_directory(self, directory: Path) -> None:
        self.settings = replace(self.settings, last_pdf_directory=str(directory))
        self.settings_store.save(self.settings)

    def _save_openai_settings(self, model_name: str) -> None:
        self.settings = replace(self.settings, openai_model=model_name)
        self.settings_store.save(self.settings)

    def _save_categorization_rules(self) -> None:
        self.settings = replace(
            self.settings,
            categorization_rules=self.rules_editor.toPlainText().strip() or None,
        )
        self.settings_store.save(self.settings)

    def _toggle_rules_editor(self, expanded: bool) -> None:
        self.rules_container.setVisible(expanded)
        self.rules_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )

    def _show_progress_dialog(self, message: str) -> None:
        dialog = QProgressDialog(message, "", 0, 0, self)
        dialog.setWindowTitle("Importing PDFs")
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setMinimumDuration(0)
        dialog.setCancelButton(None)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.show()
        self.progress_dialog = dialog

    def _update_progress(self, message: str) -> None:
        self.status_label.setText(message)
        if self.progress_dialog is not None:
            self.progress_dialog.setLabelText(message)

    def _close_progress_dialog(self) -> None:
        if self.progress_dialog is None:
            return
        self.progress_dialog.close()
        self.progress_dialog.deleteLater()
        self.progress_dialog = None


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.db_path = APP_ROOT / "cashflow.db"
        self.database = Database(self.db_path)
        self.database.initialize()
        self.settings_store = SettingsStore()

        self.setWindowTitle("Cashflow Tool")
        self.resize(1280, 800)

        container = QWidget(self)
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Cashflow Tool")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")
        layout.addWidget(title)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, stretch=1)

        self.import_tab = ImportTab(self.database, self.settings_store)
        self.report_tab = InOutReportTab(self.database)
        self.import_tab.import_succeeded.connect(self.report_tab.refresh_years)

        self.tabs.addTab(self.import_tab, "Import")
        self.tabs.addTab(self.report_tab, "In/Out")
def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
