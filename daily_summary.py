import base64
import os
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from math import log
from zoneinfo import ZoneInfo

from gmail_auth import api_call_with_retry, get_service, load_settings
from gmail_logger import setup_logger

logger = setup_logger('daily_summary')
_TZ = ZoneInfo('America/El_Salvador')

_TIPO_ICON = {
    'tarjeta': '💳',
    'intrafinanciamiento': '🏦',
    'prestamo': '🏛️',
    'extra': '📚',
    'ahorro': '💰',
}
_TIPO_COLOR = {
    'tarjeta': '#e4002b',
    'intrafinanciamiento': '#0ea5e9',
    'prestamo': '#f59e0b',
    'extra': '#a855f7',
    'ahorro': '#22c55e',
}


def _next_occurrence(dia: int, today: date) -> date:
    if today.day <= dia:
        try:
            return today.replace(day=dia)
        except ValueError:
            pass
    m, y = (today.month % 12) + 1, today.year + (1 if today.month == 12 else 0)
    try:
        return date(y, m, dia)
    except ValueError:
        return date(y, m, 28)


def build_summary(today: date | None = None) -> dict:
    if today is None:
        today = datetime.now(tz=_TZ).date()

    settings = load_settings()
    planner = settings.get('planner', {})

    # --- BAC presupuesto ---
    bac = next((c for c in settings.get('otras_cuentas', [])
                if c.get('nombre') == 'Débito BAC'), {})
    bac_saldo = bac.get('saldo', 0)
    ppto = bac.get('presupuesto', {})

    ppto_diario = remanente = gasto_ayer = dias_restantes = proyeccion_diaria = 0
    fecha_fin_str = ''

    if ppto:
        fecha_inicio = date.fromisoformat(ppto['fecha_inicio'])
        fecha_fin = date.fromisoformat(ppto['fecha_fin'])
        fecha_fin_str = ppto['fecha_fin']
        saldo_inicio = ppto['saldo_inicio']
        dias_total = ppto['dias_total']
        ppto_diario = round(saldo_inicio / dias_total, 2)
        dias_transcurridos = max(0, (today - fecha_inicio).days)
        dias_restantes = max(0, (fecha_fin - today).days)

        movimientos = bac.get('movimientos', [])
        ayer_str = (today - timedelta(days=1)).isoformat()
        gasto_periodo = round(sum(m['monto'] for m in movimientos
                                  if m['tipo'] == 'egreso'
                                  and m['fecha'] >= ppto['fecha_inicio']), 2)
        gasto_ayer = round(sum(m['monto'] for m in movimientos
                               if m['tipo'] == 'egreso' and m['fecha'] == ayer_str), 2)
        presupuesto_consumido = round(ppto_diario * dias_transcurridos, 2)
        remanente = round(presupuesto_consumido - gasto_periodo, 2)
        proyeccion_diaria = round(bac_saldo / dias_restantes, 2) if dias_restantes > 0 else 0

    # --- MultiMoney ---
    multimoney_saldo = 0
    for f in settings.get('fondos_ahorro', []):
        if 'MultiMoney' in f.get('nombre', ''):
            multimoney_saldo = f.get('saldo', 0)
            break

    # --- Agrícola Max Electrónico ---
    agricola_saldo = next(
        (c.get('saldo', 0) for c in settings.get('otras_cuentas', [])
         if 'Agrícola' in c.get('nombre', '') or 'Agricola' in c.get('nombre', '')),
        0
    )

    # --- Próximos 7 días ---
    upcoming = []

    for c in planner.get('cards', []):
        if c.get('min_pago', 0) <= 0 and c.get('balance', 0) <= 0:
            continue
        nxt = _next_occurrence(c['fecha_pago_dia'], today)
        days_away = (nxt - today).days
        if 0 <= days_away <= 7:
            upcoming.append({
                'descripcion': f"{c['name']} ****{c['last4']}",
                'fecha': nxt.isoformat(), 'days_away': days_away,
                'monto': c.get('min_pago', 0), 'tipo': 'tarjeta',
            })

    for fi in settings.get('intrafinanciamientos', []):
        if fi.get('saldo_actual', 0) <= 0:
            continue
        nxt = _next_occurrence(fi.get('fecha_pago_dia', 1), today)
        days_away = (nxt - today).days
        if 0 <= days_away <= 7:
            upcoming.append({
                'descripcion': fi['descripcion'],
                'fecha': nxt.isoformat(), 'days_away': days_away,
                'monto': fi['cuota_mensual'], 'tipo': 'intrafinanciamiento',
            })

    for p in settings.get('prestamos', []):
        nxt = _next_occurrence(p.get('fecha_pago_dia', 1), today)
        days_away = (nxt - today).days
        if 0 <= days_away <= 7:
            upcoming.append({
                'descripcion': p['nombre'],
                'fecha': nxt.isoformat(), 'days_away': days_away,
                'monto': p['cuota_mensual'], 'tipo': 'prestamo',
            })

    for e in planner.get('obligaciones_extra', []):
        nxt = _next_occurrence(e.get('fecha_pago_dia', 1), today)
        days_away = (nxt - today).days
        if 0 <= days_away <= 7:
            upcoming.append({
                'descripcion': e['descripcion'],
                'fecha': nxt.isoformat(), 'days_away': days_away,
                'monto': e['monto_mensual'], 'tipo': 'extra',
            })

    for f in settings.get('fondos_ahorro', []):
        for dia in f.get('dias_deposito', []):
            nxt = _next_occurrence(dia, today)
            days_away = (nxt - today).days
            if 0 <= days_away <= 7:
                upcoming.append({
                    'descripcion': f"Depósito {f['nombre']}",
                    'fecha': nxt.isoformat(), 'days_away': days_away,
                    'monto': f.get('deposito_quincena', 0), 'tipo': 'ahorro',
                })
                break

    upcoming.sort(key=lambda x: x['days_away'])

    return {
        'today': today.isoformat(),
        'bac_saldo': bac_saldo,
        'ppto_diario': ppto_diario,
        'gasto_ayer': gasto_ayer,
        'remanente': remanente,
        'dias_restantes': dias_restantes,
        'proyeccion_diaria': proyeccion_diaria,
        'fecha_fin': fecha_fin_str,
        'multimoney_saldo': multimoney_saldo,
        'agricola_saldo': agricola_saldo,
        'upcoming': upcoming,
        'bien': remanente >= 0,
    }


