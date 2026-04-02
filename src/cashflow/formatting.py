from __future__ import annotations


def format_amount(amount_cents: int) -> str:
    euros = amount_cents / 100
    return f"{euros:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
