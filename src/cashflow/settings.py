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
        ]
        self.settings_path.write_text("\n".join(content), encoding="utf-8")

def _read_optional_string(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _escape_toml_string(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
