from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFontMetrics, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QButtonGroup, QSizePolicy
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .database import Database
from .formatting import format_amount


@dataclass(frozen=True, slots=True)
class ChartRow:
    category: str
    amount_cents: int


class HorizontalBarChartWidget(QWidget):
    category_selected = Signal(int)
    EMPTY_HEIGHT = 220
    TOP_MARGIN = 10
    BOTTOM_MARGIN = 10
    ROW_HEIGHT = 34
    ROW_GAP = 10
    BAR_HEIGHT = 20

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[ChartRow] = []
        self.bar_color = QColor("#2f855a")
        self.empty_message = "No data available."
        self.setFixedHeight(self.EMPTY_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor("#ffffff"))
        self.setPalette(palette)

    def set_data(self, rows: list[ChartRow], color: str) -> None:
        self.rows = rows
        self.bar_color = QColor(color)
        self.setFixedHeight(self._content_height())
        parent = self.parentWidget()
        if parent is not None:
            parent.setFixedHeight(self.height() + 84)
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        row_index = self._row_index_at(event.position().y())
        if row_index is not None:
            self.category_selected.emit(row_index)
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(12, 12, -12, -12)
        if not self.rows:
            painter.setPen(self.palette().color(self.foregroundRole()))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.empty_message)
            return

        metrics = QFontMetrics(self.font())
        label_width = max(metrics.horizontalAdvance(row.category) for row in self.rows)
        value_label_width = max(
            metrics.horizontalAdvance(format_amount(row.amount_cents))
            for row in self.rows
        )

        chart_left = rect.left() + label_width + 18
        chart_right = rect.right() - value_label_width - 16
        chart_width = max(80, chart_right - chart_left)
        max_value = max(row.amount_cents for row in self.rows)
        text_color = self.palette().color(self.foregroundRole())
        guide_pen = QPen(QColor("#d7dde5"))
        bar_pen = QPen(Qt.PenStyle.NoPen)

        for index, row in enumerate(self.rows):
            row_top = rect.top() + self.TOP_MARGIN + index * (self.ROW_HEIGHT + self.ROW_GAP)
            row_center_y = row_top + self.ROW_HEIGHT / 2
            label_rect = QRectF(rect.left(), row_top, label_width, self.ROW_HEIGHT)
            bar_background_rect = QRectF(
                chart_left,
                row_center_y - self.BAR_HEIGHT / 2,
                chart_width,
                self.BAR_HEIGHT,
            )
            bar_ratio = 0 if max_value == 0 else row.amount_cents / max_value
            bar_rect = QRectF(
                chart_left,
                row_center_y - self.BAR_HEIGHT / 2,
                max(1.0, chart_width * bar_ratio),
                self.BAR_HEIGHT,
            )
            value_rect = QRectF(
                chart_right + 8,
                row_top,
                value_label_width + 8,
                self.ROW_HEIGHT,
            )

            painter.setPen(text_color)
            painter.drawText(
                label_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                row.category,
            )

            painter.setPen(guide_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(bar_background_rect, 4, 4)

            painter.setPen(bar_pen)
            painter.setBrush(self.bar_color)
            painter.drawRoundedRect(bar_rect, 4, 4)

            painter.setPen(text_color)
            painter.drawText(
                value_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                format_amount(row.amount_cents),
            )

    def _row_index_at(self, y_pos: float) -> int | None:
        if not self.rows:
            return None

        rect = self.rect().adjusted(12, 12, -12, -12)
        chart_top = rect.top() + self.TOP_MARGIN
        chart_bottom = chart_top + len(self.rows) * self.ROW_HEIGHT + max(0, len(self.rows) - 1) * self.ROW_GAP
        if y_pos < chart_top or y_pos > chart_bottom:
            return None

        relative_y = y_pos - chart_top
        slot_height = self.ROW_HEIGHT + self.ROW_GAP
        index = int(relative_y / slot_height)
        within_row = relative_y - index * slot_height
        if within_row > self.ROW_HEIGHT:
            return None
        if 0 <= index < len(self.rows):
            return index
        return None

    def _content_height(self) -> int:
        if not self.rows:
            return self.EMPTY_HEIGHT
        return (
            self.TOP_MARGIN
            + self.BOTTOM_MARGIN
            + len(self.rows) * self.ROW_HEIGHT
            + max(0, len(self.rows) - 1) * self.ROW_GAP
            + 24
        )


class InOutReportTab(QWidget):
    DOCUMENT_COLUMN = 4

    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        self.selected_flow: str | None = None
        self.selected_category: str | None = None
        self.current_inflow_categories: list[str] = []
        self.current_outflow_categories: list[str] = []
        self.report_mode = "total"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        layout.addLayout(controls)

        controls.addWidget(QLabel("Year"))
        self.year_selector = QComboBox()
        self.year_selector.currentIndexChanged.connect(self.refresh_report)
        controls.addWidget(self.year_selector)

        self.mode_buttons = QButtonGroup(self)
        self.mode_buttons.setExclusive(True)

        self.total_button = QPushButton("Total")
        self.total_button.setCheckable(True)
        self.total_button.setChecked(True)
        self.mode_buttons.addButton(self.total_button)
        controls.addWidget(self.total_button)

        self.average_button = QPushButton("Avg / Month")
        self.average_button.setCheckable(True)
        self.mode_buttons.addButton(self.average_button)
        controls.addWidget(self.average_button)

        self.mode_buttons.buttonClicked.connect(self._handle_mode_changed)
        controls.addStretch(1)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, stretch=1)

        charts_scroll = QScrollArea()
        charts_scroll.setWidgetResizable(True)
        charts_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        charts_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        splitter.addWidget(charts_scroll)

        charts_container = QWidget()
        charts_container.setAutoFillBackground(True)
        charts_palette = charts_container.palette()
        charts_palette.setColor(charts_container.backgroundRole(), QColor("#ffffff"))
        charts_container.setPalette(charts_palette)
        charts_scroll.setWidget(charts_container)
        charts_layout = QHBoxLayout(charts_container)
        charts_layout.setContentsMargins(0, 0, 0, 0)
        charts_layout.setSpacing(16)

        self.inflow_total_label = QLabel("Inflows total: 0,00")
        self.inflow_chart = HorizontalBarChartWidget()
        self.inflow_chart.category_selected.connect(self._handle_inflow_click)
        inflow_panel = self._wrap_chart_panel(
            "Inflows by Category",
            self.inflow_total_label,
            self.inflow_chart,
        )
        charts_layout.addWidget(inflow_panel, 1, Qt.AlignmentFlag.AlignTop)

        self.outflow_total_label = QLabel("Outflows total: 0,00")
        self.outflow_chart = HorizontalBarChartWidget()
        self.outflow_chart.category_selected.connect(self._handle_outflow_click)
        outflow_panel = self._wrap_chart_panel(
            "Outflows by Category",
            self.outflow_total_label,
            self.outflow_chart,
        )
        charts_layout.addWidget(outflow_panel, 1, Qt.AlignmentFlag.AlignTop)

        details_container = QWidget()
        details_layout = QVBoxLayout(details_container)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(8)
        splitter.addWidget(details_container)

        self.selection_label = QLabel("Click a bar or label to show matching line items.")
        details_layout.addWidget(self.selection_label)

        self.details_table = QTableWidget(0, 5)
        self.details_table.setHorizontalHeaderLabels(
            ["Booked", "Description", "Amount", "Currency", "Document"]
        )
        details_header = self.details_table.horizontalHeader()
        details_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        details_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        details_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        details_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        details_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.details_table.setAlternatingRowColors(True)
        self.details_table.cellClicked.connect(self._handle_details_table_click)
        details_layout.addWidget(self.details_table, stretch=1)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([420, 260])

        self.refresh_years()

    def refresh_years(self) -> None:
        years = self.database.fetch_available_years()
        current_year = self.current_year()

        self.year_selector.blockSignals(True)
        self.year_selector.clear()
        for year in years:
            self.year_selector.addItem(str(year), year)
        self.year_selector.blockSignals(False)

        if not years:
            self._clear_report()
            return

        if current_year in years:
            self.year_selector.setCurrentIndex(years.index(current_year))
        else:
            self.year_selector.setCurrentIndex(0)
        self.refresh_report()

    def refresh_report(self) -> None:
        year = self.current_year()
        if year is None:
            self._clear_report()
            return

        active_month_count = max(1, self.database.fetch_active_month_count(year))
        inflows = self.database.fetch_category_totals(year, inflow=True)
        outflows = self.database.fetch_category_totals(year, inflow=False)

        inflow_rows = [
            ChartRow(
                category=row["category"],
                amount_cents=self._display_amount_cents(
                    int(row["total_amount_cents"]),
                    active_month_count,
                ),
            )
            for row in inflows
        ]
        outflow_rows = [
            ChartRow(
                category=row["category"],
                amount_cents=self._display_amount_cents(
                    int(row["total_amount_cents"]),
                    active_month_count,
                ),
            )
            for row in outflows
        ]

        self.current_inflow_categories = [row.category for row in inflow_rows]
        self.current_outflow_categories = [row.category for row in outflow_rows]

        self.inflow_chart.set_data(inflow_rows, "#2f855a")
        self.outflow_chart.set_data(outflow_rows, "#c05621")

        mode_suffix = self._mode_title_suffix()
        self.inflow_chart_title.setText(f"Inflows by Category ({mode_suffix})")
        self.outflow_chart_title.setText(f"Outflows by Category ({mode_suffix})")
        self.inflow_total_label.setText(
            f"{self._flow_label('Inflows')}: {format_amount(sum(row.amount_cents for row in inflow_rows))}"
        )
        self.outflow_total_label.setText(
            f"{self._flow_label('Outflows')}: {format_amount(sum(row.amount_cents for row in outflow_rows))}"
        )

        if self.selected_flow == "inflow" and self.selected_category in self.current_inflow_categories:
            self._load_detail_rows(year, inflow=True, category=self.selected_category)
        elif self.selected_flow == "outflow" and self.selected_category in self.current_outflow_categories:
            self._load_detail_rows(year, inflow=False, category=self.selected_category)
        else:
            self.selected_flow = None
            self.selected_category = None
            self._clear_detail_rows("Click a bar or label to show matching line items.")

    def current_year(self) -> int | None:
        value = self.year_selector.currentData()
        if value is None:
            return None
        return int(value)

    def _handle_inflow_click(self, index: int) -> None:
        if index >= len(self.current_inflow_categories):
            return
        self.selected_flow = "inflow"
        self.selected_category = self.current_inflow_categories[index]
        self._load_detail_rows(self.current_year(), inflow=True, category=self.selected_category)

    def _handle_outflow_click(self, index: int) -> None:
        if index >= len(self.current_outflow_categories):
            return
        self.selected_flow = "outflow"
        self.selected_category = self.current_outflow_categories[index]
        self._load_detail_rows(self.current_year(), inflow=False, category=self.selected_category)

    def _load_detail_rows(self, year: int | None, *, inflow: bool, category: str) -> None:
        if year is None:
            self._clear_detail_rows("No year selected.")
            return

        rows = self.database.fetch_line_items_for_category(
            year,
            inflow=inflow,
            category=category,
        )
        self.details_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row["booking_date"],
                row["description"],
                format_amount(abs(row["amount_cents"])),
                row["currency"],
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
                self.details_table.setItem(row_index, column_index, item)

        flow_label = "Inflows" if inflow else "Outflows"
        self.selection_label.setText(
            f"{flow_label} in {year} for category '{category}' ({len(rows)} item(s))"
        )

    def _clear_report(self) -> None:
        self.current_inflow_categories = []
        self.current_outflow_categories = []
        mode_suffix = self._mode_title_suffix()
        self.inflow_chart_title.setText(f"Inflows by Category ({mode_suffix})")
        self.outflow_chart_title.setText(f"Outflows by Category ({mode_suffix})")
        self.inflow_total_label.setText(f"{self._flow_label('Inflows')}: 0,00")
        self.outflow_total_label.setText(f"{self._flow_label('Outflows')}: 0,00")
        self.inflow_chart.set_data([], "#2f855a")
        self.outflow_chart.set_data([], "#c05621")
        self._clear_detail_rows("No imported data available.")

    def _clear_detail_rows(self, message: str) -> None:
        self.details_table.setRowCount(0)
        self.selection_label.setText(message)

    def _handle_details_table_click(self, row: int, column: int) -> None:
        if column != self.DOCUMENT_COLUMN:
            return
        item = self.details_table.item(row, column)
        if item is None:
            return
        document_path = item.data(Qt.ItemDataRole.UserRole)
        if not document_path:
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(document_path))):
            self.selection_label.setText(f"Could not open document: {document_path}")

    def _wrap_chart_panel(
        self,
        title_text: str,
        total_label: QLabel,
        chart_widget: HorizontalBarChartWidget,
    ) -> QWidget:
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.NoFrame)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        panel.setStyleSheet("background: #ffffff; border: none;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel(title_text)
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)
        layout.addWidget(total_label)
        layout.addWidget(chart_widget)
        panel.setFixedHeight(chart_widget.height() + 84)
        if "Inflows" in title_text:
            self.inflow_chart_title = title
        else:
            self.outflow_chart_title = title
        return panel

    def _handle_mode_changed(self) -> None:
        self.report_mode = "average" if self.average_button.isChecked() else "total"
        self.refresh_report()

    def _display_amount_cents(self, total_amount_cents: int, month_count: int) -> int:
        if self.report_mode == "average":
            return round(total_amount_cents / month_count)
        return total_amount_cents

    def _mode_title_suffix(self) -> str:
        return "Average Monthly" if self.report_mode == "average" else "Total"

    def _flow_label(self, base_label: str) -> str:
        if self.report_mode == "average":
            return f"{base_label} avg / month"
        return f"{base_label} total"
