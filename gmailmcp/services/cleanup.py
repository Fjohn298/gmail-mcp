"""Manda a papelera los hilos de remitentes de spam, sin tocar los financieros."""
import logging
from datetime import datetime
from typing import Protocol

from gmailmcp.gmail.ports import ThreadReader, ThreadTrasher
from gmailmcp.repositories.settings_repo import JsonSettingsRepository


class CleanupMailbox(ThreadReader, ThreadTrasher, Protocol):
    """Lo único que cleanup necesita de Gmail."""


def load_spam_senders(path: str) -> list[str]:
    senders = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                senders.append(line)
    return senders


def build_query(senders: list[str]) -> str:
    froms = ' OR '.join([f'from:{s}' for s in senders])
    return f'({froms}) in:inbox'


class CleanupService:
    def __init__(self, mailbox: CleanupMailbox, settings_repo: JsonSettingsRepository,
                 logger: logging.Logger):
        self._mailbox = mailbox
        self._settings_repo = settings_repo
        self._logger = logger

    def _collect_thread_ids(self, query: str, page_size: int) -> list[str]:
        """Lista completa antes de modificar nada.

        Volver a pedir la primera página tras cada borrado repetía para siempre los
        hilos protegidos que no se borran (bucle infinito).
        """
        ids, page_token = [], None
        while True:
            result = self._mailbox.list_threads(query=query, max_results=page_size, page_token=page_token)
            ids.extend(t['id'] for t in result.get('threads', []))
            page_token = result.get('nextPageToken')
            if not page_token:
                return ids

    def run(self) -> int:
        self._logger.info("=== Limpieza iniciada ===")
        start = datetime.now()
        settings = self._settings_repo.load()
        page_size = settings['gmail']['page_size']
        protected = set(settings['gmail']['protected_labels'])

        senders = load_spam_senders(settings['paths']['spam_senders_file'])
        if not senders:
            self._logger.warning("spam_senders.txt vacío, nada que limpiar.")
            return 0

        deleted = 0
        sender_counts: dict[str, int] = {}
        for i, thread_id in enumerate(self._collect_thread_ids(build_query(senders), page_size), 1):
            thread = self._mailbox.get_thread(thread_id, format='metadata',
                                              metadata_headers=['From', 'X-Gmail-Labels'])
            first = thread.get('messages', [{}])[0]
            if any(lbl in protected for lbl in first.get('labelIds', [])):
                self._logger.warning(f"Saltando thread {thread_id} — tiene etiqueta protegida")
                continue
            headers = first['payload'].get('headers', [])
            from_header = next((h['value'] for h in headers if h['name'] == 'From'), 'desconocido')
            self._mailbox.trash_thread(thread_id)
            deleted += 1
            sender_counts[from_header] = sender_counts.get(from_header, 0) + 1
            if i % page_size == 0:
                self._logger.info(f"   {deleted} threads en papelera hasta ahora...")

        duration = (datetime.now() - start).seconds
        self._logger.info(f"=== Limpieza finalizada: {deleted} eliminados en {duration}s ===")
        if sender_counts:
            self._logger.info("Top remitentes eliminados:")
            for sender, count in sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                self._logger.info(f"  {count:3d}x  {sender}")
        return deleted
