"""Plan quincenal de pagos de tarjetas (estrategia avalancha) y su envío por correo."""
import copy
import logging
from collections.abc import Callable
from datetime import datetime

from gmailmcp.clock import now_local
from gmailmcp.dates import MONTHS_LONG, MONTHS_SHORT, add_months
from gmailmcp.notifications.notifier import EmailNotifier
from gmailmcp.notifications.plan_email import render_plan_email
from gmailmcp.repositories.settings_repo import JsonSettingsRepository
from gmailmcp.repositories.state_repo import JsonPlanRepository


def simulate_payoff(sim_cards: list, monthly_budget: float) -> dict:
    """Simulación waterfall avalancha. Retorna {nombre_tarjeta: meses_hasta_cero}."""
    cards = copy.deepcopy(sim_cards)
    result = {}
    for month in range(1, 361):
        if not any(c['balance'] > 0.01 for c in cards):
            break
        for c in cards:
            if c['balance'] > 0.01:
                c['balance'] = round(c['balance'] * (1 + c['rate_m']), 2)
        remaining = monthly_budget
        for c in cards:
            if c['balance'] > 0.01:
                pay = min(c['min_monthly'], c['balance'])
                c['balance'] = round(max(0, c['balance'] - pay), 2)
                remaining = round(max(0, remaining - pay), 2)
                if c['balance'] <= 0.01:
                    c['balance'] = 0
                    result.setdefault(c['name'], month)
        if remaining > 0.01:
            for c in cards:
                if c['balance'] > 0.01:
                    pay = min(remaining, c['balance'])
                    c['balance'] = round(max(0, c['balance'] - pay), 2)
                    if c['balance'] <= 0.01:
                        c['balance'] = 0
                        result.setdefault(c['name'], month)
                    break
    return result


def payment_calendar(payments: list, prestamos: list) -> dict:
    """Asigna cada deuda a la quincena-15 (vence 16-31) o a la quincena-30 (vence 1-15)."""
    q15, q30, unknown = [], [], []
    for p in payments:
        dia = p.get('fecha_pago_dia', 0)
        item = {'name': p['name'], 'last4': p['last4'],
                'amount': round(p['payment'] * 2, 2),
                'dia': dia, 'type': 'tarjeta',
                'is_focus': p['is_focus'], 'priority': p['priority']}
        (q15 if dia >= 16 else q30 if dia >= 1 else unknown).append(item)
    for pr in prestamos:
        dia = pr.get('fecha_pago_dia', 0)
        item = {'name': pr['nombre'], 'last4': None,
                'amount': pr['cuota_mensual'],
                'dia': dia, 'type': 'prestamo', 'is_focus': False}
        (q15 if dia >= 16 else q30 if dia >= 1 else unknown).append(item)
    return {
        'q15': sorted(q15, key=lambda x: x['dia']),
        'q30': sorted(q30, key=lambda x: x['dia']),
        'unknown': unknown,
    }


