"""Única fuente de "ahora" en hora de negocio (El Salvador)."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

BUSINESS_TZ = ZoneInfo("America/El_Salvador")


def now_local() -> datetime:
    return datetime.now(tz=BUSINESS_TZ)


def today_local() -> date:
    return now_local().date()
