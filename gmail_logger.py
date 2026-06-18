import logging
import os
from datetime import datetime

def setup_logger(name: str) -> logging.Logger:
    """Configura un logger que escribe a consola y a archivo con fecha."""
    os.makedirs('logs', exist_ok=True)
    date_str = datetime.now().strftime('%Y-%m-%d')
    log_file = f"logs/{name}_{date_str}.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setFormatter(fmt)
        logger.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    return logger
