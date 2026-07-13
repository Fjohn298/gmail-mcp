# 💡 Banco de Ideas

> Repositorio de ideas pendientes de desarrollo.
> **NO implementar** hasta que esté planificado. Solo agregar, priorizar y documentar.

---

## Formato de entrada

```
### Idea #NNN — DD-MMM-YYYY
**Título:** ...
**Descripción:** ...
**Requiere:** ...
**Prioridad:** Alta / Media / Baja
**Estado:** 💡 Pendiente / 🔄 En progreso / ✅ Completada / ❌ Descartada
```

---

### Idea #001 — 07-Jul-2026
**Título:** Historial de transacciones y captura de movimientos
**Descripción:** Crear CSV para registrar todos los movimientos de todas las cuentas (BAC, AMEX, NIU, efectivo) desde ene-2026 en adelante. Alimentarlo automáticamente desde Gmail y con entrada manual. Usar para análisis de patrones de gasto diario, semanal y quincenal.
**Requiere:** Definir estructura CSV, integrar con Gmail MCP, crear vista en dashboard.
**Prioridad:** Alta
**Estado:** 🔄 En progreso
**Notas de ejecución:**
- Inicio real: 13-Jul-2026
- CSV en Drive: `Finanzas/movimientos.csv` (ID Drive: `1DK9UXzkyt6i36kh-Lwy0AQwTXsaTe3-V` → migrado a carpeta Finanzas `1LXw_WHHybVhFZtSqlhmU3-yLhPCuIehl`)
- Movimientos reales Jul 10-12 extraídos de Gmail BAC/Agrícola/NIU
- Dashboard: `finanzas/dashboard.py` (pandas + matplotlib)
- Pendiente: automatización completa + DEL SUR monto + salario Jul 13 + AMEX pago

---

### Idea #002 — 09-Jul-2026
**Título:** Mapa de flujos de ingresos
**Descripción:** Explorar 7 fuentes de ingreso adicional basadas en habilidades técnicas (Python, SQL, Power BI, inglés B2). Para cada una evaluar: dificultad de inicio, coste inicial, tiempo hasta generar ingresos, riesgo y escalabilidad. Crear secuencia de implementación de 12 meses.
**Requiere:** Análisis externo + documento de plan, posible vista en dashboard.
**Prioridad:** Alta
**Estado:** 💡 Pendiente

---

### Idea #003 — 09-Jul-2026
**Título:** Presupuesto sin vergüenza
**Descripción:** Sistema de límites por categoría con alertas visuales en el dashboard cuando se acerca al tope mensual. Distribución 50/30/20 adaptada a ingresos $1,133.84. Incluir guiones para situaciones sociales (cenas, viajes, cumpleaños, planes improvisados).
**Requiere:** Definir categorías y límites, integrar con datos de gastos, crear widget de alertas.
**Prioridad:** Media
**Estado:** 💡 Pendiente

---

### Idea #004 — 09-Jul-2026
**Título:** Sistema de ahorro automático por objetivos
**Descripción:** Configurar metas de ahorro en el dashboard (fondo emergencia, hipoteca 2027, viaje) con progreso visual y transferencias automáticas sugeridas desde MultiMoney. Jerarquía: emergencia → hipoteca → otros. Base actual: $77.67 libre en MultiMoney al 3.5% anual.
**Requiere:** Estructura de metas en settings.json, widget de progreso, integración con fondos_ahorro.
**Prioridad:** Alta
**Estado:** 💡 Pendiente

---

### Idea #005 — 09-Jul-2026
**Título:** Validador de trabajo secundario
**Descripción:** Matriz de evaluación de ideas de ingreso extra basadas en habilidades disponibles (Python, SQL, Power BI, SAP, Crystal Reports, inglés B2, ~10 horas/semana, presupuesto inicial $0). Candidatos: freelance de datos/BI, consultoría, tutorías técnicas, automatización para PYMEs, contenido sobre finanzas. Plan de lanzamiento 30 días para el primero.
**Requiere:** Análisis y scoring, posible vista comparativa en dashboard.
**Prioridad:** Alta
**Estado:** 💡 Pendiente
