"""Proceso de producción: dashboard en un hilo + jobs programados con `schedule`."""
import threading
import time
from datetime import datetime

import schedule

from gmailmcp import __version__
from gmailmcp.config import AppConfig
from gmailmcp.container import Container
from gmailmcp.jobs import JOBS, run_job
from gmailmcp.logging_setup import get_logger
from gmailmcp.web import create_app


def _run_dashboard(container: Container, logger) -> None:
    try:
        logger.info(f"Dashboard iniciando en http://0.0.0.0:{container.config.port}")
        create_app(container).run(host='0.0.0.0', port=container.config.port, debug=False,
                                  use_reloader=False)
    except Exception as e:
        logger.error(f"✗ dashboard falló: {e}", exc_info=True)


def setup_schedules(container: Container, logger) -> None:
    sched = container.settings.load()['schedule']
    cleanup_h = sched['cleanup_interval_hours']
    labeler_h = sched['labeler_interval_hours']
    financial_time = sched['financial_extractor_time']
    planner_time = sched.get('planner_time', '07:00')
    summary_time = sched.get('daily_summary_time', '14:00')

    def job(name):
        return lambda: run_job(JOBS[name], container, logger)

    schedule.every(cleanup_h).hours.do(job('cleanup'))
    schedule.every(labeler_h).hours.do(job('labeler'))
    schedule.every().day.at(financial_time).do(job('financial_extractor'))
    schedule.every().day.at(planner_time).do(job('payment_planner'))
    schedule.every().day.at(summary_time).do(job('daily_summary'))

    logger.info("Schedules configurados:")
    logger.info(f"  cleanup       → cada {cleanup_h}h")
    logger.info(f"  labeler       → cada {labeler_h}h")
    logger.info(f"  financiero    → diario a las {financial_time}")
    logger.info(f"  planner       → diario a las {planner_time} (activo días 13 y 28)")
    logger.info(f"  daily_summary → diario a las {summary_time} UTC (08:00 CST)")


def main() -> None:
    container = Container(AppConfig.from_env())
    logger = get_logger('orchestrator')
    logger.info("=" * 50)
    logger.info(f"Orquestador v{__version__} [{container.config.env}] iniciado — "
                f"{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 50)

    # create_app (en el hilo del dashboard) registra los avisos de configuración
    threading.Thread(target=_run_dashboard, args=(container, logger), daemon=True).start()

    for name in ('cleanup', 'labeler', 'financial_extractor'):
        run_job(JOBS[name], container, logger)

    setup_schedules(container, logger)
    logger.info("Scheduler activo. Ctrl+C para detener.")
    while True:
        schedule.run_pending()
        time.sleep(60)