def build_email_html(s: dict) -> str:
    today_dt = date.fromisoformat(s['today'])
    fecha_str = today_dt.strftime('%d/%m/%Y')
    indicador = '✅' if s['bien'] else '⚠️'
    indicador_txt = ('Bajo presupuesto — vas bien'
                     if s['bien'] else 'Excediste el límite ayer')
    ind_bg = '#052e16' if s['bien'] else '#450a0a'
    ind_color = '#22c55e' if s['bien'] else '#ef4444'
    ind_border = '#166534' if s['bien'] else '#991b1b'

    rem_color = '#22c55e' if s['remanente'] >= 0 else '#ef4444'
    rem_sign = '+' if s['remanente'] >= 0 else ''

    # Upcoming payments rows
    up_rows = ''
    if s['upcoming']:
        for u in s['upcoming']:
            icon = _TIPO_ICON.get(u['tipo'], '•')
            color = _TIPO_COLOR.get(u['tipo'], '#64748b')
            urgency = ('hoy' if u['days_away'] == 0
                       else 'mañana' if u['days_away'] == 1
                       else f"en {u['days_away']}d")
            badge_bg = '#450a0a' if u['days_away'] <= 1 else (
                '#422006' if u['days_away'] <= 3 else '#1e293b')
            badge_color = '#ef4444' if u['days_away'] <= 1 else (
                '#f59e0b' if u['days_away'] <= 3 else '#94a3b8')
            up_rows += f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9">
            <span style="color:{color}">{icon}</span>
            <strong style="margin-left:6px">{u['descripcion']}</strong>
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;
                     text-align:center;white-space:nowrap">
            <span style="background:{badge_bg};color:{badge_color};
                         padding:2px 8px;border-radius:99px;font-size:11px;
                         font-weight:700">{urgency}</span>
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;
                     text-align:right;font-weight:700;color:#1e293b">
            ${u['monto']:.2f}
          </td>
        </tr>"""
    else:
        up_rows = """<tr><td colspan="3" style="padding:16px 12px;
            color:#64748b;text-align:center">Sin vencimientos en los próximos 7 días</td></tr>"""

    ppto_row = ''
    if s['ppto_diario'] > 0:
        ppto_row = f"""
      <tr>
        <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;color:#64748b">
          Presupuesto/día (hasta {s['fecha_fin']})
        </td>
        <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;
                   text-align:right;font-weight:700">${s['ppto_diario']:.2f}</td>
      </tr>
      <tr>
        <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;color:#64748b">
          Proyección/día restante ({s['dias_restantes']}d)
        </td>
        <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;
                   text-align:right;font-weight:700;
                   color:{'#22c55e' if s['proyeccion_diaria'] <= s['ppto_diario'] else '#f59e0b'}">
          ${s['proyeccion_diaria']:.2f}
        </td>
      </tr>"""

    gasto_ayer_row = ''
    if s['gasto_ayer'] > 0:
        gasto_ayer_row = f"""
      <tr>
        <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;color:#64748b">
          Gasto ayer (BAC)
        </td>
        <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;
                   text-align:right;font-weight:700;color:#ef4444">
          −${s['gasto_ayer']:.2f}
        </td>
      </tr>"""

    now_str = datetime.now(tz=_TZ).strftime('%d/%m/%Y %H:%M')

    # Dashboard URL (Railway env var)
    railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
    dashboard_url = f"https://{railway_domain}" if railway_domain else ''

    # Botón dashboard (precomputado para evitar f-string anidado)
    if dashboard_url:
        dashboard_btn = (
            '<div style="padding:16px 28px;background:white;border:1px solid #e2e8f0;'
            'border-top:none;text-align:center">'
            f'<a href="{dashboard_url}" style="display:inline-block;background:#1e293b;'
            'color:white;text-decoration:none;padding:10px 28px;border-radius:8px;'
            'font-size:14px;font-weight:700">Ver Dashboard →</a>'
            '</div>'
        )
    else:
        dashboard_btn = ''

    # Agrícola row (precomputado para evitar f-string anidado)
    if s.get('agricola_saldo', 0) > 0:
        agricola_row = (
            '<tr>'
            '<td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;color:#64748b">'
            '\U0001f3e6 Agrícola Max Electrónico'
            '</td>'
            '<td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;'
            'text-align:right;font-weight:700;color:#a855f7">'
            f'${s["agricola_saldo"]:.2f}'
            '</td>'
            '</tr>'
        )
    else:
        agricola_row = ''

    return f"""<!DOCTYPE html>
<html lang="es">
<body style="margin:0;padding:20px;background:#f8fafc;font-family:Arial,sans-serif">
<div style="max-width:560px;margin:0 auto">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1e293b,#334155);
              border-radius:14px 14px 0 0;padding:22px 28px;color:white">
    <div style="font-size:28px;margin-bottom:4px">{indicador}</div>
    <h1 style="margin:0;font-size:20px;font-weight:700">Presupuesto del día</h1>
    <p style="margin:4px 0 0;opacity:.7;font-size:13px">{fecha_str} · El Salvador</p>
  </div>

  <!-- Indicador -->
  <div style="background:{ind_bg};border:1px solid {ind_border};
              padding:14px 20px;font-weight:700;color:{ind_color};font-size:14px">
    {indicador} {indicador_txt}
    {f' — remanente acumulado: <strong>{rem_sign}${abs(s["remanente"]):.2f}</strong>' if s['remanente'] != 0 else ''}
  </div>

  <!-- Saldos -->
  <div style="background:white;padding:20px 28px;border:1px solid #e2e8f0;border-top:none">
    <h3 style="margin:0 0 14px;color:#1e293b;font-size:14px;text-transform:uppercase;
               letter-spacing:.05em;color:#64748b">Saldos operativos</h3>
    <table style="width:100%;border-collapse:collapse">
      <tr>
        <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9">
          💳 Saldo BAC operativo
        </td>
        <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;
                   text-align:right;font-size:20px;font-weight:700;color:#22c55e">
          ${s['bac_saldo']:.2f}
        </td>
      </tr>
      {gasto_ayer_row}
      {ppto_row}
      <tr>
        <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;color:#64748b">
          💰 MultiMoney (ahorro)
        </td>
        <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;
                   text-align:right;font-weight:700;color:#0ea5e9">
          ${s['multimoney_saldo']:.2f}
        </td>
      </tr>
      {agricola_row}
      <tr>
        <td style="padding:14px 12px;font-weight:700">
          📊 Remanente acumulado
        </td>
        <td style="padding:14px 12px;text-align:right;font-size:18px;
                   font-weight:700;color:{rem_color}">
          {rem_sign}${abs(s['remanente']):.2f}
        </td>
      </tr>
    </table>
  </div>

  <!-- Próximos pagos -->
  <div style="background:white;padding:20px 28px;border:1px solid #e2e8f0;border-top:none">
    <h3 style="margin:0 0 14px;font-size:14px;text-transform:uppercase;
               letter-spacing:.05em;color:#64748b">Próximos 7 días</h3>
    <table style="width:100%;border-collapse:collapse">
      {up_rows}
    </table>
  </div>

  <!-- Dashboard link -->
  {dashboard_btn}

  <!-- Footer -->
  <div style="background:#1e293b;border-radius:0 0 14px 14px;
              padding:14px 28px;color:#64748b;font-size:11px;text-align:center">
    Generado automáticamente · {now_str} (El Salvador)
  </div>

</div>
</body>
</html>"""


