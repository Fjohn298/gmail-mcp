"""Login opcional del dashboard (se activa con DASHBOARD_PASSWORD / REQUIRE_LOGIN)."""
import hmac

from flask import Blueprint, jsonify, redirect, render_template, request, session

from gmailmcp.config import AppConfig
from gmailmcp.web.deps import container

bp = Blueprint('auth', __name__)

# Rutas que deben seguir abiertas: healthcheck de Railway y la memoria que lee Claude Chat.
PUBLIC_ENDPOINTS = {'auth.login', 'auth.logout', 'system.health', 'system.memory', 'static'}


def _safe_next(target: str | None) -> str:
    """Solo rutas internas: evita redirecciones abiertas a otros dominios."""
    if target and target.startswith('/') and not target.startswith('//'):
        return target
    return '/'


def install_login_guard(app, config: AppConfig) -> None:
    @app.before_request
    def _require_login():
        if not config.require_login or request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if session.get('authed'):
            return None
        if request.path.startswith('/api/'):
            return jsonify({'error': 'no autenticado'}), 401
        return redirect(f"/login?next={request.full_path.rstrip('?')}")


@bp.route('/login', methods=['GET', 'POST'])
def login():
    config = container().config
    error = None
    if request.method == 'POST':
        given = request.form.get('password', '')
        if config.dashboard_password and hmac.compare_digest(given, config.dashboard_password):
            session.clear()
            session['authed'] = True
            return redirect(_safe_next(request.args.get('next')))
        error = 'Contraseña incorrecta'
    return render_template('login.html', error=error)


@bp.route('/logout')
def logout():
    session.clear()
    return redirect('/')
