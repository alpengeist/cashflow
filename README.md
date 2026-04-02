# Cashflow

Simple desktop app to import ING Girokonto PDFs into SQLite.

## Suggestion

Keep the first version intentionally small:

- `PySide6` desktop UI
- `SQLite` database in the project root
- `OpenAI Responses API` with direct PDF file input
- structured output parsing into line items plus a first category guess

The importer sends each PDF as base64 file content in the request. That lets the model use both the PDF text and page images while extracting line items.

## Database schema

- `documents`: one row per imported PDF
- `line_items`: one row per transaction

That is enough for import, review, and later recategorization.

## Setup

```powershell
uv sync
uv run cashflow
```

The app reads OpenAI settings from `~/.cashflow/settings.toml`.

Example `settings.toml`:

```toml
[recent]
last_pdf_directory = "C:\\Users\\hermann\\Documents\\ING"

[openai]
api_key = "your_api_key_here"
model = "gpt-4o-mini"
categorization_rules = "If description contains \"spotify\", categorize as \"entertainment\"."
```

The app stores its database in `cashflow.db`.

Notes:

- PDF file inputs use more tokens than plain text extraction because the model receives both extracted text and page images.
- Each PDF must be smaller than 50 MB, and total file input per request is limited to 50 MB.

## Next step after this

Once you have a few real ING PDFs imported, the next useful improvement is an ING-specific validation pass that checks dates, signs, and duplicate detection before saving transactions.
