from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


SETTINGS_DIR = Path.home() / ".cashflow"
SETTINGS_PATH = SETTINGS_DIR / "settings.toml"


@dataclass(slots=True)
class AppSettings:
    last_pdf_directory: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None
    categorization_rules: str | None = None
    excluded_outflow_categories: tuple[str, ...] = ()


class SettingsStore:
    def __init__(self, settings_path: Path = SETTINGS_PATH) -> None:
        self.settings_path = settings_path

    def load(self) -> AppSettings:
        if not self.settings_path.is_file():
            return AppSettings()

        try:
            with self.settings_path.open("rb") as handle:
                data = tomllib.load(handle)
        except tomllib.TOMLDecodeError:
            return AppSettings()

        recent = data.get("recent", {})
        openai = data.get("openai", {})
        report = data.get("report", {})
        return AppSettings(
            last_pdf_directory=_read_optional_string(
                recent,
                "last_pdf_directory",
            ),
            openai_api_key=_read_optional_string(openai, "api_key"),
            openai_model=_read_optional_string(openai, "model"),
            categorization_rules=_read_optional_string(
                openai,
                "categorization_rules",
            ),
            excluded_outflow_categories=_read_optional_string_list(
                report,
                "excluded_outflow_categories",
            ),
        )

    def save(self, settings: AppSettings) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        content = [
            "[recent]",
            f'last_pdf_directory = "{_escape_toml_string(settings.last_pdf_directory or "")}"',
            "",
            "[openai]",
            f'api_key = "{_escape_toml_string(settings.openai_api_key or "")}"',
            f'model = "{_escape_toml_string(settings.openai_model or "")}"',
            f'categorization_rules = "{_escape_toml_string(settings.categorization_rules or "")}"',
            "",
            "[report]",
            f"excluded_outflow_categories = {_format_toml_string_array(settings.excluded_outflow_categories)}",
            "",
        ]
        self.settings_path.write_text("\n".join(content), encoding="utf-8")

def _read_optional_string(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _read_optional_string_list(
    data: dict[str, object],
    key: str,
) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list):
        return ()

    cleaned_values: list[str] = []
    seen_values: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        normalized_item = item.strip()
        if not normalized_item or normalized_item in seen_values:
            continue
        cleaned_values.append(normalized_item)
        seen_values.add(normalized_item)
    return tuple(cleaned_values)


def _escape_toml_string(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )


def _format_toml_string_array(values: tuple[str, ...]) -> str:
    if not values:
        return "[]"
    escaped_values = ", ".join(f'"{_escape_toml_string(value)}"' for value in values)
    return f"[{escaped_values}]"
