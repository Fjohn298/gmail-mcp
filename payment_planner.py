import json
import os
import base64
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from zoneinfo import ZoneInfo
from gmail_auth import get_service, load_settings, api_call_with_retry
from gmail_logger import setup_logger

logger = setup_logger('payment_planner')
_TZ = ZoneInfo('America/El_Salvador')

_MONTHS_ES = [
    '', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]


def build_plan(config: dict) -> dict | None:
    salary = config.get('salary_per_period', 0)
    if not salary:
        return None

    savings_pct = config.get('savings_percentage', 0.10)
    cards = [c.copy() for c in config.get('cards', []) if c.get('balance', 0) > 0]
    prestamos = config.get('prestamos', [])

    savings = round(salary * savings_pct, 2)
    available = round(salary - savings, 2)

    # Fixed loan payments: monthly cuota split into 2 quincenas
    total_prestamos = round(sum(p.get('cuota_mensual', 0) / 2 for p in prestamos), 2)
    available_for_cards = round(available - total_prestamos, 2)

    # Minimum: 5 % of balance or $25, whichever is higher
    for card in cards:
        card['min_payment'] = max(round(card['balance'] * 0.05, 2), 25.0)

    total_minimum = round(sum(c['min_payment'] for c in cards), 2)
    extra = max(round(available_for_cards - total_minimum, 2), 0)

    # Avalanche: send all extra to the highest-balance card
    sorted_cards = sorted(cards, key=lambda x: x['balance'], reverse=True)

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
            'payment': round(payment, 2),
            'balance_after': round(max(card['balance'] - payment, 0), 2),
            'priority': i + 1,
            'is_focus': i == 0,
        })

    total_payments = round(sum(p['payment'] for p in payments), 2)
    free_to_spend = round(available_for_cards - total_payments, 2)
    total_debt = round(sum(c['balance'] for c in config.get('cards', [])), 2)

    # Rough estimate: how many periods until debt-free (assumes constant payments)
    periods_to_free = round(total_debt / total_payments) if total_payments > 0 else None

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
        'periods_to_debt_free': periods_to_free,
        'generated_at': datetime.now(tz=_TZ).isoformat(),
    }


def save_plan(plan: dict):
    os.makedirs('data', exist_ok=True)
    with open('data/payment_plan.json', 'w', encoding='utf-8') as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    logger.info("Plan guardado en data/payment_plan.json")


def _period_label(now: datetime) -> str:
    month = _MONTHS_ES[now.month]
    if now.day <= 15:
        return f"Quincena del 15 de {month} {now.year}"
    return f"Quincena del 30 de {month} {now.year}"


def _build_email_html(plan: dict, period_label: str) -> str:
    rows = ''
    for p in plan['payments']:
        tag = '🎯 Foco (avalancha)' if p['is_focus'] else 'Pago mínimo'
        tag_color = '#6366f1' if p['is_focus'] else '#64748b'
        rows += f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9">
            <strong>{p['name']}</strong><br>
            <span style="font-size:11px;color:#64748b">···{p['last4']}</span>
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;text-align:right;color:#ef4444">
            ${p['balance']:.2f}
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;text-align:right;
                     font-weight:700;font-size:16px;color:#6366f1">
            ${p['payment']:.2f}
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;text-align:right;color:#16a34a">
            ${p['balance_after']:.2f}
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;
                     font-size:11px;color:{tag_color}">{tag}</td>
        </tr>"""

    periods = plan.get('periods_to_debt_free')
    months = round(periods / 2) if periods else None
    estimate = ''
    if months:
        estimate = f"""<p style="margin:12px 0 0;color:#64748b;font-size:13px">
          📅 A este ritmo pagarías la deuda en aproximadamente
          <strong>{periods} quincenas (~{months} meses)</strong>.
        </p>"""

    pct = round(plan['savings_pct'] * 100)
    now_str = datetime.now(tz=_TZ).strftime('%d/%m/%Y %H:%M')
    prestamos_row = ''
    if plan.get('total_prestamos', 0) > 0:
        prestamos_row = f"""<tr>
        <td style="padding:10px 12px;color:#f59e0b">🏛️ Préstamos fijos (quinc.)</td>
        <td style="padding:10px 12px;text-align:right;font-weight:700;color:#f59e0b">${plan['total_prestamos']:.2f}</td>
      </tr>"""

    return f"""<!DOCTYPE html>
