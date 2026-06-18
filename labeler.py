import json
from datetime import datetime
from gmail_auth import get_service, api_call_with_retry, load_settings
from gmail_logger import setup_logger

logger = setup_logger('labeler')

LOOKBACK_DAYS = 7
TOTAL_SECONDS = 300   # 5 minutos totales
PHASE1_SECONDS = 270  # primero: últimos 7 días

SKIP_IF_HAS = {
    'Label_2', 'Label_3', 'Label_4', 'Label_6',
    'Label_13', 'Label_15', 'Label_17',
    'Label_1834638960901538876',
    'Label_8650347335116413717', 'Label_11',
    'Label_8229819340533470960', 'Label_1938252154982079077',
    'Label_1714922903715444819',
}

CORRECTIONS = {
    'Label_1834638960901538876': ['iseade.edu.sv', 'utec.edu.sv'],
    'Label_13': ['datacamp', 'notify.thinkific', 'kaggle', 'platzi', 'netec', 'coursera'],
}

OUR_LABELS = set(SKIP_IF_HAS)

LABEL_PRIORITY = {
    'Label_1834638960901538876': 1,  # Banco Cuscatlán (most specific)
    'Label_17': 2,    # Fun Capital/Conciertos
    'Label_3': 3,     # Recibos
    'Label_4': 4,     # Trabajo
    'Label_2': 5,     # Cursos
    'Label_6': 6,     # Archivo
    'Label_15': 7,    # Newsletters
    'Label_13': 8,    # Promociones
}

def load_rules():
    settings = load_settings()
    with open(settings['paths']['label_rules_file'], 'r', encoding='utf-8') as f:
        raw = json.load(f)
    rules = []
    for category, data in raw.items():
        if category.startswith('_'):
            continue
        label_id = data['_label_id']
        for sender in data['senders']:
            rules.append((sender.lower(), label_id))
    return rules

def match_label(from_header: str, rules: list):
    from_lower = from_header.lower()
    for fragment, label_id in rules:
        if fragment in from_lower:
            return label_id
    return None

def needs_correction(from_header: str, existing_labels: list):
    from_lower = from_header.lower()
    for wrong_label, fragments in CORRECTIONS.items():
        if wrong_label in existing_labels:
            if any(f in from_lower for f in fragments):
                return True, wrong_label
    return False, None

def _process_messages(service, query, rules, start, deadline, labeled, corrected, skipped, label_counts, cleaned=0):
    page_token = None
    settings = load_settings()
    page_size = settings['gmail']['page_size']

    while True:
        if (datetime.now() - start).total_seconds() >= deadline:
            break

        kwargs = dict(userId='me', q=query, maxResults=page_size)
        if page_token:
            kwargs['pageToken'] = page_token

        result = api_call_with_retry(service.users().messages().list(**kwargs).execute)
        messages = result.get('messages', [])
        if not messages:
            break

        for msg in messages:
            if (datetime.now() - start).total_seconds() >= deadline:
                return labeled, corrected, skipped, label_counts, cleaned, False  # deadline hit

            m = api_call_with_retry(
                service.users().messages().get(
                    userId='me', id=msg['id'], format='metadata',
                    metadataHeaders=['From']
                ).execute
            )
            existing_labels = m.get('labelIds', [])
            from_header = next(
                (h['value'] for h in m['payload']['headers'] if h['name'] == 'From'), ''
            )

            # Enforce single label: if >1 of our labels, remove lower-priority ones
            our_labels_present = [lbl for lbl in existing_labels if lbl in OUR_LABELS]
            if len(our_labels_present) > 1:
                to_keep = min(our_labels_present, key=lambda l: LABEL_PRIORITY.get(l, 99))
                to_remove = [l for l in our_labels_present if l != to_keep]
                api_call_with_retry(
                    service.users().messages().modify(
                        userId='me', id=msg['id'],
                        body={'removeLabelIds': to_remove}
                    ).execute
                )
                cleaned += 1
                logger.info(f"  Dedup: {from_header[:40]} | kept={to_keep}, removed={to_remove}")
                skipped += 1
                continue

            wrong, wrong_label_id = needs_correction(from_header, existing_labels)
            if wrong:
                correct_label = match_label(from_header, rules)
                if correct_label and correct_label != wrong_label_id:
                    api_call_with_retry(
                        service.users().messages().modify(
                            userId='me', id=msg['id'],
                            body={'addLabelIds': [correct_label],
                                  'removeLabelIds': [wrong_label_id]}
                        ).execute
                    )
                    corrected += 1
                    logger.info(f"  Corregido: {from_header[:50]} | {wrong_label_id}→{correct_label}")
                continue

            if any(lbl in SKIP_IF_HAS for lbl in existing_labels):
                skipped += 1
                continue

            label_id = match_label(from_header, rules)
            if label_id:
                api_call_with_retry(
                    service.users().messages().modify(
                        userId='me', id=msg['id'],
                        body={'addLabelIds': [label_id]}
                    ).execute
                )
                labeled += 1
                label_counts[label_id] = label_counts.get(label_id, 0) + 1

        page_token = result.get('nextPageToken')
        if not page_token:
            break

    return labeled, corrected, skipped, label_counts, cleaned, True  # finished normally

def label_messages():
    logger.info("=== Etiquetado iniciado (ventana 5 min) ===")
    start = datetime.now()

    try:
        service = get_service()
        rules = load_rules()
        if not rules:
            logger.warning("Sin reglas.")
            return 0

        labeled, corrected, skipped, cleaned = 0, 0, 0, 0
        label_counts = {}

        # FASE 1 — últimos 7 días (hasta 4m30s)
        logger.info(f"  Fase 1: últimos {LOOKBACK_DAYS} días")
        labeled, corrected, skipped, label_counts, cleaned, done = _process_messages(
            service, f'in:inbox newer_than:{LOOKBACK_DAYS}d',
            rules, start, PHASE1_SECONDS,
            labeled, corrected, skipped, label_counts, cleaned
        )

        # FASE 2 — correos más antiguos sin etiquetar (tiempo restante)
        elapsed = (datetime.now() - start).total_seconds()
        remaining = TOTAL_SECONDS - elapsed
        if remaining > 10:
            logger.info(f"  Fase 2: correos sin etiqueta ({remaining:.0f}s disponibles)")
            labeled, corrected, skipped, label_counts, cleaned, _ = _process_messages(
                service, 'in:inbox has:nouserlabels',
                rules, start, TOTAL_SECONDS,
                labeled, corrected, skipped, label_counts, cleaned
            )
        else:
            logger.info("  Fase 2 omitida: sin tiempo disponible")

        duration = (datetime.now() - start).total_seconds()
        logger.info(
            f"=== Etiquetado finalizado: {labeled} nuevos, {corrected} corregidos, "
            f"{cleaned} dedup, {skipped} ya etiquetados — {duration:.1f}s ==="
        )
        if label_counts:
            for lid, count in sorted(label_counts.items(), key=lambda x: x[1], reverse=True):
                logger.info(f"  {count:3d}x  {lid}")
        return labeled + corrected

    except Exception as e:
        logger.error(f"Error en labeler: {e}", exc_info=True)
        return 0


if __name__ == '__main__':
    label_messages()