def build_plan(config: dict, now: datetime | None = None) -> dict | None:
    """Función pura: configuración del planner → plan de la quincena (None si no hay salario)."""
    now = now or now_local()
    salary = config.get('salary_per_period', 0)
    if not salary:
        return None

    savings_pct = config.get('savings_percentage', 0.10)
    cards = [c.copy() for c in config.get('cards', []) if c.get('balance', 0) > 0]
    prestamos = config.get('prestamos', [])

    savings = round(salary * savings_pct, 2)
    available = round(salary - savings, 2)

    # Cuota mensual fija de préstamos repartida en 2 quincenas
    total_prestamos = round(sum(p.get('cuota_mensual', 0) / 2 for p in prestamos), 2)
    available_for_cards = round(available - total_prestamos, 2)

    # Pago mínimo: mínimo mensual guardado / 2 (quincenal); si no hay, regla 5% / $25
    for card in cards:
        stored = card.get('min_pago', 0)
        card['min_payment'] = round(stored / 2, 2) if stored > 0 else max(round(card['balance'] * 0.05, 2), 25.0)

    total_minimum = round(sum(c['min_payment'] for c in cards), 2)
    extra = max(round(available_for_cards - total_minimum, 2), 0)

    # Prioridad híbrida: mayor tasa primero; a igual tasa, menor saldo (avalancha + quick win)
    sorted_cards = sorted(cards, key=lambda x: (-x.get('tasa_anual', 30.0), x['balance']))

    payments = []
    remaining_extra = extra
    for i, card in enumerate(sorted_cards):
        payment = card['min_payment']
        if i == 0 and remaining_extra > 0:
            bonus = min(remaining_extra, card['balance'] - card['min_payment'])
            payment += max(bonus, 0)
            remaining_extra -= max(bonus, 0)
        payments.append({
            'name': card['name'],
            'last4': card['last4'],
            'balance': card['balance'],
            'min_payment': card['min_payment'],
            'tasa_anual': card.get('tasa_anual', 30.0),
            'fecha_pago_dia': card.get('fecha_pago_dia', 0),
            'payment': round(payment, 2),
            'balance_after': round(max(card['balance'] - payment, 0), 2),
            'priority': i + 1,
            'is_focus': i == 0,
        })

    total_payments = round(sum(p['payment'] for p in payments), 2)
    free_to_spend = round(available_for_cards - total_payments, 2)
    total_debt = round(sum(c['balance'] for c in config.get('cards', [])), 2)

    today_d = now.date()
    monthly_budget = round(total_payments * 2, 2)
    sim_cards = [{'name': c['name'], 'balance': c['balance'],
                  'min_monthly': round(c['min_payment'] * 2, 2),
                  'rate_m': c.get('tasa_anual', 30.0) / 100 / 12}
                 for c in sorted_cards]
    payoff_map = simulate_payoff(sim_cards, monthly_budget) if monthly_budget > 0 else {}
    for p in payments:
        pm = payoff_map.get(p['name'])
        if pm:
            pd = add_months(today_d, pm)
            p['payoff_months'] = pm
            p['payoff_label'] = f"{MONTHS_SHORT[pd.month]} {pd.year}"
        else:
            p['payoff_months'] = None
            p['payoff_label'] = None

    all_free_months = max(payoff_map.values()) if payoff_map else None
    all_free_label = None
    if all_free_months:
        d = add_months(today_d, all_free_months)
        all_free_label = f"{MONTHS_SHORT[d.month]} {d.year}"

    return {
        'salary': salary,
        'savings': savings,
        'savings_pct': savings_pct,
        'available': available,
        'total_prestamos': total_prestamos,
        'available_for_cards': available_for_cards,
        'total_minimum': total_minimum,
        'extra_for_debt': extra,
        'payments': payments,
        'total_payments': total_payments,
        'free_to_spend': free_to_spend,
        'total_debt': total_debt,
        'all_cards_free_months': all_free_months,
        'all_cards_free_label': all_free_label,
        'payment_calendar': payment_calendar(payments, prestamos),
        'generated_at': now.isoformat(),
    }


def period_label(now: datetime) -> str:
    month = MONTHS_LONG[now.month]
    if now.day <= 15:
        return f"Quincena del 15 de {month} {now.year}"
    return f"Quincena del 30 de {month} {now.year}"


def planner_config(settings: dict) -> dict:
    """Config del planner con los préstamos adjuntos, como espera build_plan."""
    planner = dict(settings.get('planner', {}))
    planner['prestamos'] = settings.get('prestamos', [])
    return planner


class PaymentPlannerService:
    def __init__(self, settings_repo: JsonSettingsRepository, plans: JsonPlanRepository,
                 notifier: EmailNotifier, logger: logging.Logger,
                 now: Callable[[], datetime] = now_local):
        self._settings_repo = settings_repo
        self._plans = plans
        self._notifier = notifier
        self._logger = logger
        self._now = now

    def send(self, plan: dict, label: str) -> None:
        notify_email = self._settings_repo.load().get('planner', {}).get('notify_email', '')
        if not notify_email:
            self._logger.warning("planner.notify_email no configurado en settings.json")
            return
        self._notifier.send_html(notify_email, f"💰 Plan Financiero — {label}",
                                 render_plan_email(plan, label, self._now()))
        self._logger.info(f"Email del plan enviado a {notify_email}")

    def run(self, force: bool = False) -> int:
        settings = self._settings_repo.load()
        planner = settings.get('planner', {})
        if not planner.get('salary_per_period'):
            self._logger.info("Planner: salario no configurado en settings.json → saltando")
            return 0

        now = self._now()
        if now.day not in planner.get('run_days', [13, 28]) and not force:
            return 0

        label = period_label(now)
        self._logger.info(f"▶ Generando plan para: {label}")
        plan = build_plan(planner_config(settings), now)
        if not plan:
            self._logger.warning("No se pudo generar el plan")
            return 0

        self._plans.save(plan)
        self._logger.info("Plan guardado en data/payment_plan.json")
        self.send(plan, label)
        self._logger.info(f"✓ Plan: ahorro=${plan['savings']:.2f} | "
                          f"tarjetas=${plan['total_payments']:.2f} | "
                          f"libre=${plan['free_to_spend']:.2f}")
        return 1
