"""Cálculos de calendario compartidos (antes duplicados en 5 lugares)."""
import calendar
from datetime import date

MONTHS_SHORT = ['', 'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
MONTHS_LONG = ['', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
               'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']


def _clamped(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def next_occurrence(day: int, today: date) -> date:
    """Próxima fecha (hoy incluido) con ese día del mes.

    Si el mes no tiene ese día (31 en noviembre), se usa su último día.
    """
    if today.day <= day:
        return _clamped(today.year, today.month, day)
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return _clamped(year, month, day)


def add_months(d: date, n: int) -> date:
    """Primer día del mes que está n meses después de d."""
    month = d.month - 1 + n
    return date(d.year + month // 12, month % 12 + 1, 1)


def month_label(d: date) -> str:
    return f"{MONTHS_SHORT[d.month]} {d.year}"
