"""Vistas de solo lectura sobre settings.json para el dashboard (funciones puras)."""
from datetime import date

from gmailmcp.dates import add_months, month_label


def savings_and_loans(settings: dict) -> dict:
    fondos = []
    for f in settings.get('fondos_ahorro', []):
        fondos.append({**f, 'ganancia_mensual': round(f['saldo'] * f['tasa_anual'] / 100 / 12, 2),
                       'ganancia_anual': round(f['saldo'] * f['tasa_anual'] / 100, 2)})
    prestamos = [{**p, 'cuota_quincenal': round(p['cuota_mensual'] / 2, 2)}
                 for p in settings.get('prestamos', [])]
    return {'fondos': fondos, 'prestamos': prestamos}


def _financing_payoff(item: dict, cuotas_restantes: int, today: date) -> str:
    """Mes de la última cuota: desde fecha_corte; si falta, fecha_fin; si falta, desde hoy.

    Antes se exigía fecha_corte y ningún intrafinanciamiento la tiene (la ruta daba 500).
    """
    if item.get('fecha_corte'):
        return month_label(add_months(date.fromisoformat(item['fecha_corte']), cuotas_restantes))
    if item.get('fecha_fin'):
        return month_label(date.fromisoformat(item['fecha_fin']))
    return month_label(add_months(today, cuotas_restantes))


def financing_overview(settings: dict, today: date) -> dict:
    result = []
    for item in settings.get('intrafinanciamientos', []):
        cuotas_restantes = item['cuotas_total'] - item['cuotas_pagadas']
        result.append({**item, 'cuotas_restantes': cuotas_restantes,
                       'payoff_label': _financing_payoff(item, cuotas_restantes, today),
                       'progress_pct': round(item['cuotas_pagadas'] / item['cuotas_total'] * 100)})
    return {'items': result,
            'total_saldo': round(sum(i['saldo_actual'] for i in result), 2),
            'total_cuota': round(sum(i['cuota_mensual'] for i in result), 2)}


def cash_flow(settings: dict) -> dict:
    cuenta = settings.get('cuenta_corriente', {})
    saldo = cuenta.get('saldo', 0)
    planner = settings.get('planner', {})
    salary_per_period = planner.get('salary_per_period', 0)
    ingreso_mensual = round(salary_per_period * 2, 2)

    oblig_tarjetas = round(sum(c.get('min_pago', 0) for c in planner.get('cards', [])), 2)
    oblig_fi = round(sum(i.get('cuota_mensual', 0) for i in settings.get('intrafinanciamientos', [])), 2)
    oblig_prestamos = round(sum(p.get('cuota_mensual', 0) for p in settings.get('prestamos', [])), 2)
    oblig_extra = round(sum(e.get('monto_mensual', 0) for e in planner.get('obligaciones_extra', [])), 2)
    obligaciones_mes = round(oblig_tarjetas + oblig_fi + oblig_prestamos + oblig_extra, 2)
    multimoney_mes = round(sum(f.get('deposito_quincena', 0) * 2
                               for f in settings.get('fondos_ahorro', []) if f.get('deposito_quincena')), 2)
    return {
        'saldo': saldo,
        'banco': cuenta.get('banco', ''),
        'movimientos': list(reversed(cuenta.get('movimientos', []))),
        'salary_per_period': salary_per_period,
        'ingreso_mensual': ingreso_mensual,
        'obligaciones_mes': obligaciones_mes,
        'oblig_tarjetas': oblig_tarjetas,
        'oblig_fi': oblig_fi,
        'oblig_prestamos': oblig_prestamos,
        'oblig_extra': oblig_extra,
        'multimoney_mes': multimoney_mes,
        'remanente_mes': round(ingreso_mensual - obligaciones_mes - multimoney_mes, 2),
        'proyectado': round(saldo + ingreso_mensual - obligaciones_mes, 2),
    }