def send_daily_summary():
    settings = load_settings()
    notify = settings.get('planner', {}).get('notify_email', '')
    if not notify:
        logger.warning("planner.notify_email no configurado")
        return

    s = build_summary()
    html = build_email_html(s)
    fecha_str = date.fromisoformat(s['today']).strftime('%d/%m/%Y')

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"{'✅' if s['bien'] else '⚠️'} Presupuesto del día — {fecha_str}"
    msg['From'] = 'me'
    msg['To'] = notify
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    service = get_service()
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    api_call_with_retry(
        service.users().messages().send(userId='me', body={'raw': raw}).execute
    )
    logger.info(f"Resumen diario enviado a {notify} — {'✅' if s['bien'] else '⚠️'}")


if __name__ == '__main__':
    # Preview: imprime el HTML sin enviar
    import sys
    s = build_summary()
    html = build_email_html(s)
    out = 'preview_daily_summary.html'
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Preview guardado en {out}")
    print(f"BAC: ${s['bac_saldo']:.2f} | Ppto/día: ${s['ppto_diario']:.2f} | "
          f"Remanente: ${s['remanente']:.2f} | MultiMoney: ${s['multimoney_saldo']:.2f}")
    print(f"Indicador: {'✅ Vas bien' if s['bien'] else '⚠️ Te pasaste'}")
    print(f"Próximos pagos ({len(s['upcoming'])}):")
    for u in s['upcoming']:
        print(f"  {u['fecha']} ({u['days_away']}d) — {u['descripcion']}: ${u['monto']:.2f}")
