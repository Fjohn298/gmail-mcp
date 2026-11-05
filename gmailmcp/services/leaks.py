"""Detector de fugas: categorías al alza, suscripciones activas y gastos sobre el promedio."""


def _monthly_categories(historial: list[dict]) -> dict[str, dict[str, float]]:
    monthly = {}
    for mes in historial:
        cats = {}
        for tx in mes.get('transacciones', []):
            cat = tx.get('categoria', 'Otros')
            cats[cat] = round(cats.get(cat, 0) + tx['monto'], 2)
        monthly[mes['periodo']] = cats
    return monthly


def _rising_trends(periods, monthly) -> list[dict]:
    """Promedio de los últimos 3 periodos vs los anteriores; solo alzas > 25%."""
    n = len(periods)
    if n < 3:
        return []
    recent = periods[max(0, n - 3):]
    earlier = periods[:max(1, n - 3)]
    all_cats = set().union(*monthly.values())
    trends = []
    for cat in all_cats:
        r_avg = sum(monthly[p].get(cat, 0) for p in recent) / len(recent)
        e_avg = sum(monthly[p].get(cat, 0) for p in earlier) / len(earlier) if earlier else 0
        if e_avg > 0 and r_avg > 10:
            var = round((r_avg - e_avg) / e_avg * 100, 1)
            if var > 25:
                trends.append({'categoria': cat, 'promedio_anterior': round(e_avg, 2),
                               'promedio_reciente': round(r_avg, 2), 'variacion_pct': var})
    trends.sort(key=lambda x: -x['variacion_pct'])
    return trends


def _subscriptions(historial, periods) -> list[dict]:
    recent_periods = periods[-3:] if len(periods) >= 3 else periods
    subs = {}
    for mes in historial:
        if mes['periodo'] not in recent_periods:
            continue
        for tx in mes.get('transacciones', []):
            if tx.get('tipo') != 'fijo':
                continue
            desc = tx['descripcion']
            sub = subs.setdefault(desc, {'descripcion': desc, 'meses_activos': 0, 'ultimo_monto': 0,
                                         'cancelar': False, 'categoria': tx.get('categoria', 'Otros')})
            sub['meses_activos'] += 1
            sub['ultimo_monto'] = tx['monto']
            if tx.get('cancelar'):
                sub['cancelar'] = True
    return sorted(subs.values(), key=lambda x: (-int(x['cancelar']), -x['ultimo_monto']))


def _over_average(periods, monthly) -> list[dict]:
    """Categorías del último periodo > 130% de su promedio histórico."""
    n = len(periods)
    if n < 2:
        return []
    last_p = periods[-1]
    over = []
    for cat, amt in monthly[last_p].items():
        hist_avg = sum(monthly[p].get(cat, 0) for p in periods[:-1]) / (n - 1)
        if amt > hist_avg * 1.3 and amt > 15 and hist_avg > 0:
            over.append({'categoria': cat, 'mes_actual': amt, 'mes_actual_label': last_p,
                         'promedio_historico': round(hist_avg, 2),
                         'variacion_pct': round((amt - hist_avg) / hist_avg * 100, 1)})
    over.sort(key=lambda x: -x['variacion_pct'])
    return over


def detect_leaks(settings: dict) -> dict:
    historial = settings.get('amex_historial', [])
    periods = [m['periodo'] for m in historial]
    monthly = _monthly_categories(historial)
    return {
        'periodos': periods,
        'suscripciones': _subscriptions(historial, periods),
        'tendencias_al_alza': _rising_trends(periods, monthly),
        'sobre_historico': _over_average(periods, monthly),
        'monthly_cats': monthly,
    }
