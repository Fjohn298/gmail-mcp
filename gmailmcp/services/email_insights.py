"""Consultas de solo lectura sobre el buzón para la pestaña "Correos" y la actividad del plan."""
import json
import os
from collections.abc import Callable
from datetime import date

from gmailmcp.classification import TransactionClassifier
from gmailmcp.gmail.ports import LabelCatalog, MessageReader
from gmailmcp.parsers.base import ParserRegistry
from gmailmcp.services.extractor import FINANCIAL_LABEL_IDS, parse_message

SYSTEM_LABELS = {'INBOX', 'SENT', 'DRAFT', 'SPAM', 'TRASH', 'STARRED', 'IMPORTANT', 'UNREAD',
                 'CATEGORY_PERSONAL', 'CATEGORY_SOCIAL', 'CATEGORY_PROMOTIONS',
                 'CATEGORY_UPDATES', 'CATEGORY_FORUMS'}


def load_label_names(rules_path: str) -> dict[str, str]:
    """{label_id: categoría} desde label_rules.json, para mostrar nombres legibles."""
    if not os.path.exists(rules_path):
        return {}
    with open(rules_path, encoding='utf-8') as f:
        raw = json.load(f)
    return {data['_label_id']: cat for cat, data in raw.items()
            if not cat.startswith('_') and '_label_id' in data}


def _headers(message: dict) -> dict:
    return {x['name']: x['value'] for x in message['payload']['headers']}


def _summaries(mailbox: MessageReader, query: str, max_results: int) -> list[tuple[dict, dict]]:
    result = mailbox.list_messages(query=query, max_results=max_results)
    out = []
    for msg in result.get('messages', []):
        m = mailbox.get_message(msg['id'], format='metadata', metadata_headers=['From', 'Subject', 'Date'])
        out.append((msg, m))
    return out


def recent_emails(mailbox: MessageReader, label_names: dict[str, str]) -> list[dict]:
    emails = []
    for msg, m in _summaries(mailbox, 'in:inbox newer_than:7d', 30):
        h = _headers(m)
        emails.append({'id': msg['id'], 'from': h.get('From', ''), 'subject': h.get('Subject', ''),
                       'date': h.get('Date', ''),
                       'labels': [label_names.get(lbl, lbl) for lbl in m.get('labelIds', [])
                                  if lbl not in SYSTEM_LABELS],
                       'snippet': m.get('snippet', '')[:100]})
    return emails


def unlabeled_emails(mailbox: MessageReader) -> list[dict]:
    emails = []
    for msg, m in _summaries(mailbox, 'in:inbox has:nouserlabels', 20):
        h = _headers(m)
        emails.append({'id': msg['id'], 'from': h.get('From', ''), 'subject': h.get('Subject', ''),
                       'date': h.get('Date', ''), 'snippet': m.get('snippet', '')[:100]})
    return emails


def label_stats(catalog: LabelCatalog, label_names: dict[str, str]) -> list[dict]:
    stats = [{'id': lbl['id'], 'name': label_names.get(lbl['id'], lbl['name']),
              'messages_total': lbl.get('messagesTotal', 0), 'messages_unread': lbl.get('messagesUnread', 0)}
             for lbl in catalog.list_labels() if lbl['type'] == 'user']
    return sorted(stats, key=lambda x: x['messages_total'], reverse=True)


def recent_activity(mailbox: MessageReader, parsers: ParserRegistry, classifier: TransactionClassifier,
                    settings: dict, days: int, today: Callable[[], date]) -> list[dict]:
    """Transacciones recientes leídas directo de Gmail (no del CSV, que es efímero) y clasificadas."""
    seen, records = set(), []
    for label_id in FINANCIAL_LABEL_IDS:
        result = mailbox.list_messages(label_ids=[label_id], query=f'newer_than:{days}d', max_results=50)
        for msg in result.get('messages', []):
            if msg['id'] in seen:
                continue
            seen.add(msg['id'])
            m = mailbox.get_message(msg['id'], format='full')
            parsed = parse_message(m, parsers, today())
            if parsed.get('tipo') == 'login':
                continue
            parsed['descripcion'] = m.get('snippet', '')[:200]
            parsed.update(classifier.classify(parsed, settings))
            records.append(parsed)
    records.sort(key=lambda r: r.get('fecha_iso', ''), reverse=True)
    return records
