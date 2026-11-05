"""Dashboard solo, para desarrollo local: `python dashboard.py`.

En producción el dashboard lo levanta orchestrator.py. Para un servidor WSGI:
    gunicorn "gmailmcp.web:create_app()"
"""
from gmailmcp.web import create_app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=app.extensions['container'].config.port, debug=False)
