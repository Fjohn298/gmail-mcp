"""API de lectura y corrección de finanzas: transacciones, saldos, cuentas, calendarios."""
from flask import Blueprint, jsonify, request

from gmailmcp.clock import today_local
from gmailmcp.services import calendar, debts, finance_views, leaks
from gmailmcp.web.deps import container

bp = Blueprint('finance', __name__, url_prefix='/api')


def _settings() -> dict:
    return container().settings.load()


@bp.get('/transactions')
def transactions():
    return jsonify(container().transactions.all())


@bp.post('/correct')
def correct():
    data = request.get_json()
    repo = container().transactions
    rows = repo.all()
    idx = int(data['idx'])
    if 0 <= idx < len(rows):
        for field in ('fecha_iso', 'banco', 'comercio', 'tipo', 'monto'):
            rows[idx][field] = data.get(field, rows[idx].get(field, ''))
        rows[idx]['revisado'] = 'true'
        repo.replace_all(rows)
    return jsonify(rows)


@bp.get('/balances')
def balances():
    c = container()
    return jsonify(finance_views.balances_with_activity(c.balances.load(), c.transactions.all()))


@bp.get('/emails/financial')
def emails_financial():
    return jsonify(finance_views.recent_financial(container().transactions.all()))


@bp.get('/cuenta')
def cuenta():
    return jsonify(finance_views.cash_flow(_settings()))


@bp.get('/calendario_pagos')
def calendario_pagos():
    return jsonify(calendar.payment_calendar(_settings(), today_local()))


@bp.get('/tarjetas/calendario')
def tarjetas_calendario():
    return jsonify(calendar.card_cycle_calendar(_settings(), today_local()))


@bp.get('/amex/historial')
def amex_historial():
    s = _settings()
    return jsonify({'historial': s.get('amex_historial', []), 'estado_actual': s.get('amex_estado_actual', {})})


@bp.get('/otras_cuentas')
def otras_cuentas():
    return jsonify(_settings().get('otras_cuentas', []))


@bp.get('/deudas/estrategias')
def deudas_estrategias():
    return jsonify(debts.compare_strategies(_settings(), today_local()))


@bp.get('/fugas')
def fugas():
    return jsonify(leaks.detect_leaks(_settings()))


@bp.get('/efectivo')
def efectivo():
    return jsonify(finance_views.cash_on_hand(_settings()))


@bp.get('/presupuesto_bac')
def presupuesto_bac():
    return jsonify(finance_views.bac_budget(_settings(), today_local()))


@bp.get('/recomendaciones')
def recomendaciones():
    return jsonify(container().recommendations.load())


@bp.get('/notas')
def notas_get():
    return jsonify({'texto': container().notes.load()})


@bp.post('/notas')
def notas_post():
    container().notes.save(request.get_json().get('texto', '').strip())
    return jsonify({'ok': True})
