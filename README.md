# gmail-mcp

Automatización de Gmail y finanzas personales: limpia spam, etiqueta el inbox, extrae
movimientos de las alertas de BAC, Cuscatlán y Agrícola, y los muestra en un dashboard con
plan de pagos y resumen diario por correo. Corre en Railway (`python orchestrator.py`).

## Estructura

```
gmailmcp/
├── config.py          # entorno DEV/PROD desde variables de entorno
├── container.py       # composition root: arma cada servicio con sus dependencias
├── gmail/             # puertos (interfaces), cliente real, cliente dry-run, OAuth, reintentos
├── parsers/           # un parser por banco + registro (correos y PDFs)
├── classification.py  # reglas por banco para asignar cuenta destino
├── repositories/      # settings.json, CSV de transacciones, saldos, plan, notas, logs
├── services/          # cleanup, labeler, extractor, plan de pagos, resumen, vistas del dashboard
├── notifications/     # HTML de los correos y envío
├── web/               # create_app(), blueprints, plantillas, login, errores
├── jobs.py            # jobs ejecutables: python -m gmailmcp.jobs <job>
└── scheduler.py       # proceso de producción
orchestrator.py        # entrada de Railway
dashboard.py           # dashboard solo, para desarrollo
main.py                # servidor MCP (stdio)
```

## Desarrollo

```bash
uv sync                      # Python 3.11, igual que producción
cp .env.example .env         # y completa los valores
uv run pytest
uv run ruff check .
uv run --env-file .env python dashboard.py
```

En desarrollo (`APP_ENV=development`) el modo dry-run está activo por defecto: se lee Gmail
pero no se etiqueta, borra ni envía nada.

Flujo de ramas, versiones y despliegue: [CONTRIBUTING.md](CONTRIBUTING.md). Cambios: [CHANGELOG.md](CHANGELOG.md).
