"""Acceso a config/settings.json."""
from gmailmcp.repositories.files import read_json, write_json_atomic


class JsonSettingsRepository:
    """Se relee en cada llamada: otro proceso (git / dashboard) puede haberlo cambiado."""

    def __init__(self, path: str = "config/settings.json"):
        self.path = path

    def load(self) -> dict:
        return read_json(self.path)

    def save(self, settings: dict) -> None:
        write_json_atomic(self.path, settings)
