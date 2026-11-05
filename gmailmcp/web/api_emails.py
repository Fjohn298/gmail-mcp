"""API de la pestaña Correos (lee Gmail en vivo)."""
from flask import Blueprint, jsonify

from gmailmcp.services import email_insights
from gmailmcp.web.deps import container

bp = Blueprint('emails', __name__, url_prefix='/api/emails')


def _label_names() -> dict:
    return email_insights.load_label_names(container().settings.load()['paths']['label_rules_file'])


@bp.get('/recent')
def recent():
    return jsonify(email_insights.recent_emails(container().gmail('dashboard'), _label_names()))


@bp.get('/unlabeled')
def unlabeled():
    return jsonify(email_insights.unlabeled_emails(container().gmail('dashboard')))


@bp.get('/label-stats')
def label_stats():
    return jsonify(email_insights.label_stats(container().gmail('dashboard'), _label_names()))
