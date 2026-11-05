"""Resumen diario de presupuesto: cálculo (puro) y envío por correo."""
import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta

from gmailmcp.clock import now_local
from gmailmcp.dates import next_occurrence
from gmailmcp.notifications.notifier import EmailNotifier
from gmailmcp.notifications.summary_email import render_summary_email, summary_subject
from gmailmcp.repositories.settings_repo import JsonSettingsRepository


def _upcoming(descripcion: str, nxt: date, today: date, monto: float, tipo: str) -> dict:
    return {'descripcion': descripcion, 'fecha': nxt.isoformat(), 'days_away': (nxt - today).days,
            'monto': monto, 'tipo': tipo}


def _within_week(nxt: date, today: date) -> bool:
    return 0 <= (nxt - today).days <= 7


def build_summary(settings: dict, today: date) -> dict:
    planner = settings.get('planner', {})

    # --- BAC presupuesto ---
    bac = next((c for c in settings.get('otras_cuentas', []) if c.get('nombre') == 'Débito BAC'), {})
    bac_saldo = bac.get('saldo', 0)
    ppto = bac.get('presupuesto', {})

    ppto_diario = remanente = gasto_ayer = dias_restantes = proyeccion_diaria = 0
    fecha_fin_str = ''
    if ppto:
        fecha_inicio = date.fromisoformat(ppto['fecha_inicio'])
        fecha_fin = date.fromisoformat(ppto['fecha_fin'])
        fecha_fin_str = ppto['fecha_fin']
        ppto_diario = round(ppto['saldo_inicio'] / ppto['dias_total'], 2)
        dias_transcurridos = max(0, (today - fecha_inicio).days)
        dias_restantes = max(0, (fecha_fin - today).days)

        movimientos = bac.get('movimientos', [])
        ayer_str = (today - timedelta(days=1)).isoformat()
        gasto_periodo = round(sum(m['monto'] for m in movimientos
                                  if m['tipo'] == 'egreso' and m['fecha'] >= ppto['fecha_inicio']), 2)
        gasto_ayer = round(sum(m['monto'] for m in movimientos
                               if m['tipo'] == 'egreso' and m['fecha'] == ayer_str), 2)
        remanente = round(round(ppto_diario * dias_transcurridos, 2) - gasto_periodo, 2)
        proyeccion_diaria = round(bac_saldo / dias_restantes, 2) if dias_restantes > 0 else 0

    # --- MultiMoney ---
    multimoney_saldo = next((f.get('saldo', 0) for f in settings.get('fondos_ahorro', [])
                             if 'MultiMoney' in f.get('nombre', '')), 0)

    # --- Agrícola Max Electrónico ---
    agricola_saldo = next(
        (c.get('saldo', 0) for c in settings.get('otras_cuentas', [])
         if 'Agrícola' in c.get('nombre', '') or 'Agricola' in c.get('nombre', '')), 0)

    # --- Próximos 7 días ---
    upcoming = []
    for c in planner.get('cards', []):
        if c.get('min_pago', 0) <= 0 and c.get('balance', 0) <= 0:
            continue
        nxt = next_occurrence(c['fecha_pago_dia'], today)
        if _within_week(nxt, today):
            upcoming.append(_upcoming(f"{c['name']} ****{c['last4']}", nxt, today,
                                      c.get('min_pago', 0), 'tarjeta'))
    for fi in settings.get('intrafinanciamientos', []):
        if fi.get('saldo_actual', 0) <= 0:
            continue
        nxt = next_occurrence(fi.get('fecha_pago_dia', 1), today)
        if _within_week(nxt, today):
            upcoming.append(_upcoming(fi['descripcion'], nxt, today, fi['cuota_mensual'],
                                      'intrafinanciamiento'))
    for p in settings.get('prestamos', []):
        nxt = next_occurrence(p.get('fecha_pago_dia', 1), today)
        if _within_week(nxt, today):
            upcoming.append(_upcoming(p['nombre'], nxt, today, p['cuota_mensual'], 'prestamo'))
    for e in planner.get('obligaciones_extra', []):
        nxt = next_occurrence(e.get('fecha_pago_dia', 1), today)
        if _within_week(nxt, today):
            upcoming.append(_upcoming(e['descripcion'], nxt, today, e['monto_mensual'], 'extra'))
    for f in settings.get('fondos_ahorro', []):
        for dia in f.get('dias_deposito', []):
            nxt = next_occurrence(dia, today)
            if _within_week(nxt, today):
                upcoming.append(_upcoming(f"Depósito {f['nombre']}", nxt, today,
                                          f.get('deposito_quincena', 0), 'ahorro'))
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


class DailySummaryService:
    def __init__(self, settings_repo: JsonSettingsRepository, notifier: EmailNotifier,
                 logger: logging.Logger, dashboard_url: str = '',
                 now: Callable[[], datetime] = now_local):
        self._settings_repo = settings_repo
        self._notifier = notifier
        self._logger = logger
        self._dashboard_url = dashboard_url
        self._now = now

    def render(self) -> tuple[dict, str]:
        now = self._now()
        summary = build_summary(self._settings_repo.load(), now.date())
        return summary, render_summary_email(summary, now, self._dashboard_url)

    def send(self) -> None:
        notify = self._settings_repo.load().get('planner', {}).get('notify_email', '')
        if not notify:
            self._logger.warning("planner.notify_email no configurado")
            return
        summary, html = self.render()
        self._notifier.send_html(notify, summary_subject(summary), html)
        self._logger.info(f"Resumen diario enviado a {notify} — {'✅' if summary['bien'] else '⚠️'}")
