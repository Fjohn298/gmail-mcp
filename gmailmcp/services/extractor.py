"""Extrae transacciones de los correos financieros y las guarda en el histórico CSV."""
import base64
import logging
import os
import re
from collections.abc import Callable
from datetime import date, datetime
from email.utils import parsedate_to_datetime

from gmailmcp.clock import today_local
from gmailmcp.gmail.ports import MessageReader
from gmailmcp.parsers.base import ParserRegistry
from gmailmcp.parsers.mime import get_body_and_attachments
from gmailmcp.parsers.pdf_statements import PdfParserRegistry
from gmailmcp.repositories.settings_repo import JsonSettingsRepository
from gmailmcp.repositories.state_repo import JsonBalanceRepository
from gmailmcp.repositories.transactions_repo import CsvTransactionRepository

# Etiquetas financieras (IDs reales de Gmail): Recibos y Banco Cuscatlán
FINANCIAL_LABEL_IDS = ('Label_3', 'Label_1834638960901538876')


def parse_message(message: dict, parsers: ParserRegistry, today: date) -> dict:
    """Mensaje completo de Gmail → registro de transacción (sin descripcion)."""
    headers = {h['name']: h['value'] for h in message['payload']['headers']}
    body, _ = get_body_and_attachments(message['payload'])
    if not body:
        body = message.get('snippet', '')
    parsed = parsers.parse(headers.get('From', ''), headers.get('Subject', ''), body)
    parsed['message_id'] = message['id']
    if not parsed.get('fecha_iso'):
        try:
            parsed['fecha_iso'] = parsedate_to_datetime(headers.get('Date', '')).date().isoformat()
        except Exception:
            parsed['fecha_iso'] = today.isoformat()
    return parsed


class PdfAttachmentStore:
    """Descarga adjuntos PDF una sola vez y devuelve su ruta local."""

    def __init__(self, mailbox: MessageReader, directory: str, logger: logging.Logger):
        self._mailbox = mailbox
        self._directory = directory
        self._logger = logger

    def fetch(self, message_id: str, attachment_id: str, filename: str) -> str:
        os.makedirs(self._directory, exist_ok=True)
        safe_name = re.sub(r'[^\w\-_\.]', '_', filename)
        path = os.path.join(self._directory, f"{message_id[:8]}_{safe_name}")
        if os.path.exists(path):
            return path
        att = self._mailbox.get_attachment(message_id, attachment_id)
        with open(path, 'wb') as f:
            f.write(base64.urlsafe_b64decode(att['data'] + '=='))
        self._logger.info(f"  PDF guardado: {path}")
        return path


class FinancialExtractor:
    def __init__(self, mailbox: MessageReader, parsers: ParserRegistry, pdf_parsers: PdfParserRegistry,
                 transactions: CsvTransactionRepository, balances: JsonBalanceRepository,
                 settings_repo: JsonSettingsRepository, logger: logging.Logger,
                 today: Callable[[], date] = today_local):
        self._mailbox = mailbox
        self._parsers = parsers
        self._pdf_parsers = pdf_parsers
        self._transactions = transactions
        self._balances = balances
        self._settings_repo = settings_repo
        self._logger = logger
        self._today = today

    def run(self) -> int:
        self._logger.info("=== Extracción financiera iniciada ===")
        start = datetime.now()
        settings = self._settings_repo.load()
        csv_path = settings['paths']['financial_csv']
        page_size = settings['gmail']['page_size']
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        pdfs = PdfAttachmentStore(self._mailbox, os.path.join(os.path.dirname(csv_path), 'pdfs'),
                                  self._logger)

        existing_ids = self._transactions.existing_message_ids()
        seen: set[str] = set()
        new_records: list[dict] = []
        # Una consulta por etiqueta: labelIds combina con AND y necesitamos OR
        for label_id in FINANCIAL_LABEL_IDS:
            for msg_id in self._message_ids(label_id, page_size):
                if msg_id in existing_ids or msg_id in seen:
                    continue
                seen.add(msg_id)
                new_records.extend(self._records_for(msg_id, existing_ids, pdfs))

        self._transactions.append(new_records)
        duration = (datetime.now() - start).total_seconds()
        self._logger.info(f"=== Extracción finalizada: {len(new_records)} registros nuevos "
                          f"en {csv_path} ({duration:.1f}s) ===")
        return len(new_records)

    def _message_ids(self, label_id: str, page_size: int):
        page_token = None
        while True:
            result = self._mailbox.list_messages(label_ids=[label_id], max_results=page_size,
                                                 page_token=page_token)
            messages = result.get('messages', [])
            if not messages:
                return
            yield from (m['id'] for m in messages)
            page_token = result.get('nextPageToken')
            if not page_token:
                return

    def _records_for(self, msg_id: str, existing_ids: set[str], pdfs: PdfAttachmentStore) -> list[dict]:
        m = self._mailbox.get_message(msg_id, format='full')
        parsed = parse_message(m, self._parsers, self._today())
        parsed['fuente'] = 'email'
        parsed['pdf_path'] = ''
        parsed['descripcion'] = m.get('snippet', '')[:150]
        if parsed.get('tipo') == 'login':     # inicios de sesión: no son movimientos
            return []

        records = [parsed]
        if parsed.get('tipo', '').startswith('estado_cuenta') and parsed.get('saldo'):
            saved = self._balances.save_statement_balance(parsed, self._today())
            if saved:
                self._logger.info(f"  Balance guardado: {saved['banco']} *{saved['tarjeta_ultimos4']} = "
                                  f"${saved['saldo_estado_cuenta']:.2f} ({saved['fecha']})")

        _, attachments = get_body_and_attachments(m['payload'])
        for fname, att_id, _mime in attachments:
            try:
                pdf_path = pdfs.fetch(msg_id, att_id, fname)
                for pr in self._pdf_parsers.extract(pdf_path, parsed['banco']):
                    pr['message_id'] = msg_id + '_pdf_' + fname[:8]
                    if pr['message_id'] not in existing_ids:
                        records.append(pr)
            except Exception as e:
                self._logger.error(f"  Error procesando PDF {fname}: {e}")
        return records
