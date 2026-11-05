"""Deudas: snapshot con fechas de liquidación y comparación de estrategias de pago."""
import copy
import math
from datetime import date

from gmailmcp.dates import MONTHS_SHORT


def _month_after(today: date, months: int) -> tuple[int, int]:
    raw = today.month - 1 + months
    return today.year + raw // 12, raw % 12 + 1


def payoff_info(balance: float, tasa_anual: float, min_pago: float, today: date) -> dict:
    """Cuándo se liquida una tarjeta pagando solo el mínimo (fórmula de amortización)."""
    if balance <= 0:
        return {'label': 'Pagado ✓', 'never': False, 'paid': True}
    r = tasa_anual / 100 / 12
    if min_pago <= 0:
        return {'label': '—', 'never': True, 'paid': False}
    if r > 0 and min_pago <= balance * r:
        return {'label': f'Interés/mes ${balance * r:.2f} > pago mínimo', 'never': True, 'paid': False}
    if r == 0:
        months = math.ceil(balance / min_pago)
    else:
        months = math.ceil(-math.log(1 - balance * r / min_pago) / math.log(1 + r))
    year, month = _month_after(today, months)
    return {'label': f'{MONTHS_SHORT[month]} {year} ({months}m)', 'never': False, 'paid': False}


def debt_snapshot(settings: dict, today: date) -> dict:
    cards_cfg = settings.get('planner', {}).get('cards', [])
    cards = [{**c, 'payoff': payoff_info(c['balance'], c['tasa_anual'], c['min_pago'], today)}
             for c in cards_cfg]
    return {'cards': cards,
            'total_balance': round(sum(c['balance'] for c in cards_cfg), 2),
            'total_min': round(sum(c['min_pago'] for c in cards_cfg), 2)}


def _collect_debts(settings: dict) -> list[dict]:
    debts = []
    for c in settings.get('planner', {}).get('cards', []):
        if c['balance'] > 0:
            tasa_m = c['tasa_anual'] / 100 / 12
            debts.append({
                'id': f"card_{c['last4']}", 'nombre': f"{c['name']} ····{c['last4']}", 'tipo': 'tarjeta',
                'saldo': c['balance'], 'tasa_mensual': round(tasa_m, 6), 'tasa_anual': c['tasa_anual'],
                'pago_minimo': max(c.get('min_pago', 0), round(c['balance'] * tasa_m + 1, 2)),
            })
    for p in settings.get('prestamos', []):
        if p.get('saldo', 0) > 0:
            debts.append({
                'id': f"prestamo_{p.get('numero', p['nombre'])}", 'nombre': p['nombre'], 'tipo': 'prestamo',
                'saldo': p['saldo'], 'tasa_mensual': round(p['tasa_anual'] / 100 / 12, 6),
                'tasa_anual': p['tasa_anual'], 'pago_minimo': p['cuota_mensual'],
            })
    for fi in settings.get('intrafinanciamientos', []):
        if fi.get('saldo_actual', 0) > 0 and fi.get('tasa_mensual', 0) > 0:
            debts.append({
                'id': f"fi_{fi['ref']}", 'nombre': fi['descripcion'][:40], 'tipo': 'financiamiento',
                'saldo': fi['saldo_actual'], 'tasa_mensual': fi['tasa_mensual'] / 100,
                'tasa_anual': round(fi['tasa_mensual'] * 12, 2), 'pago_minimo': fi['cuota_mensual'],
            })
    return debts


def simulate_strategy(debts_ordered: list[dict], budget: float) -> tuple[int, float, dict]:
    """Mes a mes: interés, mínimos en orden y el sobrante a la primera deuda viva."""
    ds = copy.deepcopy(debts_ordered)
    month = 0
    total_interest = 0.0
    payoff_months = {}
    while any(d['saldo'] > 0.01 for d in ds) and month < 360:
        month += 1
        for d in ds:
            if d['saldo'] > 0.01:
                interest = d['saldo'] * d['tasa_mensual']
                d['saldo'] = round(d['saldo'] + interest, 4)
                total_interest += interest
        remaining = budget
        for d in ds:
            if d['saldo'] > 0.01:
                pay = min(d['pago_minimo'], d['saldo'], remaining)
                d['saldo'] = max(0, round(d['saldo'] - pay, 4))
                remaining = round(remaining - pay, 4)
                if d['saldo'] <= 0.01:
                    d['saldo'] = 0
                    payoff_months.setdefault(d['id'], month)
        for d in ds:
            if d['saldo'] > 0.01 and remaining > 0.01:
                pay = min(remaining, d['saldo'])
                d['saldo'] = max(0, round(d['saldo'] - pay, 4))
                if d['saldo'] <= 0.01:
                    d['saldo'] = 0
                    payoff_months.setdefault(d['id'], month)
                break
    return month, round(total_interest, 2), payoff_months


