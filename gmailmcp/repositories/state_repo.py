"""Estado pequeño persistido en data/: saldos de estado de cuenta, plan, notas, recomendaciones."""
import json
import os
from datetime import date

from gmailmcp.repositories.files import read_json, write_json_atomic, write_text_atomic
from gmailmcp.repositories.settings_repo import JsonSettingsRepository


class JsonBalanceRepository:
    def __init__(self, settings_repo: JsonSettingsRepository):
        self._settings_repo = settings_repo

    @property
    def path(self) -> str:
        return os.path.join(self._settings_repo.load()['paths']['data_dir'], 'balances.json')

    def load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        try:
            return read_json(self.path)
        except json.JSONDecodeError:
            return {}

    def save_statement_balance(self, record: dict, today: date) -> dict | None:
        """Guarda el saldo de un estado de cuenta si es igual o más reciente que el guardado."""
        saldo = record.get('saldo', '')
        if not saldo:
            return None
        try:
            saldo_float = float(str(saldo).replace(',', ''))
        except ValueError:
            return None
        balances = self.load()
        banco = record.get('banco', 'Desconocido')
        tarjeta = record.get('tarjeta_ultimos4', 'xxxx')
        key = f"{banco}_{tarjeta}"
        fecha = record.get('fecha_iso', today.isoformat())
        if balances.get(key, {}).get('fecha', '') > fecha:
            return None
        balances[key] = {
            'banco': banco, 'tarjeta_ultimos4': tarjeta,
            'saldo_estado_cuenta': saldo_float, 'fecha': fecha,
            'message_id': record.get('message_id', '')
        }
        write_json_atomic(self.path, balances)
        return balances[key]


class JsonPlanRepository:
    def __init__(self, path: str = 'data/payment_plan.json'):
        self.path = path

    def exists(self) -> bool:
        return os.path.exists(self.path)

    def load(self) -> dict:
        return read_json(self.path)

    def save(self, plan: dict) -> None:
        write_json_atomic(self.path, plan)


class TextNotesRepository:
    def __init__(self, path: str = 'data/notas.txt'):
        self.path = path

    def load(self) -> str:
        if not os.path.exists(self.path):
            return ''
        with open(self.path, encoding='utf-8') as f:
            return f.read()

    def save(self, text: str) -> None:
        write_text_atomic(self.path, text)


class JsonRecommendationsRepository:
    def __init__(self, path: str = 'data/recomendaciones.json'):
        self.path = path

    def load(self) -> list:
        if not os.path.exists(self.path):
            return []
        return read_json(self.path)


class LogDirectory:
    def __init__(self, path: str = 'logs'):
        self.path = path

    def files(self) -> list[str] | None:
        if not os.path.exists(self.path):
            return None
        return sorted(os.listdir(self.path), reverse=True)

    def read(self, name: str) -> str:
        """Solo lee nombres que existen en el directorio (sin rutas relativas)."""
        if name not in (self.files() or []):
            return ''
        with open(os.path.join(self.path, name), encoding='utf-8') as f:
            return f.read()
