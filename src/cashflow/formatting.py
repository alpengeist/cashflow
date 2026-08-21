from __future__ import annotations

from datetime import datetime


def format_amount(amount_cents: int) -> str:
    euros = amount_cents / 100
    return f"{euros:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def format_local_datetime(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value
