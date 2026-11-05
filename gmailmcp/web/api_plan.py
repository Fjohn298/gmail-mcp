"""API del plan quincenal: configuración, envío, fondos, financiamientos, actividad."""
from flask import Blueprint, jsonify, request

from gmailmcp.clock import now_local, today_local
from gmailmcp.services import debts, finance_views
from gmailmcp.services.email_insights import recent_activity
from gmailmcp.services.payment_planner import build_plan, period_label, planner_config
from gmailmcp.web.deps import container

bp = Blueprint('plan', __name__, url_prefix='/api')


@bp.get('/plan')
def plan_get():
    plans = container().plans
    if not plans.exists():
        return jsonify({'error': 'Sin plan generado. Configura tu salario y guarda.'})
    return jsonify(plans.load())


@bp.post('/plan/config')
def plan_config():
    c = container()
    data = request.get_json()
    settings = c.settings.load()
    debts.update_planner_config(settings, salary=float(data.get('salary', 0)),
                                savings_pct=float(data.get('savings_pct', 0.10)),
                                cards=data.get('cards', []))
    c.settings.save(settings)
    plan = build_plan(planner_config(settings))
    if not plan:
        return jsonify({'error': 'Salario inválido'}), 400
    c.plans.save(plan)
    return jsonify({'ok': True, 'plan': plan})


@bp.post('/plan/send')
def plan_send():
    c = container()
    if not c.plans.exists():
        return jsonify({'error': 'Sin plan guardado'}), 400
    c.planner_service().send(c.plans.load(), period_label(now_local()))
    return jsonify({'ok': True})


@bp.route('/summary/send', methods=['POST', 'GET'])
def summary_send():
    container().summary_service().send()
    return jsonify({'ok': True, 'msg': 'Resumen enviado correctamente'})


@bp.get('/plan/fondos')
def plan_fondos():
    return jsonify(finance_views.savings_and_loans(container().settings.load()))


@bp.get('/plan/financiamientos')
def plan_financiamientos():
    return jsonify(finance_views.financing_overview(container().settings.load(), today_local()))


@bp.get('/plan/snapshot')
def plan_snapshot():
    return jsonify(debts.debt_snapshot(container().settings.load(), today_local()))


@bp.get('/plan/quincenal')
def plan_quincenal():
    return jsonify(container().settings.load().get('plan_quincenal', {}))


@bp.get('/plan/gastos_fijos_amex')
def plan_gastos_fijos_amex():
    return jsonify(finance_views.amex_fixed_costs(container().settings.load()))


@bp.route('/plan/fondos_esporadicos', methods=['GET', 'POST'])
def plan_fondos_esporadicos():
    c = container()
    settings = c.settings.load()
    if request.method == 'GET':
        return jsonify(finance_views.sporadic_funds(settings))
    data = request.get_json()
    fondos = settings.get('fondos_esporadicos', [])
    fondo = next((f for f in fondos if f['nombre'] == data.get('nombre')), None)
    if fondo:
        fondo['saldo'] = round(float(data.get('saldo', 0)), 2)
    settings['fondos_esporadicos'] = fondos
    c.settings.save(settings)
    return jsonify({'ok': True})


@bp.get('/plan/activity')
def plan_activity():
    c = container()
    days = int(request.args.get('days', 30))
    return jsonify(recent_activity(c.gmail('dashboard'), c.parsers, c.classifier,
                                   c.settings.load(), days, today_local))


@bp.post('/plan/activity/confirm')
def plan_activity_confirm():
    """Body: {last4, delta}. delta < 0 = pago recibido; delta > 0 = compra nueva."""
    c = container()
    data = request.get_json()
    last4 = data.get('last4', '')
    delta = float(data.get('delta', 0))
    if not last4:
        return jsonify({'error': 'last4 requerido'}), 400
    if delta == 0:
        return jsonify({'error': 'delta no puede ser 0'}), 400
    settings = c.settings.load()
    try:
        card = debts.apply_card_delta(settings, last4, delta)
    except debts.CardNotFound:
        return jsonify({'error': 'Tarjeta no encontrada'}), 404
    c.settings.save(settings)
    return jsonify({'ok': True, 'name': card['name'], 'new_balance': card['balance']})