def compare_strategies(settings: dict, today: date) -> dict:
    planner = settings.get('planner', {})
    ingreso_mensual = planner.get('salary_per_period', 0) * 2
    debts = _collect_debts(settings)

    total_min = round(sum(d['pago_minimo'] for d in debts), 2)
    multimoney_mes = round(sum(f.get('deposito_quincena', 0) * 2 for f in settings.get('fondos_ahorro', [])
                               if f.get('deposito_quincena')), 2)
    oblig_extra = round(sum(e.get('monto_mensual', 0) for e in planner.get('obligaciones_extra', [])), 2)
    fi_zero = round(sum(fi.get('cuota_mensual', 0) for fi in settings.get('intrafinanciamientos', [])
                        if fi.get('saldo_actual', 0) > 0 and fi.get('tasa_mensual', 0) == 0), 2)
    remanente = round(ingreso_mensual - total_min - multimoney_mes - oblig_extra - fi_zero, 2)
    extra_budget = max(0, remanente)
    budget_total = round(total_min + extra_budget, 2)

    def label(m):
        year, month = _month_after(today, m)
        return f"{MONTHS_SHORT[month]} {year}"

    def strategy_obj(name, ordered, meses, interes, poffs):
        return {
            'label': name,
            'orden': [{'id': d['id'], 'nombre': d['nombre'], 'saldo': d['saldo'],
                       'tasa_anual': d['tasa_anual'],
                       'liquidacion_label': label(poffs.get(d['id'], meses)),
                       'mes': poffs.get(d['id'], meses)} for d in ordered],
            'meses': meses,
            'liquidacion_label': label(meses),
            'interes_total': interes,
        }

    orders = {
        'avalancha': ('Avalancha', sorted(debts, key=lambda d: -d['tasa_anual'])),
        'bola_de_nieve': ('Bola de nieve', sorted(debts, key=lambda d: d['saldo'])),
        'hibrida': ('Híbrida', sorted([d for d in debts if d['saldo'] < 500], key=lambda d: d['saldo'])
                    + sorted([d for d in debts if d['saldo'] >= 500], key=lambda d: -d['tasa_anual'])),
    }
    estrategias, intereses = {}, []
    for key, (name, ordered) in orders.items():
        meses, interes, poffs = simulate_strategy(ordered, budget_total)
        estrategias[key] = strategy_obj(name, ordered, meses, interes, poffs)
        intereses.append((key, interes))

    return {
        'debts': debts,
        'budget_total': budget_total,
        'total_min': total_min,
        'extra_budget': extra_budget,
        'ingreso_mensual': ingreso_mensual,
        'recomendada': min(intereses, key=lambda x: x[1])[0],
        'estrategias': estrategias,
    }


class CardNotFound(LookupError):
    pass


def apply_card_delta(settings: dict, last4: str, delta: float) -> dict:
    """Ajusta el saldo de una tarjeta (delta<0 pago, delta>0 compra). Muta y devuelve la tarjeta."""
    cards = settings.get('planner', {}).get('cards', [])
    card = next((c for c in cards if c.get('last4') == last4), None)
    if not card:
        raise CardNotFound(last4)
    card['balance'] = max(0, round(card['balance'] + delta, 2))
    return card


def update_planner_config(settings: dict, salary: float, savings_pct: float, cards: list[dict]) -> None:
    """Actualiza salario/ahorro y solo los saldos enviados, conservando el resto de cada tarjeta."""
    planner = settings.setdefault('planner', {})
    planner['salary_per_period'] = salary
    planner['savings_percentage'] = savings_pct
    existing = {c['last4']: c for c in planner.get('cards', [])}
    for c in cards:
        if float(c.get('balance', 0)) > 0:
            existing[c['last4']] = {**existing.get(c['last4'], {}),
                                    'name': c['name'], 'last4': c['last4'],
                                    'balance': float(c['balance'])}
    planner['cards'] = list(existing.values())
