"""HTML del correo "Presupuesto del día" (presentación pura)."""
from datetime import date, datetime

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


def summary_subject(s: dict) -> str:
    fecha_str = date.fromisoformat(s['today']).strftime('%d/%m/%Y')
    return f"{'✅' if s['bien'] else '⚠️'} Presupuesto del día — {fecha_str}"


def render_summary_email(s: dict, now: datetime, dashboard_url: str = '') -> str:
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

    now_str = now.strftime('%d/%m/%Y %H:%M')

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
