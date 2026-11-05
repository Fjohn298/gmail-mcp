"""Calendarios: obligaciones del mes por día y ciclos de corte/pago de tarjetas."""
from datetime import date

from gmailmcp.dates import MONTHS_SHORT, next_occurrence


def _event(dia, descripcion, monto, tipo, subtipo, nxt: date, today: date, **extra) -> dict:
    return {'dia': dia, 'descripcion': descripcion, 'monto': monto, 'tipo': tipo, 'subtipo': subtipo,
            'passed': (nxt - today).days < 0, 'next_label': f"{MONTHS_SHORT[nxt.month]} {nxt.day}",
            'days_away': (nxt - today).days, **extra}


def payment_calendar(settings: dict, today: date) -> dict:
    planner = settings.get('planner', {})
    events = []
    for c in planner.get('cards', []):
        if c.get('min_pago', 0) <= 0:
            continue
        dia = c['fecha_pago_dia']
        events.append(_event(dia, f"{c['name']} ****{c['last4']}", c['min_pago'], 'pago', 'tarjeta',
                             next_occurrence(dia, today), today))
    for i in settings.get('intrafinanciamientos', []):
        dia = i.get('fecha_pago_dia', 0)
        if not dia:
            continue
        events.append(_event(dia, i['descripcion'], i['cuota_mensual'], 'pago', 'intrafinanciamiento',
                             next_occurrence(dia, today), today))
    for p in settings.get('prestamos', []):
        dia = p.get('fecha_pago_dia', 0)
        events.append(_event(dia, p['nombre'], p['cuota_mensual'], 'pago', 'prestamo',
                             next_occurrence(dia, today), today))
    for e in planner.get('obligaciones_extra', []):
        dia = e.get('fecha_pago_dia', 1)
        monto = (e.get('monto_matricula', e['monto_mensual'])
                 if today.month in e.get('meses_matricula', []) else e['monto_mensual'])
        events.append(_event(dia, e['descripcion'], monto, 'pago', 'extra', next_occurrence(dia, today),
                             today, notas=e.get('notas', '')))
    for f in settings.get('fondos_ahorro', []):
        for dia in f.get('dias_deposito', []):
            events.append(_event(dia, f"Depósito {f['nombre']}", f.get('deposito_quincena', 0), 'deposito',
                                 'ahorro', next_occurrence(dia, today), today))

    events.sort(key=lambda x: x['dia'])
    return {
        'events': events,
        'today_day': today.day,
        'total_egresos': round(sum(e['monto'] for e in events if e['tipo'] == 'pago'), 2),
        'total_ahorro': round(sum(e['monto'] for e in events if e['tipo'] == 'deposito'), 2),
    }


def _add_month(d: date) -> date:
    m, y = d.month + 1, d.year
    if m > 12:
        m, y = 1, y + 1
    return d.replace(year=y, month=m)


def card_cycle_calendar(settings: dict, today: date) -> dict:
    """Qué tarjeta conviene usar hoy según su próximo corte y fecha de pago."""
    result = []
    for c in settings.get('planner', {}).get('cards', []):
        corte_dia = c.get('fecha_corte_dia', c['fecha_pago_dia'] + 5)
        pago_dia = c['fecha_pago_dia']
        next_cut = next_occurrence(corte_dia, today)
        next_payment = _add_month(next_cut).replace(day=pago_dia)
        has_balance = c['balance'] > 0
        result.append({
            'name': c['name'], 'last4': c['last4'],
            'balance': c['balance'], 'has_balance': has_balance,
            'corte_dia': corte_dia, 'pago_dia': pago_dia,
            'next_cut_label': f"{MONTHS_SHORT[next_cut.month]} {next_cut.day}",
            'next_payment_label': f"{MONTHS_SHORT[next_payment.month]} {next_payment.day}",
            'days_until_cut': (next_cut - today).days,
            'days_until_payment': (next_payment - today).days,
            'safe_to_use': not has_balance,
        })
    result.sort(key=lambda x: (x['has_balance'], -x['days_until_payment']))
    return {'cards': result, 'today': today.isoformat()}
