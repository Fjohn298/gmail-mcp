"""Asigna cada registro parseado a una cuenta conocida de settings.json.

Una regla por banco (Strategy). Cada regla devuelve una clasificación o None si no
sabe resolver el caso; el clasificador prueba en orden y usa un resultado por defecto.
"""
from abc import ABC, abstractmethod

_DEST_PATTERNS = [
    ('BAC',        ['bac credomatic', 'banco de america central', 'baccredomatic', ' bac ']),
    ('Cuscatlán',  ['cuscatlan', 'cuscatlán', 'banco cuscatlan', 'banco cuscatlán']),
    ('Agrícola',   ['banco agricola', 'banco agrícola', 'bancoagricola']),
    ('Davivienda', ['davivienda']),
]


def _dest_bank(text: str) -> str | None:
    t = ' ' + text.lower() + ' '
    return next((name for name, pats in _DEST_PATTERNS if any(p in t for p in pats)), None)


def _result(cuenta, last4, tipo, confianza) -> dict:
    return {'cuenta_destino': cuenta, 'last4_destino': last4,
            'tipo_clasificado': tipo, 'confianza': confianza}


def _card(cards: list[dict], last4: str) -> dict | None:
    return next((c for c in cards if c.get('last4') == last4), None)


class ClassificationRule(ABC):
    @abstractmethod
    def applies_to(self, banco: str) -> bool: ...

    @abstractmethod
    def classify(self, record: dict, settings: dict) -> dict | None: ...


class BacRule(ClassificationRule):
    def applies_to(self, banco):
        return 'BAC' in banco

    def classify(self, record, settings):
        last4 = record.get('tarjeta_ultimos4', '') or ''
        tipo = record.get('tipo', '') or ''
        cards = settings.get('planner', {}).get('cards', [])
        card = next((c for c in cards if c.get('last4') == last4 and 'BAC' in c.get('name', '')), None)
        if card:
            return _result(card['name'], last4, tipo or 'compra', 'alta')
        return _result(None, last4 or None, tipo, 'baja')


class AgricolaRule(ClassificationRule):
    def applies_to(self, banco):
        return 'grícola' in banco or 'gricola' in banco

    def classify(self, record, settings):
        tipo = record.get('tipo', '') or ''
        desc = (record.get('descripcion', '') or '').lower()
        last4 = record.get('tarjeta_ultimos4', '') or ''
        cards = settings.get('planner', {}).get('cards', [])
        prestamos = settings.get('prestamos', [])

        if tipo.startswith('estado_cuenta'):
            card = _card(cards, last4)
            if card:
                return _result(card['name'], last4, 'estado_cuenta', 'alta')

        if 'pago de tarjeta de cr' in desc or ('tarjeta de cr' in desc and 'propia' in desc):
            agri = _card(cards, '6114')
            return _result(agri['name'] if agri else 'VISA Agrícola ****6114', '6114', 'pago_tarjeta', 'alta')

        if 'prestamo propio' in desc or 'préstamo propio' in desc or ('prestamo' in desc and 'propio' in desc):
            name = prestamos[0]['nombre'] if prestamos else 'Préstamo Agrícola'
            return _result(name, None, 'pago_prestamo', 'alta')

        if tipo == 'transfer365':
            dest = _dest_bank(desc)
            if dest == 'BAC':
                return _result('BAC (AMEX/VISA)', None, 'pago_transfer365', 'media')
            if dest == 'Cuscatlán':
                card = _card(cards, '2789')
                return _result(card['name'] if card else 'VISA Cuscatlán ****2789', '2789',
                               'pago_transfer365', 'alta')
            if dest:
                return _result(f'Transfer365 → {dest}', None, 'pago_transfer365', 'media')
            return _result('Transfer365 (destino desconocido)', None, 'pago_transfer365', 'baja')

        if 'has recibido' in desc or 'recibido un abono' in desc:
            return _result('Cuenta Agrícola (ingreso)', None, 'abono_recibido', 'alta')

        if tipo == 'transferencia' or 'terceros' in desc:
            dest = _dest_bank(desc)
            return _result(f'Transferencia → {dest or "Tercero"}', None, 'transferencia',
                           'media' if dest else 'baja')
        return None


class CuscatlanRule(ClassificationRule):
    def applies_to(self, banco):
        return 'uscatlán' in banco or 'uscatlan' in banco

    def classify(self, record, settings):
        tipo = record.get('tipo', '') or ''
        if tipo in ('debito', 'credito'):
            return _result('Cuenta Cuscatlán', '5261', tipo, 'alta')
        if tipo == 'pago_tarjeta':
            card = _card(settings.get('planner', {}).get('cards', []), '2789')
            return _result(card['name'] if card else 'VISA Cuscatlán ****2789', '2789', 'pago_tarjeta', 'alta')
        if tipo == 'transfer365':
            return _result('Cuenta Cuscatlán', '5261', 'transfer365', 'media')
        return None


class PaywayRule(ClassificationRule):
    def applies_to(self, banco):
        return 'Payway' in banco or 'ayway' in banco

    def classify(self, record, settings):
        comercio = record.get('comercio', '') or ''
        return _result(f'Servicio: {comercio or "Payway"}', None, 'pago_servicio', 'alta')


DEFAULT_RULES: tuple[ClassificationRule, ...] = (BacRule(), AgricolaRule(), CuscatlanRule(), PaywayRule())


class TransactionClassifier:
    def __init__(self, rules: tuple[ClassificationRule, ...] = DEFAULT_RULES):
        self._rules = rules

    def classify(self, record: dict, settings: dict) -> dict:
        banco = record.get('banco', '') or ''
        for rule in self._rules:
            if rule.applies_to(banco):
                result = rule.classify(record, settings)
                if result is not None:
                    return result
        return _result(None, None, record.get('tipo', '') or '', 'sin_clasificar')
