"""Jobs ejecutables: los usa el scheduler y también se pueden lanzar a mano.

    python -m gmailmcp.jobs cleanup
    python -m gmailmcp.jobs planner --force
    python -m gmailmcp.jobs preview-summary
"""
import argparse
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass

from gmailmcp.config import AppConfig
from gmailmcp.container import Container
from gmailmcp.logging_setup import get_logger


@dataclass(frozen=True)
class Job:
    name: str
    run: Callable[[Container], int | None]
    success_message: Callable[[int | None], str | None]
    announce: bool = True


JOBS: dict[str, Job] = {job.name: job for job in (
    Job('cleanup', lambda c: c.cleanup_service().run(),
        lambda n: f"✓ cleanup: {n} threads eliminados"),
    Job('labeler', lambda c: c.labeler_service().run(),
        lambda n: f"✓ labeler: {n} mensajes etiquetados"),
    Job('financial_extractor', lambda c: c.extractor_service().run(),
        lambda n: f"✓ financial_extractor: {n} registros nuevos"),
    # El planner corre a diario pero solo actúa los días configurados (13 y 28).
    Job('payment_planner', lambda c: c.planner_service().run(),
        lambda n: "✓ payment_planner: plan generado y enviado" if n else None, announce=False),
    Job('daily_summary', lambda c: c.summary_service().send(),
        lambda _: "✓ daily_summary: resumen enviado"),
)}


def run_job(job: Job, container: Container, logger: logging.Logger) -> bool:
    """Ejecuta un job registrando el resultado. Devuelve False si falló (nunca relanza)."""
    try:
        if job.announce:
            logger.info(f"▶ Ejecutando {job.name}...")
        message = job.success_message(job.run(container))
        if message:
            logger.info(message)
        return True
    except Exception as e:
        logger.error(f"✗ {job.name} falló: {e}", exc_info=True)
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m gmailmcp.jobs')
    parser.add_argument('job', choices=[*JOBS, 'preview-summary'])
    parser.add_argument('--force', action='store_true', help='planner: generar aunque no sea día 13/28')
    args = parser.parse_args(argv)

    container = Container(AppConfig.from_env())
    logger = get_logger('jobs')
    for warning in container.config.warnings():
        logger.warning(warning)

    if args.job == 'preview-summary':
        summary, html = container.summary_service().render()
        with open('preview_daily_summary.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"Preview guardado en preview_daily_summary.html — {'✅' if summary['bien'] else '⚠️'}")
        return 0
    if args.job == 'payment_planner' and args.force:
        ok = run_job(Job('payment_planner', lambda c: c.planner_service().run(force=True),
                         JOBS['payment_planner'].success_message), container, logger)
    else:
        ok = run_job(JOBS[args.job], container, logger)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
