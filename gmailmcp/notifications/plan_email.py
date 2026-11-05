"""HTML del correo "Plan Financiero" (presentación pura: datos in, HTML out)."""
from datetime import datetime


def render_plan_email(plan: dict, period_label: str, now: datetime) -> str:
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
    now_str = now.strftime('%d/%m/%Y %H:%M')
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
