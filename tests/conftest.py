"""Entorno de test aislado: carpeta temporal con config sintética (sin datos reales)."""
import json

import pytest

from gmailmcp.config import AppConfig
from gmailmcp.container import Container
from tests.fakes import FakeGmailService

SETTINGS = {
    "auth": {"token_file": "token.json", "credentials_file": "credentials.json",
             "scopes": ["https://www.googleapis.com/auth/gmail.modify"]},
    "schedule": {"cleanup_interval_hours": 1, "labeler_interval_hours": 1,
                 "financial_extractor_time": "08:00", "planner_time": "07:00", "daily_summary_time": "14:00"},
    "planner": {
        "salary_per_period": 500.0, "savings_percentage": 0.10, "run_days": [13, 28],
        "notify_email": "yo@example.com",
        "cards": [
            {"name": "Tarjeta A", "last4": "1111", "balance": 300.0, "tasa_anual": 40.0,
             "fecha_pago_dia": 10, "fecha_corte_dia": 18, "min_pago": 30.0},
            {"name": "Tarjeta B", "last4": "2222", "balance": 100.0, "tasa_anual": 30.0,
             "fecha_pago_dia": 3, "fecha_corte_dia": 9, "min_pago": 20.0},
        ],
        "obligaciones_extra": [{"descripcion": "Universidad", "monto_mensual": 80.0, "fecha_pago_dia": 1}],
    },
    "prestamos": [{"nombre": "Préstamo X", "numero": "1", "saldo": 1000.0, "cuota_mensual": 50.0,
                   "tasa_anual": 15.0, "fecha_pago_dia": 7}],
    "fondos_ahorro": [{"nombre": "Mi Ahorro MultiMoney", "saldo": 200.0, "tasa_anual": 3.5,
                       "deposito_quincena": 50.0, "dias_deposito": [15, 30]}],
    "intrafinanciamientos": [{"ref": "R1", "descripcion": "Laptop 0%", "cuota_mensual": 20.0,
                              "saldo_actual": 200.0, "cuotas_pagadas": 2, "cuotas_total": 12,
                              "tasa_mensual": 0.0, "fecha_fin": "2027-08-10", "fecha_pago_dia": 10}],
    "otras_cuentas": [{"nombre": "Débito BAC", "saldo": 150.0, "movimientos": [
        {"fecha": "2026-10-01", "monto": 10.0, "tipo": "egreso"},
        {"fecha": "2026-10-02", "monto": 5.0, "tipo": "egreso"}],
        "presupuesto": {"fecha_inicio": "2026-10-01", "fecha_fin": "2026-10-11", "saldo_inicio": 100.0,
                        "dias_total": 10}}],
    "paths": {"data_dir": "data", "spam_senders_file": "config/spam_senders.txt",
              "label_rules_file": "config/label_rules.json", "financial_csv": "data/financial_data.csv"},
    "gmail": {"page_size": 2, "rate_limit_retries": 3, "rate_limit_wait_seconds": 0,
              "protected_labels": ["Label_3"]},
}

LABEL_RULES = {
    "recibos": {"_label_id": "Label_3", "senders": ["alertas@baccredomatic.com"]},
    "cursos": {"_label_id": "Label_2", "senders": ["datacamp.com"]},
}


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.json").write_text(json.dumps(SETTINGS), encoding="utf-8")
    (tmp_path / "config" / "label_rules.json").write_text(json.dumps(LABEL_RULES), encoding="utf-8")
    (tmp_path / "config" / "spam_senders.txt").write_text("# spam\nspam.com\n", encoding="utf-8")
    (tmp_path / "memory.md").write_text("# memoria", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def make_config(**overrides) -> AppConfig:
    env = {"APP_ENV": "development", "DRY_RUN": "false", "FLASK_SECRET": "test"}
    env.update(overrides)
    return AppConfig.from_env(env)


@pytest.fixture
def gmail():
    return FakeGmailService()


@pytest.fixture
def container(workdir, gmail):
    from dataclasses import replace
    config = replace(make_config(), memory_path=workdir / "memory.md")
    return Container(config, gmail_service_factory=lambda logger: gmail)
