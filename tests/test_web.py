from dataclasses import replace

import pytest

from gmailmcp.container import Container
from gmailmcp.web import create_app
from tests.conftest import make_config

PAGES = ["/", "/finanzas", "/emails", "/plan", "/deudas", "/fugas", "/logs", "/health", "/memory"]
APIS = ["/api/status", "/api/transactions", "/api/plan", "/api/plan/fondos", "/api/plan/financiamientos",
        "/api/balances", "/api/emails/recent", "/api/emails/unlabeled", "/api/emails/financial",
        "/api/emails/label-stats", "/api/plan/activity", "/api/cuenta", "/api/calendario_pagos",
        "/api/tarjetas/calendario", "/api/plan/snapshot", "/api/plan/quincenal",
        "/api/plan/fondos_esporadicos", "/api/plan/gastos_fijos_amex", "/api/amex/historial",
        "/api/recomendaciones", "/api/otras_cuentas", "/api/deudas/estrategias", "/api/fugas",
        "/api/notas", "/api/efectivo", "/api/presupuesto_bac"]


@pytest.fixture
def client(container):
    return create_app(container).test_client()


@pytest.mark.parametrize("path", PAGES + APIS)
def test_todas_las_rutas_responden(client, path):
    assert client.get(path).status_code == 200


def test_financiamientos_sin_fecha_corte_ya_no_da_500(client):
    item = client.get("/api/plan/financiamientos").get_json()["items"][0]
    assert item["payoff_label"] == "Ago 2027"
    assert item["progress_pct"] == 17


def test_logs_no_permite_leer_archivos_fuera_de_logs(client, workdir):
    (workdir / "token.json").write_text("SECRETO", encoding="utf-8")
    assert "SECRETO" not in client.get("/logs?f=../token.json").get_data(as_text=True)


def test_notas_se_guardan_y_se_leen(client):
    client.post("/api/notas", json={"texto": "  hola  "})
    assert client.get("/api/notas").get_json() == {"texto": "hola"}


def test_confirmar_movimiento_ajusta_saldo_de_tarjeta(client, container):
    r = client.post("/api/plan/activity/confirm", json={"last4": "1111", "delta": -50})
    assert r.get_json() == {"ok": True, "name": "Tarjeta A", "new_balance": 250.0}
    assert client.post("/api/plan/activity/confirm", json={"last4": "9999", "delta": 1}).status_code == 404


def _app(workdir, gmail, **env):
    config = replace(make_config(**env), memory_path=workdir / "memory.md")
    return create_app(Container(config, gmail_service_factory=lambda logger: gmail))


def test_en_produccion_los_errores_no_filtran_detalles(workdir, gmail):
    (workdir / "config" / "settings.json").write_text("{roto", encoding="utf-8")
    client = _app(workdir, gmail, APP_ENV="production").test_client()
    r = client.get("/api/cuenta")
    assert r.status_code == 500 and r.get_json() == {"error": "error interno"}


def test_login_protege_dashboard_y_api_pero_no_health_ni_memory(workdir, gmail):
    client = _app(workdir, gmail, DASHBOARD_PASSWORD="clave").test_client()
    assert client.get("/finanzas").status_code == 302
    assert client.get("/api/transactions").status_code == 401
    assert client.get("/health").status_code == 200
    assert client.get("/memory").status_code == 200

    assert client.post("/login", data={"password": "mala"}).status_code == 200
    r = client.post("/login?next=/finanzas", data={"password": "clave"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/finanzas")
    assert client.get("/api/transactions").status_code == 200


def test_login_no_redirige_a_dominios_externos(workdir, gmail):
    client = _app(workdir, gmail, DASHBOARD_PASSWORD="clave").test_client()
    r = client.post("/login?next=//malicioso.com", data={"password": "clave"})
    assert r.headers["Location"] == "/"
