from __future__ import annotations

import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from dotenv import load_dotenv

if __package__ in {None, ""}:
    from cashflow.database import Database
    from cashflow.pdf_importer import PdfImportService
    from cashflow.settings import AppSettings, SettingsStore
else:
    from .database import Database
    from .pdf_importer import PdfImportService
    from .settings import AppSettings, SettingsStore


APP_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = Path(__file__).resolve().parent


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
    ) -> None:
        super().__init__()
        self.pdf_paths = pdf_paths
        self.db_path = db_path
        self.model_name = model_name

    def run(self) -> None:
        try:
            service = PdfImportService(self.db_path, self.model_name)
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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.db_path = APP_ROOT / "cashflow.db"
        self.database = Database(self.db_path)
        self.database.initialize()
        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load()
        self.worker: ImportWorker | None = None

        self.setWindowTitle("Cashflow Importer")
        self.resize(1100, 720)

        container = QWidget(self)
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("ING PDF Import")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Select exported ING Girokonto PDFs and send them directly to "
            "OpenAI as file inputs to extract structured line items."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self.api_key_label = QLabel()
        self._refresh_api_key_status()
        layout.addWidget(self.api_key_label)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        layout.addLayout(controls)

        controls.addWidget(QLabel("Model"))
        self.model_input = QLineEdit(os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
        self.model_input.setPlaceholderText("gpt-4o-mini")
        controls.addWidget(self.model_input, stretch=1)

        self.import_button = QPushButton("Import PDFs")
        self.import_button.clicked.connect(self.import_pdfs)
        controls.addWidget(self.import_button)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_table)
        controls.addWidget(self.refresh_button)

        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)

        self.status_label = QLabel("Ready.")
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "Booked",
                "Value",
                "Description",
                "Amount",
                "Currency",
                "Category",
                "Document",
            ]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
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

        self._set_busy(True)
        self.status_label.setText("Preparing import...")
        self._refresh_api_key_status()

        self.worker = ImportWorker(
            pdf_paths=[Path(path) for path in pdf_paths],
            db_path=self.db_path,
            model_name=self.model_input.text().strip() or "gpt-4o-mini",
        )
        self.worker.progress.connect(self.status_label.setText)
        self.worker.succeeded.connect(self._handle_success)
        self.worker.failed.connect(self._handle_failure)
        self.worker.start()

    def refresh_table(self) -> None:
        rows = self.database.fetch_line_items()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            values = [
                row["booking_date"],
                row["value_date"] or "",
                row["description"],
                format_amount(row["amount_cents"]),
                row["currency"],
                row["category"] or "",
                row["file_name"],
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column_index == 3:
                    item.setTextAlignment(
                        int(
                            Qt.AlignmentFlag.AlignRight
                            | Qt.AlignmentFlag.AlignVCenter
                        )
                    )
                self.table.setItem(row_index, column_index, item)

        self.table.setSortingEnabled(True)
        self.summary_label.setText(
            f"Database: {self.database.count_line_items()} imported line items"
        )

    def _handle_success(self, message: str) -> None:
        self._set_busy(False)
        self.status_label.setText(message)
        self.refresh_table()

    def _handle_failure(self, message: str) -> None:
        self._set_busy(False)
        self.status_label.setText(f"Import failed: {message}")
        QMessageBox.critical(self, "Import failed", message)

    def _set_busy(self, busy: bool) -> None:
        self.import_button.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy)
        self.model_input.setEnabled(not busy)

    def _refresh_api_key_status(self) -> None:
        if os.getenv("OPENAI_API_KEY"):
            self.api_key_label.setText("OPENAI_API_KEY detected.")
        else:
            self.api_key_label.setText(
                "OPENAI_API_KEY is missing. Import will fail until it is set."
            )

    def _get_initial_pdf_directory(self) -> Path:
        if self.settings.last_pdf_directory:
            directory = Path(self.settings.last_pdf_directory)
            if directory.is_dir():
                return directory
        return Path.home()

    def _save_last_pdf_directory(self, directory: Path) -> None:
        self.settings = AppSettings(last_pdf_directory=str(directory))
        self.settings_store.save(self.settings)


def format_amount(amount_cents: int) -> str:
    euros = amount_cents / 100
    return f"{euros:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def load_app_env() -> Path | None:
    for dotenv_path in (APP_ROOT / ".env", PACKAGE_DIR / ".env"):
        if dotenv_path.is_file():
            load_dotenv(dotenv_path)
            return dotenv_path
    return None


def main() -> None:
    load_app_env()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
