"""Rutas de sistema: health, estado del extractor, logs y memoria para Claude Chat."""
from datetime import datetime, timedelta

from flask import Blueprint, Response, jsonify, render_template, request

from gmailmcp import __version__
from gmailmcp.clock import BUSINESS_TZ, now_local
from gmailmcp.web.deps import container

bp = Blueprint('system', __name__)


@bp.get('/health')
def health():
    c = container()
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat(),
                    'version': __version__, 'env': c.config.env})


@bp.get('/api/status')
def status():
    c = container()
    mtime, count = c.transactions.stats()
    last_update = (datetime.fromtimestamp(mtime, tz=BUSINESS_TZ).strftime('%Y-%m-%d %H:%M')
                   if mtime is not None else None)
    h, m = map(int, c.settings.load()['schedule']['financial_extractor_time'].split(':'))
    now = now_local()
    next_run = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return jsonify({'last_update': last_update, 'total_records': count,
                    'next_update': next_run.strftime('%Y-%m-%d %H:%M')})


@bp.get('/logs')
def logs():
    log_dir = container().logs
    files = log_dir.files()
    if files is None:
        return render_template('logs.html', files=[], content='Sin logs todavía.', current='')
    selected = request.args.get('f', files[0] if files else '')
    return render_template('logs.html', files=files, content=log_dir.read(selected), current=selected)


@bp.get('/memory')
def memory():
    try:
        content = container().config.memory_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        content = '# claude_memory.md no encontrado'
    resp = Response(content, mimetype='text/plain; charset=utf-8')
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp
