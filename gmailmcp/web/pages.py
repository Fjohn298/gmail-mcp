"""Páginas HTML del dashboard (los datos los piden por JS a /api/*)."""
from flask import Blueprint, render_template

bp = Blueprint('pages', __name__)


@bp.route('/')
def index():
    return render_template('index.html')


@bp.route('/finanzas')
def finanzas():
    return render_template('finanzas.html')


@bp.route('/emails')
def emails():
    return render_template('emails.html')


@bp.route('/plan')
def plan():
    return render_template('plan.html')


@bp.route('/deudas')
def deudas():
    return render_template('deudas.html')


@bp.route('/fugas')
def fugas():
    return render_template('fugas.html')
