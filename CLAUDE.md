# Gmail MCP — Instrucciones para Claude Code

## Lectura obligatoria al inicio de sesión

Antes de cualquier acción financiera, leer:
1. `claude_memory.md` — estado financiero actual, reglas de negocio, pendientes
2. `config/settings.json` — fuente de datos estructurada
3. `finanzas/movimientos.csv` — historial de transacciones

## Reglas de actualización

- **Saldo real**: actualizar solo con confirmación de app / Gmail / usuario explícito
- **Saldo estimado**: marcar siempre con `~` y la fecha del cálculo
- **claude_memory.md**: actualizar siempre que haya un movimiento confirmado o corrección
- **Commit**: después de cada actualización financiera, hacer commit descriptivo y push a `main`

## Estructura del proyecto

```
config/settings.json       → datos financieros estructurados (tarjetas, préstamos, cuentas)
finanzas/movimientos.csv   → historial CSV de transacciones
finanzas/dashboard.py      → genera resumen + gráfico PNG
claude_memory.md           → memoria de sesión (leer siempre al inicio)
banco_de_ideas.md          → ideas pendientes de implementar
```

## Flujo de trabajo estándar

1. Leer `claude_memory.md`
2. Buscar correos nuevos con Gmail MCP (`mcp__Gmail__search_threads`)
3. Extraer movimientos confirmados
4. Actualizar `movimientos.csv` + `settings.json` + `claude_memory.md`
5. Commit y push a `main`
6. Generar prompt de resumen para Claude Chat

## Rama de despliegue

- `main` → Railway (app en producción)
- Toda actualización de datos financieros va a `main` directamente
