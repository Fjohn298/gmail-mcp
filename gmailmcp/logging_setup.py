"""Loggers con salida a consola y a logs/<nombre>_<fecha>.log en hora local."""
import logging
import os
from datetime import datetime

from gmailmcp.clock import BUSINESS_TZ

LOG_DIR = "logs"


class _TZFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=BUSINESS_TZ)
        return dt.strftime(datefmt or '%Y-%m-%d %H:%M:%S')


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    os.makedirs(LOG_DIR, exist_ok=True)
    date_str = datetime.now(tz=BUSINESS_TZ).strftime('%Y-%m-%d')
    fmt = _TZFormatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    fh = logging.FileHandler(os.path.join(LOG_DIR, f"{name}_{date_str}.log"), encoding='utf-8')
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger
