import os
import re
import csv
import base64
import json
from datetime import datetime, date
from gmail_auth import get_service, api_call_with_retry, load_settings
from gmail_logger import setup_logger

logger = setup_logger('financial_extractor')


def save_balance(settings: dict, record: dict):
    saldo = record.get('saldo', '')
    if not saldo:
        return
    try:
        saldo_float = float(str(saldo).replace(',', ''))
    except ValueError:
        return
    data_dir = settings['paths']['data_dir']
    os.makedirs(data_dir, exist_ok=True)
    balances_path = os.path.join(data_dir, 'balances.json')
    balances = {}
    if os.path.exists(balances_path):
        with open(balances_path, 'r', encoding='utf-8') as f:
            try:
                balances = json.load(f)
            except json.JSONDecodeError:
                pass
    banco = record.get('banco', 'Desconocido')
    tarjeta = record.get('tarjeta_ultimos4', 'xxxx')
    key = f"{banco}_{tarjeta}"
    fecha = record.get('fecha_iso', date.today().isoformat())
    if balances.get(key, {}).get('fecha', '') <= fecha:
        balances[key] = {
            'banco': banco, 'tarjeta_ultimos4': tarjeta,
            'saldo_estado_cuenta': saldo_float, 'fecha': fecha,
            'message_id': record.get('message_id', '')
        }
        with open(balances_path, 'w', encoding='utf-8') as f:
            json.dump(balances, f, ensure_ascii=False, indent=2)
        logger.info(f"  Balance guardado: {banco} *{tarjeta} = ${saldo_float:.2f} ({fecha})")

# Etiquetas financieras (IDs reales)
FINANCIAL_LABEL_IDS = ['Label_3', 'Label_1834638960901538876']

CSV_COLUMNS = [
    'fecha_iso', 'banco', 'tipo', 'tarjeta_tipo', 'tarjeta_ultimos4',
    'monto', 'moneda', 'comercio', 'descripcion',
    'fuente', 'pdf_path', 'message_id', 'revisado'
]

# ── Patrones por banco ──────────────────────────────────────────────────────

def parse_bac(body: str, from_header: str) -> dict:
    """BAC Credomatic — alertas de compra y transferencias."""
    r = {'banco': 'BAC Credomatic', 'moneda': 'USD', 'revisado': 'false'}

    # Tipo de tarjeta y últimos 4
    m = re.search(r'tarjeta (MASTERCARD|AMEX|VISA)\s+terminada en (\d{4})', body, re.IGNORECASE)
    if m:
        r['tarjeta_tipo'] = m.group(1)
        r['tarjeta_ultimos4'] = m.group(2)

    # Comercio y monto — aparecen en líneas separadas después de "Monto\n\n"
    m = re.search(r'Comercio\s+Monto\s+([\w*\s\-\.]+?)\s+([\d]+\.[\d]{2})\s', body, re.DOTALL)
    if m:
        r['comercio'] = m.group(1).strip()
        r['monto'] = m.group(2)
    else:
        # Fallback: buscar cualquier monto dólar
        m2 = re.search(r'(\d+\.\d{2})', body)
        if m2:
            r['monto'] = m2.group(1)

    # Fecha de la transacción
    m = re.search(r'(\d{4}/\d{2}/\d{2})-(\d{2}:\d{2}:\d{2})', body)
    if m:
        try:
            r['fecha_iso'] = datetime.strptime(m.group(1), '%Y/%m/%d').date().isoformat()
        except ValueError:
            pass

    # Tipo de movimiento
    if re.search(r'compra', body, re.IGNORECASE):
        r['tipo'] = 'compra'
    elif re.search(r'transferencia', body, re.IGNORECASE):
        r['tipo'] = 'transferencia'
        # Para transferencias el monto está en el snippet "por USD X.XX"
        m2 = re.search(r'por USD\s*([\d.]+)', body, re.IGNORECASE)
        if m2:
            r['monto'] = m2.group(1)
    elif re.search(r'pago.*servicio', body, re.IGNORECASE):
        r['tipo'] = 'pago_servicio'

    return r

def parse_cuscatlan(body: str, subject: str) -> dict:
    """Banco Cuscatlán — débitos, abonos, Transfer365, pagos tarjeta."""
    r = {'banco': 'Banco Cuscatlán', 'moneda': 'USD', 'revisado': 'false'}

    # Cuenta / tarjeta
    m = re.search(r'cuenta [X]+(\d{4})', body, re.IGNORECASE)
    if m:
        r['tarjeta_ultimos4'] = m.group(1)

    # Monto — formatos: "por USD220.92", "por USD 20.00", "USD 20.00"
    m = re.search(r'USD\s*([\d,]+\.?\d*)', body, re.IGNORECASE)
    if m:
        r['monto'] = m.group(1).replace(',', '')

    # Fecha
    m = re.search(r'el día (\d{4}-\d{2}-\d{2})', body)
    if m:
        r['fecha_iso'] = m.group(1)
    else:
        m = re.search(r'(\d{4}-\d{2}-\d{2})', body)
        if m:
            r['fecha_iso'] = m.group(1)

    # Tipo
    subj_lower = subject.lower()
    body_lower = body.lower()
    if 'débito' in body_lower or 'cargo' in subj_lower or 'debito' in subj_lower:
        r['tipo'] = 'debito'
    elif 'crédito' in body_lower or 'abono' in body_lower or 'deposito' in subj_lower:
        r['tipo'] = 'credito'
    elif 'transfer365' in body_lower or 'transfer365' in subj_lower:
        r['tipo'] = 'transfer365'
    elif 'pago de tarjeta' in body_lower:
        r['tipo'] = 'pago_tarjeta'
        m2 = re.search(r'pago exitoso.*?(\d+\.\d{2})', body, re.IGNORECASE | re.DOTALL)
        if m2:
            r['monto'] = m2.group(1)
    elif 'inicio de sesión' in subj_lower or 'sesión' in body_lower:
        r['tipo'] = 'login'
        r['monto'] = ''  # no es transacción monetaria

    return r

def parse_agricola(body: str, subject: str) -> dict:
    """Banco Agrícola — transferencias, inicio de sesión, estado de cuenta."""
    r = {'banco': 'Banco Agrícola', 'moneda': 'USD', 'revisado': 'false'}

    # Estado de cuenta (email de aviso, el detalle está en el PDF)
    if 'estado de cuenta' in subject.lower():
        r['tipo'] = 'estado_cuenta'
        m = re.search(r'XXXX-XXXX-XXXX-(\d{4})', body)
        if m:
            r['tarjeta_ultimos4'] = m.group(1)
        m2 = re.search(r'Pago m[íi]nimo.*?\$([\d.]+)', body, re.IGNORECASE | re.DOTALL)
        if m2:
            r['monto'] = m2.group(1)
            r['tipo'] = 'estado_cuenta_pago_minimo'
        m3 = re.search(r'Fecha de corte.*?(\d{2}/\d{2}/\d{4})', body, re.IGNORECASE | re.DOTALL)
        if m3:
            try:
                r['fecha_iso'] = datetime.strptime(m3.group(1), '%d/%m/%Y').date().isoformat()
            except ValueError:
                pass
        # Intentar extraer saldo actual
        for pat in [
            r'[Ss]aldo\s+(?:[Aa]ctual|[Tt]otal|[Aa]l\s+[Cc]orte)\s*[:\$]?\s*([\d,]+\.?\d*)',
            r'[Tt]otal\s+a\s+[Pp]agar\s*[:\$]?\s*([\d,]+\.?\d*)',
            r'[Ss]aldo\s+[Cc]ontado\s*[:\$]?\s*([\d,]+\.?\d*)',
        ]:
            m_saldo = re.search(pat, body, re.IGNORECASE | re.DOTALL)
            if m_saldo:
                r['saldo'] = m_saldo.group(1).replace(',', '')
                break
        return r

    # Transfer365
    if 'transfer365' in subject.lower() or 'transfer365' in body.lower():
        r['tipo'] = 'transfer365'
        m = re.search(r'([\d,]+\.?\d*)\s*USD', body)
        if not m:
            m = re.search(r'\$([\d,]+\.?\d*)', body)
        if m:
            r['monto'] = m.group(1).replace(',', '')

    # Transferencia a terceros
    elif 'transferencia' in body.lower():
        r['tipo'] = 'transferencia'

    # Login
    elif 'inicio de sesión' in subject.lower():
        r['tipo'] = 'login'
        r['monto'] = ''

    # Fecha
    m = re.search(r'(\d{2}-\d{2}-\d{4})', body)
    if m:
        try:
            r['fecha_iso'] = datetime.strptime(m.group(1), '%d-%m-%Y').date().isoformat()
        except ValueError:
            pass

    return r

def parse_anthropic(body: str) -> dict:
    r = {'banco': 'Anthropic', 'tipo': 'suscripcion', 'comercio': 'Anthropic',
         'moneda': 'USD', 'revisado': 'false'}
    m = re.search(r'\$([\d.]+)', body)
    if m:
        r['monto'] = m.group(1)
    m2 = re.search(r'\*+(\d{4})', body)
    if m2:
        r['tarjeta_ultimos4'] = m2.group(1)
    return r

def parse_payway(body: str, subject: str) -> dict:
    """Payway — notificaciones de pago de servicios (ej. DELSUR, ANDA)."""
    r = {'banco': 'Payway', 'tipo': 'pago_servicio', 'moneda': 'USD', 'revisado': 'false'}
    m = re.search(r'notificaci[oó]n de pago\s*[-–]\s*(.+)', subject, re.IGNORECASE)
    if m:
        r['comercio'] = m.group(1).strip()
    m2 = re.search(r'\$([\d,]+\.?\d*)', body)
    if m2:
        r['monto'] = m2.group(1).replace(',', '')
    m3 = re.search(r'(\d{4}-\d{2}-\d{2})', body)
    if m3:
        r['fecha_iso'] = m3.group(1)
    return r


def parse_generic(body: str, from_header: str) -> dict:
    r = {'banco': 'Desconocido', 'revisado': 'false', 'moneda': 'USD'}
    m = re.search(r'\$([\d,]+\.?\d*)', body)
    if m:
        r['monto'] = m.group(1).replace(',', '')
    return r

# ── Detección de banco ───────────────────────────────────────────────────────

def detect_and_parse(from_header: str, subject: str, body: str) -> dict:
    f = from_header.lower()
    if 'baccredomatic' in f or 'baccredomatic.sv' in f:
        return parse_bac(body, from_header)
    if 'bancocuscatlan' in f or 'cuscatlan' in f:
        return parse_cuscatlan(body, subject)
    if 'bancoagricola' in f or 'notificacionesbancoagricola' in f:
        return parse_agricola(body, subject)
    if 'payway' in f:
        return parse_payway(body, subject)
    if 'anthropic' in f:
        return parse_anthropic(body)
    if 'netflix' in f:
        return {'banco': 'Netflix', 'tipo': 'suscripcion', 'comercio': 'Netflix',
                'moneda': 'USD', 'revisado': 'false',
                'monto': re.search(r'\$([\d.]+)', body).group(1)
                if re.search(r'\$([\d.]+)', body) else ''}
    return parse_generic(body, from_header)

# ── Extracción de cuerpo y adjuntos ─────────────────────────────────────────

def get_body_and_attachments(payload: dict) -> tuple[str, list]:
    """Retorna (texto_plano, [(filename, attachment_id, mime_type)])."""
    body_text = ''
    attachments = []

    def walk(part):
        nonlocal body_text
        mime = part.get('mimeType', '')
        if mime == 'text/plain':
            data = part.get('body', {}).get('data', '')
            if data:
                body_text += base64.urlsafe_b64decode(data + '==').decode('utf-8', errors='ignore')
        elif mime == 'application/pdf':
            att_id = part.get('body', {}).get('attachmentId', '')
            fname = part.get('filename', 'attachment.pdf')
            if att_id:
                attachments.append((fname, att_id, mime))
        for sub in part.get('parts', []):
            walk(sub)

    walk(payload)
    return body_text, attachments

def download_pdf(service, message_id: str, att_id: str, fname: str, pdf_dir: str) -> str:
    """Descarga PDF y retorna la ruta local."""
    os.makedirs(pdf_dir, exist_ok=True)
    safe_name = re.sub(r'[^\w\-_\.]', '_', fname)
    path = os.path.join(pdf_dir, f"{message_id[:8]}_{safe_name}")
    if os.path.exists(path):
        return path
    att = api_call_with_retry(
        service.users().messages().attachments().get(
            userId='me', messageId=message_id, id=att_id
        ).execute
    )
    data = base64.urlsafe_b64decode(att['data'] + '==')
    with open(path, 'wb') as f:
        f.write(data)
    logger.info(f"  PDF guardado: {path}")
    return path

def extract_pdf_transactions(pdf_path: str, banco: str) -> list[dict]:
    """Extrae transacciones de un PDF de estado de cuenta."""
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber no instalado — omitiendo extracción PDF")
        return []

    records = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = '\n'.join(page.extract_text() or '' for page in pdf.pages)

        logger.info(f"  PDF texto ({len(full_text)} chars): {full_text[:200]!r}")

        if 'BAC' in banco or 'bac' in pdf_path.lower():
            records = _parse_bac_pdf(full_text, pdf_path)
        elif 'Agrícola' in banco or 'agricola' in pdf_path.lower():
            records = _parse_agricola_pdf(full_text, pdf_path)
        elif 'Cuscatlán' in banco or 'cuscatlan' in pdf_path.lower():
            records = _parse_cuscatlan_pdf(full_text, pdf_path)

    except Exception as e:
        logger.error(f"  Error leyendo PDF {pdf_path}: {e}")
    return records

def _parse_bac_pdf(text: str, pdf_path: str) -> list[dict]:
    """Estado de cuenta BAC Credomatic — filas: fecha descripcion monto."""
    records = []
    # Patrón típico BAC: "DD/MM/AAAA  DESCRIPCION   MONTO"
    pattern = re.compile(
        r'(\d{2}/\d{2}/\d{4})\s+(.+?)\s+([\d,]+\.\d{2})\s*(CR)?',
        re.MULTILINE
    )
    for m in pattern.finditer(text):
        try:
            fecha = datetime.strptime(m.group(1), '%d/%m/%Y').date().isoformat()
        except ValueError:
            fecha = m.group(1)
        monto = m.group(2).replace(',', '')
        tipo = 'credito' if m.group(4) else 'debito'
        records.append({
            'fecha_iso': fecha, 'banco': 'BAC Credomatic',
            'tipo': tipo, 'comercio': m.group(2).strip(),
            'monto': m.group(3).replace(',', ''),
            'moneda': 'USD', 'fuente': 'pdf', 'pdf_path': pdf_path,
            'revisado': 'false',
        })
    return records

def _parse_agricola_pdf(text: str, pdf_path: str) -> list[dict]:
    """Estado de cuenta Banco Agrícola."""
    records = []
    # Patrón: "DD/MM/AAAA  DESCRIPCION  MONTO"
    pattern = re.compile(
        r'(\d{2}/\d{2}/\d{4})\s+(.+?)\s+([\d,]+\.\d{2})',
        re.MULTILINE
    )
    for m in pattern.finditer(text):
        try:
            fecha = datetime.strptime(m.group(1), '%d/%m/%Y').date().isoformat()
        except ValueError:
            fecha = m.group(1)
        records.append({
            'fecha_iso': fecha, 'banco': 'Banco Agrícola',
            'tipo': 'debito', 'comercio': m.group(2).strip(),
            'monto': m.group(3).replace(',', ''),
            'moneda': 'USD', 'fuente': 'pdf', 'pdf_path': pdf_path,
            'revisado': 'false',
        })
    return records

def _parse_cuscatlan_pdf(text: str, pdf_path: str) -> list[dict]:
    """Estado de cuenta Banco Cuscatlán."""
    records = []
    pattern = re.compile(
        r'(\d{2}/\d{2}/\d{4})\s+(.+?)\s+([\d,]+\.\d{2})',
        re.MULTILINE
    )
    for m in pattern.finditer(text):
        try:
            fecha = datetime.strptime(m.group(1), '%d/%m/%Y').date().isoformat()
        except ValueError:
            fecha = m.group(1)
        records.append({
            'fecha_iso': fecha, 'banco': 'Banco Cuscatlán',
            'tipo': 'debito', 'comercio': m.group(2).strip(),
            'monto': m.group(3).replace(',', ''),
            'moneda': 'USD', 'fuente': 'pdf', 'pdf_path': pdf_path,
            'revisado': 'false',
        })
    return records

# ── ID único para deduplicación ──────────────────────────────────────────────

def load_existing_ids(csv_path: str) -> set:
    if not os.path.exists(csv_path):
        return set()
    with open(csv_path, 'r', encoding='utf-8') as f:
        return {row.get('message_id', '') for row in csv.DictReader(f)}

def write_records(csv_path: str, records: list):
    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
    with open(csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction='ignore')
        if not file_exists:
            writer.writeheader()
        writer.writerows(records)

# ── Main ─────────────────────────────────────────────────────────────────────

def extract_financial_data():
    logger.info("=== Extracción financiera iniciada ===")
    start = datetime.now()
    settings = load_settings()
    csv_path = settings['paths']['financial_csv']
    pdf_dir = os.path.join(os.path.dirname(csv_path), 'pdfs')
    page_size = settings['gmail']['page_size']

    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    try:
        service = get_service()
        existing_ids = load_existing_ids(csv_path)
        new_records = []
        seen_ids = set()

        # Consultar cada etiqueta por separado (labelIds es AND, necesitamos OR)
        for label_id in FINANCIAL_LABEL_IDS:
            page_token = None
            while True:
                kwargs = dict(userId='me', labelIds=[label_id], maxResults=page_size)
                if page_token:
                    kwargs['pageToken'] = page_token

                result = api_call_with_retry(
                    service.users().messages().list(**kwargs).execute
                )
                messages = result.get('messages', [])
                if not messages:
                    break

                for msg in messages:
                    if msg['id'] in existing_ids or msg['id'] in seen_ids:
                        continue
                    seen_ids.add(msg['id'])

                    m = api_call_with_retry(
                        service.users().messages().get(
                            userId='me', id=msg['id'], format='full'
                        ).execute
                    )

                    headers = {h['name']: h['value'] for h in m['payload']['headers']}
                    from_header = headers.get('From', '')
                    subject = headers.get('Subject', '')
                    date_header = headers.get('Date', '')

                    body, attachments = get_body_and_attachments(m['payload'])
                    if not body:
                        body = m.get('snippet', '')

                    parsed = detect_and_parse(from_header, subject, body)
                    parsed['message_id'] = msg['id']
                    parsed['fuente'] = 'email'
                    parsed['pdf_path'] = ''
                    parsed['descripcion'] = m.get('snippet', '')[:150]

                    # Fecha fallback desde cabecera del email
                    if not parsed.get('fecha_iso'):
                        try:
                            # "Tue, 16 Jun 2026 19:09:36 +0000" → parse
                            from email.utils import parsedate_to_datetime
                            dt = parsedate_to_datetime(date_header)
                            parsed['fecha_iso'] = dt.date().isoformat()
                        except Exception:
                            parsed['fecha_iso'] = date.today().isoformat()

                    # Omitir logins (sin monto)
                    if parsed.get('tipo') == 'login':
                        continue

                    new_records.append(parsed)

                    if parsed.get('tipo', '').startswith('estado_cuenta') and parsed.get('saldo'):
                        save_balance(settings, parsed)

                    # Descargar y parsear PDFs adjuntos
                    for fname, att_id, mime in attachments:
                        try:
                            pdf_path = download_pdf(service, msg['id'], att_id, fname, pdf_dir)
                            pdf_records = extract_pdf_transactions(pdf_path, parsed['banco'])
                            for pr in pdf_records:
                                pr['message_id'] = msg['id'] + '_pdf_' + fname[:8]
                                if pr['message_id'] not in existing_ids:
                                    new_records.append(pr)
                        except Exception as e:
                            logger.error(f"  Error procesando PDF {fname}: {e}")

                page_token = result.get('nextPageToken')
                if not page_token:
                    break

        write_records(csv_path, new_records)
        duration = (datetime.now() - start).total_seconds()
        logger.info(
            f"=== Extracción finalizada: {len(new_records)} registros nuevos "
            f"en {csv_path} ({duration:.1f}s) ==="
        )
        return len(new_records)

    except Exception as e:
        logger.error(f"Error en financial_extractor: {e}", exc_info=True)
        return 0


if __name__ == '__main__':
    extract_financial_data()
