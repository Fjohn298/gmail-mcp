"""Histórico de transacciones del extractor (data/financial_data.csv)."""
import csv
import io
import os

from gmailmcp.repositories.files import write_text_atomic
from gmailmcp.repositories.settings_repo import JsonSettingsRepository

CSV_COLUMNS = [
    'fecha_iso', 'banco', 'tipo', 'tarjeta_tipo', 'tarjeta_ultimos4',
    'monto', 'moneda', 'comercio', 'descripcion',
    'fuente', 'pdf_path', 'message_id', 'revisado'
]


class CsvTransactionRepository:
    def __init__(self, settings_repo: JsonSettingsRepository):
        self._settings_repo = settings_repo

    @property
    def path(self) -> str:
        return self._settings_repo.load()['paths']['financial_csv']

    def all(self) -> list[dict]:
        path = self.path
        if not os.path.exists(path):
            return []
        with open(path, encoding='utf-8') as f:
            return list(csv.DictReader(f))

    def existing_message_ids(self) -> set[str]:
        return {row.get('message_id', '') for row in self.all()}

    def append(self, records: list[dict]) -> None:
        path = self.path
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        file_exists = os.path.exists(path) and os.path.getsize(path) > 0
        with open(path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction='ignore')
            if not file_exists:
                writer.writeheader()
            writer.writerows(records)

    def replace_all(self, rows: list[dict]) -> None:
        if not rows:
            return
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        write_text_atomic(self.path, buf.getvalue())

    def stats(self) -> tuple[float | None, int]:
        """(mtime, nº de filas sin encabezado) o (None, 0) si no existe."""
        path = self.path
        if not os.path.exists(path):
            return None, 0
        with open(path, encoding='utf-8') as f:
            count = sum(1 for _ in f) - 1
        return os.path.getmtime(path), count