def bac_budget(settings: dict, today: date) -> dict:
    bac = next((c for c in settings.get('otras_cuentas', []) if c.get('nombre') == 'Débito BAC'), None)
    if not bac or 'presupuesto' not in bac:
        return {'error': 'no presupuesto'}
    p = bac['presupuesto']
    fecha_inicio = date.fromisoformat(p['fecha_inicio'])
    fecha_fin = date.fromisoformat(p['fecha_fin'])
    saldo_inicio = p['saldo_inicio']
    dias_total = p['dias_total']
    presupuesto_diario = round(saldo_inicio / dias_total, 2)
    dias_transcurridos = max(0, (today - fecha_inicio).days)
    dias_restantes = max(0, (fecha_fin - today).days)
    movimientos = bac.get('movimientos', [])
    gasto_periodo = round(sum(m['monto'] for m in movimientos
                              if m['tipo'] == 'egreso' and m['fecha'] >= p['fecha_inicio']), 2)
    presupuesto_consumido = round(presupuesto_diario * dias_transcurridos, 2)
    saldo_actual = bac.get('saldo', 0)
    return {
        'saldo_inicio': saldo_inicio,
        'saldo_actual': saldo_actual,
        'fecha_inicio': p['fecha_inicio'],
        'fecha_fin': p['fecha_fin'],
        'dias_total': dias_total,
        'dias_transcurridos': dias_transcurridos,
        'dias_restantes': dias_restantes,
        'presupuesto_diario': presupuesto_diario,
        'gasto_periodo': gasto_periodo,
        'presupuesto_consumido': presupuesto_consumido,
        'remanente': round(presupuesto_consumido - gasto_periodo, 2),
        'proyeccion_diaria': round(saldo_actual / dias_restantes, 2) if dias_restantes > 0 else 0,
        'movimientos': list(reversed(movimientos)),
    }


def balances_with_activity(balances: dict, transactions: list[dict]) -> dict:
    """Saldo de estado de cuenta ajustado con los movimientos posteriores a su fecha."""
    for bal in balances.values():
        since = [r for r in transactions
                 if r.get('banco') == bal['banco']
                 and r.get('fecha_iso', '') >= bal['fecha']
                 and not r.get('tipo', '').startswith('estado_cuenta')]
        gastos = sum(float(r.get('monto') or 0) for r in since if not r.get('tipo', '').startswith('credito'))
        ingresos = sum(float(r.get('monto') or 0) for r in since if r.get('tipo', '').startswith('credito'))
        bal['gastos_desde_ec'] = round(gastos, 2)
        bal['ingresos_desde_ec'] = round(ingresos, 2)
        bal['saldo_calculado'] = round(bal['saldo_estado_cuenta'] - gastos + ingresos, 2)
    return balances


FINANCIAL_TYPES = {'compra', 'transferencia', 'transfer365', 'debito', 'credito',
                   'pago_tarjeta', 'pago_servicio', 'suscripcion',
                   'estado_cuenta', 'estado_cuenta_pago_minimo'}


def recent_financial(transactions: list[dict], limit: int = 200) -> list[dict]:
    result = [r for r in transactions if r.get('tipo') in FINANCIAL_TYPES]
    result.sort(key=lambda r: r.get('fecha_iso', ''), reverse=True)
    return result[:limit]


def amex_fixed_costs(settings: dict) -> dict:
    gastos = settings.get('gastos_fijos_amex', [])
    return {'gastos': gastos,
            'total': round(sum(g['monto_mensual'] for g in gastos if not g.get('cancelar')), 2),
            'total_bruto': round(sum(g['monto_mensual'] for g in gastos), 2)}


def sporadic_funds(settings: dict) -> dict:
    fondos = settings.get('fondos_esporadicos', [])
    return {'fondos': fondos,
            'total_quincenal': round(sum(f['quincenal'] for f in fondos), 2),
            'total_saldo': round(sum(f['saldo'] for f in fondos), 2)}


def cash_on_hand(settings: dict) -> dict:
    ef = settings.get('efectivo_en_mano', {})
    return {'saldo': ef.get('saldo', 0), 'movimientos': list(reversed(ef.get('movimientos', [])))}
