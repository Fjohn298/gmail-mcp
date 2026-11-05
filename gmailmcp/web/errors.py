"""Manejo de errores centralizado: reemplaza los ~30 try/except repetidos en las rutas."""
import logging

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException


def register_error_handlers(app: Flask, logger: logging.Logger, expose_details: bool) -> None:
    @app.errorhandler(Exception)
    def _unhandled(e: Exception):
        if isinstance(e, HTTPException):
            return e
        logger.error(f"Error en {request.method} {request.path}: {e}", exc_info=True)
        # En desarrollo se muestra el detalle; en producción no se filtran internos al cliente.
        message = str(e) if expose_details else 'error interno'
        return jsonify({'error': message}), 500