<html lang="es">
<body style="margin:0;padding:20px;background:#f8fafc;font-family:Arial,sans-serif">
<div style="max-width:600px;margin:0 auto">

  <div style="background:#6366f1;border-radius:14px 14px 0 0;padding:24px 28px;color:white">
    <h1 style="margin:0;font-size:22px">💰 Plan Financiero</h1>
    <p style="margin:6px 0 0;opacity:.85;font-size:14px">{period_label}</p>
  </div>

  <div style="background:white;padding:24px 28px;border:1px solid #e2e8f0">
    <h3 style="margin:0 0 16px;color:#1e293b;font-size:15px">📊 Distribución de la quincena</h3>
    <table style="width:100%;border-collapse:collapse">
      <tr style="background:#f8fafc">
        <td style="padding:10px 12px;color:#64748b">💵 Salario quincena</td>
        <td style="padding:10px 12px;text-align:right;font-weight:700">${plan['salary']:.2f}</td>
      </tr>
      <tr>
        <td style="padding:10px 12px;color:#16a34a">🏦 Ahorro ({pct}%)</td>
        <td style="padding:10px 12px;text-align:right;font-weight:700;color:#16a34a">${plan['savings']:.2f}</td>
      </tr>
      {prestamos_row}
      <tr style="background:#f8fafc">
        <td style="padding:10px 12px;color:#6366f1">💳 Total pago tarjetas</td>
        <td style="padding:10px 12px;text-align:right;font-weight:700;color:#6366f1">${plan['total_payments']:.2f}</td>
      </tr>
      <tr style="border-top:2px solid #e2e8f0">
        <td style="padding:14px 12px;font-size:16px;font-weight:700">🛍️ Libre para gastar</td>
        <td style="padding:14px 12px;text-align:right;font-size:22px;font-weight:700;color:#1e293b">${plan['free_to_spend']:.2f}</td>
      </tr>
    </table>
  </div>

  <div style="background:white;padding:24px 28px;border:1px solid #e2e8f0;border-top:none">
    <h3 style="margin:0 0 16px;color:#1e293b;font-size:15px">💳 Detalle de pagos</h3>
    <table style="width:100%;border-collapse:collapse">
      <thead>
        <tr style="background:#f8fafc">
          <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748b;text-transform:uppercase">Tarjeta</th>
          <th style="padding:10px 12px;text-align:right;font-size:11px;color:#64748b;text-transform:uppercase">Saldo</th>
          <th style="padding:10px 12px;text-align:right;font-size:11px;color:#64748b;text-transform:uppercase">Pagar</th>
          <th style="padding:10px 12px;text-align:right;font-size:11px;color:#64748b;text-transform:uppercase">Queda</th>
          <th style="padding:10px 12px;font-size:11px;color:#64748b;text-transform:uppercase">Tipo</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    {estimate}
  </div>

  <div style="background:#1e293b;border-radius:0 0 14px 14px;padding:16px 28px;
              color:#94a3b8;font-size:11px;text-align:center">
    Generado automáticamente por Gmail MCP · {now_str} (El Salvador)
  </div>

</div>
</body>
</html>"""


def send_plan_email(plan: dict, period_label: str):
    settings = load_settings()
    notify_email = settings.get('planner', {}).get('notify_email', '')
    if not notify_email:
        logger.warning("planner.notify_email no configurado en settings.json")
        return

    service = get_service()
    html = _build_email_html(plan, period_label)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"💰 Plan Financiero — {period_label}"
    msg['From'] = 'me'
    msg['To'] = notify_email
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    api_call_with_retry(
        service.users().messages().send(userId='me', body={'raw': raw}).execute
    )
    logger.info(f"Email del plan enviado a {notify_email}")


def run_planner(force: bool = False):
    settings = load_settings()
    planner = settings.get('planner', {})

    if not planner.get('salary_per_period'):
        logger.info("Planner: salario no configurado en settings.json → saltando")
        return 0

    now = datetime.now(tz=_TZ)
    run_days = planner.get('run_days', [13, 28])

    if now.day not in run_days and not force:
        return 0

    label = _period_label(now)
    logger.info(f"▶ Generando plan para: {label}")

    planner['prestamos'] = settings.get('prestamos', [])
    plan = build_plan(planner)
    if not plan:
        logger.warning("No se pudo generar el plan")
        return 0

    save_plan(plan)
    send_plan_email(plan, label)
    logger.info(
        f"✓ Plan: ahorro=${plan['savings']:.2f} | "
        f"tarjetas=${plan['total_payments']:.2f} | "
        f"libre=${plan['free_to_spend']:.2f}"
    )
    return 1


if __name__ == '__main__':
    run_planner(force=True)
