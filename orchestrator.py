import os
import time
import threading
import schedule
from datetime import datetime
from gmail_logger import setup_logger
from gmail_auth import load_settings

logger = setup_logger('orchestrator')

def run_cleanup():
    try:
        from cleanup import cleanup
        logger.info("▶ Ejecutando cleanup...")
        n = cleanup()
        logger.info(f"✓ cleanup: {n} threads eliminados")
    except Exception as e:
        logger.error(f"✗ cleanup falló: {e}", exc_info=True)

def run_labeler():
    try:
        from labeler import label_messages
        logger.info("▶ Ejecutando labeler...")
        n = label_messages()
        logger.info(f"✓ labeler: {n} mensajes etiquetados")
    except Exception as e:
        logger.error(f"✗ labeler falló: {e}", exc_info=True)

def run_financial_extractor():
    try:
        from financial_extractor import extract_financial_data
        logger.info("▶ Ejecutando financial_extractor...")
        n = extract_financial_data()
        logger.info(f"✓ financial_extractor: {n} registros nuevos")
    except Exception as e:
        logger.error(f"✗ financial_extractor falló: {e}", exc_info=True)

def run_dashboard():
    try:
        from dashboard import app
        port = int(os.environ.get('PORT', 5000))
        logger.info(f"Dashboard iniciando en http://0.0.0.0:{port}")
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"✗ dashboard falló: {e}", exc_info=True)

def setup_schedules():
    settings = load_settings()
    cleanup_h = settings['schedule']['cleanup_interval_hours']
    labeler_h = settings['schedule']['labeler_interval_hours']
    financial_time = settings['schedule']['financial_extractor_time']

    schedule.every(cleanup_h).hours.do(run_cleanup)
    schedule.every(labeler_h).hours.do(run_labeler)
    schedule.every().day.at(financial_time).do(run_financial_extractor)

    logger.info(f"Schedules configurados:")
    logger.info(f"  cleanup     → cada {cleanup_h}h")
    logger.info(f"  labeler     → cada {labeler_h}h")
    logger.info(f"  financiero  → diario a las {financial_time}")

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info(f"Orquestador iniciado — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 50)

    # Dashboard en hilo separado (no bloquea el scheduler)
    dash_thread = threading.Thread(target=run_dashboard, daemon=True)
    dash_thread.start()

    # Ejecución inicial al arrancar
    run_cleanup()
    run_labeler()
    run_financial_extractor()

    setup_schedules()

    logger.info("Scheduler activo. Ctrl+C para detener.")
    while True:
        schedule.run_pending()
        time.sleep(60)
