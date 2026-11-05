"""Acceso de los blueprints al composition root de la app actual."""
from flask import current_app

from gmailmcp.container import Container


def container() -> Container:
    return current_app.extensions['container']
