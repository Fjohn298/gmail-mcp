import json
from datetime import datetime
from gmail_auth import get_service, api_call_with_retry, load_settings
from gmail_logger import setup_logger

logger = setup_logger('cleanup')

def load_spam_senders():
    settings = load_settings()
    path = settings['paths']['spam_senders_file']
    senders = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                senders.append(line)
    return senders

def build_query(senders):
    froms = ' OR '.join([f'from:{s}' for s in senders])
    return f'({froms}) in:inbox'

def cleanup():
    logger.info("=== Limpieza iniciada ===")
    start = datetime.now()
    settings = load_settings()
    page_size = settings['gmail']['page_size']
    protected = set(settings['gmail']['protected_labels'])

    try:
        service = get_service()
        senders = load_spam_senders()
        if not senders:
            logger.warning("spam_senders.txt vacío, nada que limpiar.")
            return 0

        query = build_query(senders)
        deleted = 0
        sender_counts = {}

        while True:
            result = api_call_with_retry(
                service.users().threads().list(userId='me', q=query, maxResults=page_size).execute
            )
            threads = result.get('threads', [])
            if not threads:
                break

            for t in threads:
                thread_data = api_call_with_retry(
                    service.users().threads().get(
                        userId='me', id=t['id'], format='metadata',
                        metadataHeaders=['From', 'X-Gmail-Labels']
                    ).execute
                )

                # Nunca tocar correos financieros
                label_ids = thread_data.get('messages', [{}])[0].get('labelIds', [])
                if any(lbl in protected for lbl in label_ids):
                    logger.warning(f"Saltando thread {t['id']} — tiene etiqueta protegida")
                    continue

                # Extraer remitente para el log
                headers = thread_data['messages'][0]['payload'].get('headers', [])
                from_header = next((h['value'] for h in headers if h['name'] == 'From'), 'desconocido')

                api_call_with_retry(
                    service.users().threads().trash(userId='me', id=t['id']).execute
                )
                deleted += 1
                sender_counts[from_header] = sender_counts.get(from_header, 0) + 1

            logger.info(f"   {deleted} threads en papelera hasta ahora...")

        duration = (datetime.now() - start).seconds
        logger.info(f"=== Limpieza finalizada: {deleted} eliminados en {duration}s ===")
        if sender_counts:
            top = sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            logger.info("Top remitentes eliminados:")
            for sender, count in top:
                logger.info(f"  {count:3d}x  {sender}")
        return deleted

    except Exception as e:
        logger.error(f"Error en cleanup: {e}", exc_info=True)
        return 0


if __name__ == '__main__':
    cleanup()
