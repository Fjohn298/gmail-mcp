from datetime import date

import pytest

from gmailmcp import __version__
from gmailmcp.config import AppConfig, ConfigError, resolve_env
from gmailmcp.dates import add_months, next_occurrence


@pytest.mark.parametrize("day, today, expected", [
    (15, date(2026, 10, 10), date(2026, 10, 15)),   # este mes
    (10, date(2026, 10, 10), date(2026, 10, 10)),   # hoy cuenta
    (5, date(2026, 10, 10), date(2026, 11, 5)),     # ya pasó → mes siguiente
    (31, date(2026, 11, 4), date(2026, 11, 30)),    # noviembre no tiene 31
    (30, date(2027, 1, 31), date(2027, 2, 28)),     # febrero
    (5, date(2026, 12, 20), date(2027, 1, 5)),      # cambio de año
])
def test_next_occurrence(day, today, expected):
    assert next_occurrence(day, today) == expected


def test_add_months_devuelve_primer_dia_del_mes():
    assert add_months(date(2026, 11, 20), 3) == date(2027, 2, 1)


@pytest.mark.parametrize("environ, expected", [
    ({}, "development"),
    ({"APP_ENV": "production"}, "production"),
    ({"RAILWAY_ENVIRONMENT_NAME": "production"}, "production"),
    ({"RAILWAY_ENVIRONMENT_NAME": "development"}, "development"),
    ({"APP_ENV": "development", "RAILWAY_ENVIRONMENT_NAME": "production"}, "development"),
])
def test_resolucion_de_entorno(environ, expected):
    assert resolve_env(environ) == expected


def test_app_env_invalido_falla_rapido():
    with pytest.raises(ConfigError):
        resolve_env({"APP_ENV": "prod"})


def test_desarrollo_es_dry_run_por_defecto_y_produccion_no():
    assert AppConfig.from_env({}).dry_run is True
    assert AppConfig.from_env({"APP_ENV": "production"}).dry_run is False
    assert AppConfig.from_env({"DRY_RUN": "false"}).dry_run is False


def test_login_se_activa_al_definir_password():
    assert AppConfig.from_env({}).require_login is False
    assert AppConfig.from_env({"DASHBOARD_PASSWORD": "x"}).require_login is True
    assert AppConfig.from_env({"DASHBOARD_PASSWORD": "x", "REQUIRE_LOGIN": "false"}).require_login is False


def test_require_login_sin_password_falla_al_arrancar():
    with pytest.raises(ConfigError):
        AppConfig.from_env({"REQUIRE_LOGIN": "true"})


def test_produccion_avisa_si_falta_secreto_o_login():
    warnings = AppConfig.from_env({"APP_ENV": "production"}).warnings()
    assert any("FLASK_SECRET" in w for w in warnings)
    assert any("login" in w for w in warnings)


def test_version_del_paquete_coincide_con_pyproject():
    import tomllib
    from pathlib import Path
    pyproject = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == __version__
