"""Maps parsed email records to known accounts defined in settings.json."""

_DEST_PATTERNS = [
    ('BAC',        ['bac credomatic', 'banco de america central', 'baccredomatic', ' bac ']),
    ('Cuscatlán',  ['cuscatlan', 'cuscatlán', 'banco cuscatlan', 'banco cuscatlán']),
    ('Agrícola',   ['banco agricola', 'banco agrícola', 'bancoagricola']),
    ('Davivienda', ['davivienda']),
]


def _dest_bank(text: str) -> str | None:
    t = ' ' + text.lower() + ' '
    for name, pats in _DEST_PATTERNS:
        if any(p in t for p in pats):
            return name
    return None


def classify(record: dict, settings: dict) -> dict:
    """Return classification: cuenta_destino, last4_destino, tipo_clasificado, confianza."""
    banco = record.get('banco', '') or ''
    tipo  = record.get('tipo', '') or ''
    desc  = (record.get('descripcion', '') or '').lower()
    last4 = record.get('tarjeta_ultimos4', '') or ''

    cards     = settings.get('planner', {}).get('cards', [])
    prestamos = settings.get('prestamos', [])

    # ── BAC Credomatic ────────────────────────────────────────────────
    if 'BAC' in banco:
        card = next((c for c in cards
                     if c.get('last4') == last4 and 'BAC' in c.get('name', '')), None)
        if card:
            return {'cuenta_destino': card['name'], 'last4_destino': last4,
                    'tipo_clasificado': tipo or 'compra', 'confianza': 'alta'}
        return {'cuenta_destino': None, 'last4_destino': last4 or None,
                'tipo_clasificado': tipo, 'confianza': 'baja'}

    # ── Banco Agrícola ────────────────────────────────────────────────
    if 'grícola' in banco or 'gricola' in banco:

        # Estado de cuenta → match by last4
        if tipo.startswith('estado_cuenta'):
            card = next((c for c in cards if c.get('last4') == last4), None)
            if card:
                return {'cuenta_destino': card['name'], 'last4_destino': last4,
                        'tipo_clasificado': 'estado_cuenta', 'confianza': 'alta'}

        # Pago de tarjeta de crédito propia → VISA Agrícola ****6114
        if 'pago de tarjeta de cr' in desc or ('tarjeta de cr' in desc and 'propia' in desc):
            agri = next((c for c in cards if c.get('last4') == '6114'), None)
            name = agri['name'] if agri else 'VISA Agrícola ****6114'
            return {'cuenta_destino': name, 'last4_destino': '6114',
                    'tipo_clasificado': 'pago_tarjeta', 'confianza': 'alta'}

        # Pago de préstamo propio
        if ('prestamo propio' in desc or 'préstamo propio' in desc
                or ('prestamo' in desc and 'propio' in desc)):
            name = prestamos[0]['nombre'] if prestamos else 'Préstamo Agrícola'
            return {'cuenta_destino': name, 'last4_destino': None,
                    'tipo_clasificado': 'pago_prestamo', 'confianza': 'alta'}

        # Transfer365 salida → detectar banco destino
        if tipo == 'transfer365':
            dest = _dest_bank(desc)
            if dest == 'BAC':
                return {'cuenta_destino': 'BAC (AMEX/VISA)', 'last4_destino': None,
                        'tipo_clasificado': 'pago_transfer365', 'confianza': 'media'}
            if dest == 'Cuscatlán':
                card = next((c for c in cards if c.get('last4') == '2789'), None)
                name = card['name'] if card else 'VISA Cuscatlán ****2789'
                return {'cuenta_destino': name, 'last4_destino': '2789',
                        'tipo_clasificado': 'pago_transfer365', 'confianza': 'alta'}
            if dest:
                return {'cuenta_destino': f'Transfer365 → {dest}', 'last4_destino': None,
                        'tipo_clasificado': 'pago_transfer365', 'confianza': 'media'}
            return {'cuenta_destino': 'Transfer365 (destino desconocido)', 'last4_destino': None,
                    'tipo_clasificado': 'pago_transfer365', 'confianza': 'baja'}

        # Abono recibido (lado receptor de Transfer365)
        if 'has recibido' in desc or 'recibido un abono' in desc:
            return {'cuenta_destino': 'Cuenta Agrícola (ingreso)', 'last4_destino': None,
                    'tipo_clasificado': 'abono_recibido', 'confianza': 'alta'}

        # Transferencia a terceros
        if tipo == 'transferencia' or 'terceros' in desc:
            dest = _dest_bank(desc)
            return {'cuenta_destino': f'Transferencia → {dest or "Tercero"}',
                    'last4_destino': None, 'tipo_clasificado': 'transferencia',
                    'confianza': 'media' if dest else 'baja'}

    # ── Banco Cuscatlán ───────────────────────────────────────────────
    if 'uscatlán' in banco or 'uscatlan' in banco:
        if tipo == 'debito':
            return {'cuenta_destino': 'Cuenta Cuscatlán', 'last4_destino': '5261',
                    'tipo_clasificado': 'debito', 'confianza': 'alta'}
        if tipo == 'credito':
            return {'cuenta_destino': 'Cuenta Cuscatlán', 'last4_destino': '5261',
                    'tipo_clasificado': 'credito', 'confianza': 'alta'}
        if tipo == 'pago_tarjeta':
            card = next((c for c in cards if c.get('last4') == '2789'), None)
            name = card['name'] if card else 'VISA Cuscatlán ****2789'
            return {'cuenta_destino': name, 'last4_destino': '2789',
                    'tipo_clasificado': 'pago_tarjeta', 'confianza': 'alta'}
        if tipo == 'transfer365':
            return {'cuenta_destino': 'Cuenta Cuscatlán', 'last4_destino': '5261',
                    'tipo_clasificado': 'transfer365', 'confianza': 'media'}

    # ── Payway ────────────────────────────────────────────────────────
    if 'Payway' in banco or 'ayway' in banco:
        comercio = record.get('comercio', '') or ''
        return {'cuenta_destino': f'Servicio: {comercio or "Payway"}', 'last4_destino': None,
                'tipo_clasificado': 'pago_servicio', 'confianza': 'alta'}

    return {'cuenta_destino': None, 'last4_destino': None,
            'tipo_clasificado': tipo, 'confianza': 'sin_clasificar'}
