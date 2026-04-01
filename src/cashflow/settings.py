from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


SETTINGS_DIR = Path.home() / ".cashflow"
SETTINGS_PATH = SETTINGS_DIR / "settings.toml"


@dataclass(slots=True)
class AppSettings:
    last_pdf_directory: str | None = None


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
        last_pdf_directory = recent.get("last_pdf_directory")
        if not isinstance(last_pdf_directory, str) or not last_pdf_directory.strip():
            return AppSettings()

        return AppSettings(last_pdf_directory=last_pdf_directory)

    def save(self, settings: AppSettings) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        content = [
            "[recent]",
            f'last_pdf_directory = "{_escape_toml_string(settings.last_pdf_directory or "")}"',
            "",
        ]
        self.settings_path.write_text("\n".join(content), encoding="utf-8")


def _escape_toml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
