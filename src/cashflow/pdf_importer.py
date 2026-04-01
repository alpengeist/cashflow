from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, Field

from .database import Database, StoredLineItem

MAX_PDF_BYTES = 50 * 1024 * 1024

SYSTEM_PROMPT = """You extract booked transaction line items from ING Girokonto statements.

Return every real transaction exactly once.
Ignore page headers, page footers, balances, summaries, carry-over amounts, legal text, and account metadata.
Use ISO dates in YYYY-MM-DD format.
Use signed amounts in euro cents. Money leaving the account must be negative. Money entering the account must be positive.
Use short lowercase categories like groceries, salary, rent, transport, transfer, shopping, fees, insurance, utilities, cash, taxes, health, or entertainment. Use null when unclear.
"""

USER_PROMPT = """Extract all booked transaction line items from the attached ING Girokonto PDF.

Filename: {file_name}

Return every real transaction exactly once.
"""


class ParsedLineItem(BaseModel):
    booking_date: str = Field(description="Booking date in YYYY-MM-DD format.")
    value_date: str | None = Field(
        default=None,
        description="Value date in YYYY-MM-DD format when present in the statement.",
    )
    description: str = Field(description="Clean transaction description.")
    raw_text: str | None = Field(
        default=None,
        description="Closest raw text snippet for the transaction.",
    )
    amount_cents: int = Field(
        description="Signed amount in euro cents. Expense negative, income positive."
    )
    currency: str = Field(default="EUR", description="ISO currency code.")
    category: str | None = Field(
        default=None,
        description="Short lowercase category label or null.",
    )


class ParsedStatement(BaseModel):
    line_items: list[ParsedLineItem] = Field(default_factory=list)


class PdfImportService:
    def __init__(self, db_path: Path, model_name: str) -> None:
        self.db = Database(db_path)
        self.model_name = model_name

    def import_pdf(self, pdf_path: Path) -> int:
        self.db.initialize()
        pdf_base64 = encode_pdf_base64(pdf_path)

        parsed = self._extract_line_items(
            file_name=pdf_path.name,
            pdf_base64=pdf_base64,
        )
        self.db.save_import(
            sha256=sha256sum(pdf_path),
            file_name=pdf_path.name,
            file_path=str(pdf_path.resolve()),
            source_text="Imported via Responses API input_file.",
            model_name=self.model_name,
            line_items=parsed,
        )
        return len(parsed)

    def _extract_line_items(
        self,
        *,
        file_name: str,
        pdf_base64: str,
    ) -> list[StoredLineItem]:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set.")

        client = OpenAI()
        response = client.responses.parse(
            model=self.model_name,
            instructions=SYSTEM_PROMPT,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "filename": file_name,
                            "file_data": pdf_base64,
                        },
                        {
                            "type": "input_text",
                            "text": USER_PROMPT.format(file_name=file_name),
                        },
                    ],
                },
            ],
            text_format=ParsedStatement,
        )
        parsed_statement = response.output_parsed
        if parsed_statement is None:
            raise RuntimeError("The model did not return structured line items.")

        return [
            StoredLineItem(
                sequence_no=index,
                booking_date=item.booking_date,
                value_date=item.value_date,
                description=item.description.strip(),
                raw_text=(item.raw_text or item.description).strip(),
                amount_cents=item.amount_cents,
                currency=item.currency.strip().upper() or "EUR",
                category=(item.category.strip().lower() if item.category else None),
            )
            for index, item in enumerate(parsed_statement.line_items, start=1)
        ]


def encode_pdf_base64(pdf_path: Path) -> str:
    file_size = pdf_path.stat().st_size
    if file_size > MAX_PDF_BYTES:
        size_mb = file_size / (1024 * 1024)
        raise ValueError(
            f"{pdf_path.name} is {size_mb:.1f} MB. PDF inputs must stay below 50 MB."
        )
    return base64.b64encode(pdf_path.read_bytes()).decode("ascii")


def sha256sum(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
