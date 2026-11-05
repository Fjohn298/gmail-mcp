"""Application factory del dashboard."""
import logging

from flask import Flask

from gmailmcp.config import AppConfig
from gmailmcp.container import Container
from gmailmcp.logging_setup import get_logger
from gmailmcp.web import api_emails, api_finance, api_plan, auth, pages, system
from gmailmcp.web.errors import register_error_handlers


def create_app(container: Container | None = None) -> Flask:
    container = container or Container(AppConfig.from_env())
    config = container.config

    app = Flask(__name__)
    app.secret_key = config.flask_secret
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=config.is_production)
    app.extensions['container'] = container

    logger = get_logger('dashboard')
    app.logger.handlers = logger.handlers
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = False
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.handlers = logger.handlers
    werkzeug_logger.propagate = False
    for warning in config.warnings():
        logger.warning(warning)

    for module in (auth, pages, system, api_finance, api_plan, api_emails):
        app.register_blueprint(module.bp)
    auth.install_login_guard(app, config)
    register_error_handlers(app, logger, expose_details=not config.is_production)
    return app
