# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Versionado: [SemVer](https://semver.org/lang/es/) — `MAYOR.MENOR.PARCHE`.

## [Unreleased]

## [0.2.0] — 2026-11-04

### Cambiado
- Código reorganizado en el paquete `gmailmcp/` por capas (gmail, parsers, repositorios,
  servicios, notificaciones, web) aplicando SOLID. `orchestrator.py`, `dashboard.py` y `main.py`
  quedan como puntos de entrada finos; Railway arranca igual (`python orchestrator.py`).
- Dashboard con application factory (`gmailmcp.web:create_app`) y blueprints; HTML movido a
  `gmailmcp/web/templates/`.
- Errores de la API centralizados: en producción responden `{"error": "error interno"}` y el
  detalle va al log; en desarrollo se muestra el mensaje.
- Escrituras de `settings.json`, `balances.json`, el plan y las notas son atómicas.
- `/health` incluye `version` y `env`.

### Añadido
- Configuración por entorno (`APP_ENV`, `DRY_RUN`, `REQUIRE_LOGIN`), ver `.env.example`.
- Modo dry-run (por defecto en development): lee Gmail pero no etiqueta, borra ni envía.
- Login opcional del dashboard: se activa al definir `DASHBOARD_PASSWORD`. `/health` y
  `/memory` siguen públicos.
- Jobs ejecutables a mano: `python -m gmailmcp.jobs <job>` (salida ≠ 0 si fallan).
- Tests (`pytest`), lint (`ruff`) y CI en GitHub Actions.

### Corregido
- `cleanup` entraba en bucle infinito si un hilo de spam tenía una etiqueta protegida, lo que
  detenía todos los jobs programados.
- `/api/plan/financiamientos` respondía 500: exigía `fecha_corte`, que ningún
  intrafinanciamiento tiene.
- El saldo de los estados de cuenta de Banco Agrícola no se extraía con el formato
  `Saldo actual: $1,133.25`.
- `settings.json` se abría sin `encoding` (fallaba en Windows) y faltaba `tzdata` para
  `ZoneInfo` en Windows.
- Días de pago inexistentes en el mes (31 en noviembre) ya no dan error: se usa el último día.

### Eliminado
- `labels.py` (versión antigua del labeler que entraba en un bucle infinito al importarse).
- Contraseña y `SECRET_KEY` por defecto escritas en el código.

## [0.1.1] — 2026-11-04

### Seguridad
- `/logs?f=../archivo` permitía leer cualquier archivo del servidor (incluido el token OAuth).
