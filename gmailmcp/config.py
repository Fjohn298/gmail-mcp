"""Configuración de runtime por entorno (development / production).

Todo lo que cambia entre DEV y PROD sale de variables de entorno, nunca del código.
La configuración de negocio (horarios, saldos, reglas) sigue en config/settings.json.
"""
from __future__ import annotations

import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEVELOPMENT = "development"
PRODUCTION = "production"


class ConfigError(Exception):
    """La configuración del entorno es inválida o incompleta."""


def _env_bool(raw: str | None, default: bool) -> bool:
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on", "si", "sí"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"valor booleano inválido: {raw!r}")


def resolve_env(environ: Mapping[str, str]) -> str:
    """APP_ENV manda; si falta, se deduce del entorno de Railway; si no, development."""
    explicit = environ.get("APP_ENV", "").strip().lower()
    if explicit:
        if explicit not in {DEVELOPMENT, PRODUCTION}:
            raise ConfigError(f"APP_ENV debe ser '{DEVELOPMENT}' o '{PRODUCTION}', no {explicit!r}")
        return explicit
    railway_env = (environ.get("RAILWAY_ENVIRONMENT_NAME") or environ.get("RAILWAY_ENVIRONMENT") or "").lower()
    if railway_env:
        return PRODUCTION if railway_env == PRODUCTION else DEVELOPMENT
    return DEVELOPMENT


@dataclass(frozen=True)
class AppConfig:
    env: str
    dry_run: bool
    flask_secret: str
    flask_secret_is_ephemeral: bool
    dashboard_password: str | None
    require_login: bool
    port: int = 5000
    public_domain: str = ""
    gmail_token_json: str | None = None
    gmail_credentials_json: str | None = None
    settings_path: str = "config/settings.json"
    memory_path: Path = field(default=PROJECT_ROOT / "claude_memory.md")

    @property
    def is_production(self) -> bool:
        return self.env == PRODUCTION

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> AppConfig:
        e = os.environ if environ is None else environ
        env = resolve_env(e)

        secret = e.get("FLASK_SECRET", "").strip()
        ephemeral = not secret
        if ephemeral:
            # Sin FLASK_SECRET las sesiones no sobreviven reinicios; se avisa al arrancar.
            secret = secrets.token_hex(32)

        password = e.get("DASHBOARD_PASSWORD", "").strip() or None
        require_login = _env_bool(e.get("REQUIRE_LOGIN"), default=password is not None)
        if require_login and not password:
            raise ConfigError("REQUIRE_LOGIN está activo pero falta DASHBOARD_PASSWORD")

        return cls(
            env=env,
            # En DEV no se tocan correos reales salvo que se pida explícitamente DRY_RUN=false.
            dry_run=_env_bool(e.get("DRY_RUN"), default=env != PRODUCTION),
            flask_secret=secret,
            flask_secret_is_ephemeral=ephemeral,
            dashboard_password=password,
            require_login=require_login,
            port=int(e.get("PORT", "5000")),
            public_domain=e.get("RAILWAY_PUBLIC_DOMAIN", ""),
            gmail_token_json=e.get("GMAIL_TOKEN_JSON") or None,
            gmail_credentials_json=e.get("GMAIL_CREDENTIALS_JSON") or None,
            settings_path=e.get("SETTINGS_PATH", "config/settings.json"),
        )

    def warnings(self) -> list[str]:
        out = []
        if self.flask_secret_is_ephemeral:
            out.append("FLASK_SECRET no está definido: se usa una clave temporal por proceso")
        if self.is_production and not self.require_login:
            out.append("Dashboard sin login en producción: define DASHBOARD_PASSWORD")
        if self.is_production and self.dry_run:
            out.append("DRY_RUN activo en producción: no se modificarán ni enviarán correos")
        return out
