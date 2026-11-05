"""Parsers de los correos de cada emisor (BAC, Cuscatlán, Agrícola, Payway, Anthropic, Netflix)."""
import re
from datetime import datetime

from gmailmcp.parsers.base import BankParser, EmailContent, ParserRegistry


def _base(banco: str, **extra) -> dict:
    return {'banco': banco, 'moneda': 'USD', 'revisado': 'false', **extra}


class BacParser(BankParser):
    """BAC Credomatic — alertas de compra y transferencias."""
    name = "BAC Credomatic"
    sender_fragments = ("baccredomatic",)

    def parse(self, email: EmailContent) -> dict:
        body = email.body
        r = _base(self.name)

        m = re.search(r'tarjeta (MASTERCARD|AMEX|VISA)\s+terminada en (\d{4})', body, re.IGNORECASE)
        if m:
            r['tarjeta_tipo'] = m.group(1)
            r['tarjeta_ultimos4'] = m.group(2)

        # Comercio y monto aparecen en líneas separadas después de "Monto"
        m = re.search(r'Comercio\s+Monto\s+([\w*\s\-\.]+?)\s+([\d]+\.[\d]{2})\s', body, re.DOTALL)
        if m:
            r['comercio'] = m.group(1).strip()
            r['monto'] = m.group(2)
        else:
            m2 = re.search(r'(\d+\.\d{2})', body)
            if m2:
                r['monto'] = m2.group(1)

        m = re.search(r'(\d{4}/\d{2}/\d{2})-(\d{2}:\d{2}:\d{2})', body)
        if m:
            try:
                r['fecha_iso'] = datetime.strptime(m.group(1), '%Y/%m/%d').date().isoformat()
            except ValueError:
                pass

        if re.search(r'compra', body, re.IGNORECASE):
            r['tipo'] = 'compra'
        elif re.search(r'transferencia', body, re.IGNORECASE):
            r['tipo'] = 'transferencia'
            m2 = re.search(r'por USD\s*([\d.]+)', body, re.IGNORECASE)
            if m2:
                r['monto'] = m2.group(1)
        elif re.search(r'pago.*servicio', body, re.IGNORECASE):
            r['tipo'] = 'pago_servicio'
        return r


class CuscatlanParser(BankParser):
    """Banco Cuscatlán — débitos, abonos, Transfer365, pagos de tarjeta."""
    name = "Banco Cuscatlán"
    sender_fragments = ("bancocuscatlan", "cuscatlan")

    def parse(self, email: EmailContent) -> dict:
        body, subject = email.body, email.subject
        r = _base(self.name)

        m = re.search(r'cuenta [X]+(\d{4})', body, re.IGNORECASE)
        if m:
            r['tarjeta_ultimos4'] = m.group(1)

        m = re.search(r'USD\s*([\d,]+\.?\d*)', body, re.IGNORECASE)
        if m:
            r['monto'] = m.group(1).replace(',', '')

        m = re.search(r'el día (\d{4}-\d{2}-\d{2})', body) or re.search(r'(\d{4}-\d{2}-\d{2})', body)
        if m:
            r['fecha_iso'] = m.group(1)

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
            r['monto'] = ''
        return r


class AgricolaParser(BankParser):
    """Banco Agrícola — transferencias, inicio de sesión, estado de cuenta."""
    name = "Banco Agrícola"
    sender_fragments = ("bancoagricola", "notificacionesbancoagricola")

    # Separador ":", "$" o ": $" entre la etiqueta y el número
    _BALANCE_PATTERNS = (
        r'[Ss]aldo\s+(?:[Aa]ctual|[Tt]otal|[Aa]l\s+[Cc]orte)\s*:?\s*\$?\s*([\d,]+\.?\d*)',
        r'[Tt]otal\s+a\s+[Pp]agar\s*:?\s*\$?\s*([\d,]+\.?\d*)',
        r'[Ss]aldo\s+[Cc]ontado\s*:?\s*\$?\s*([\d,]+\.?\d*)',
    )

    def parse(self, email: EmailContent) -> dict:
        if 'estado de cuenta' in email.subject.lower():
            return self._parse_statement(email.body)
        return self._parse_movement(email.body, email.subject)

    def _parse_statement(self, body: str) -> dict:
        """Aviso de estado de cuenta; el detalle completo viene en el PDF adjunto."""
        r = _base(self.name, tipo='estado_cuenta')
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
        for pat in self._BALANCE_PATTERNS:
            m_saldo = re.search(pat, body, re.IGNORECASE | re.DOTALL)
            if m_saldo:
                r['saldo'] = m_saldo.group(1).replace(',', '')
                break
        return r

    def _parse_movement(self, body: str, subject: str) -> dict:
        r = _base(self.name)
        if 'transfer365' in subject.lower() or 'transfer365' in body.lower():
            r['tipo'] = 'transfer365'
            m = re.search(r'([\d,]+\.?\d*)\s*USD', body) or re.search(r'\$([\d,]+\.?\d*)', body)
            if m:
                r['monto'] = m.group(1).replace(',', '')
        elif 'transferencia' in body.lower():
            r['tipo'] = 'transferencia'
        elif 'inicio de sesión' in subject.lower():
            r['tipo'] = 'login'
            r['monto'] = ''

        m = re.search(r'(\d{2}-\d{2}-\d{4})', body)
        if m:
            try:
                r['fecha_iso'] = datetime.strptime(m.group(1), '%d-%m-%Y').date().isoformat()
            except ValueError:
                pass
        return r


class PaywayParser(BankParser):
    """Payway — notificaciones de pago de servicios (DELSUR, ANDA...)."""
    name = "Payway"
    sender_fragments = ("payway",)

    def parse(self, email: EmailContent) -> dict:
        r = _base(self.name, tipo='pago_servicio')
        m = re.search(r'notificaci[oó]n de pago\s*[-–]\s*(.+)', email.subject, re.IGNORECASE)
        if m:
            r['comercio'] = m.group(1).strip()
        m2 = re.search(r'\$([\d,]+\.?\d*)', email.body)
        if m2:
            r['monto'] = m2.group(1).replace(',', '')
        m3 = re.search(r'(\d{4}-\d{2}-\d{2})', email.body)
        if m3:
            r['fecha_iso'] = m3.group(1)
        return r


class AnthropicParser(BankParser):
    name = "Anthropic"
    sender_fragments = ("anthropic",)

    def parse(self, email: EmailContent) -> dict:
        r = _base(self.name, tipo='suscripcion', comercio='Anthropic')
        m = re.search(r'\$([\d.]+)', email.body)
        if m:
            r['monto'] = m.group(1)
        m2 = re.search(r'\*+(\d{4})', email.body)
        if m2:
            r['tarjeta_ultimos4'] = m2.group(1)
        return r


class NetflixParser(BankParser):
    name = "Netflix"
    sender_fragments = ("netflix",)

    def parse(self, email: EmailContent) -> dict:
        m = re.search(r'\$([\d.]+)', email.body)
        return _base(self.name, tipo='suscripcion', comercio='Netflix', monto=m.group(1) if m else '')


class GenericParser(BankParser):
    """Respaldo cuando ningún emisor coincide: solo intenta sacar un monto."""
    name = "Desconocido"

    def parse(self, email: EmailContent) -> dict:
        r = _base(self.name)
        m = re.search(r'\$([\d,]+\.?\d*)', email.body)
        if m:
            r['monto'] = m.group(1).replace(',', '')
        return r


def build_default_registry() -> ParserRegistry:
    """El orden importa: gana el primer parser cuyo remitente coincide."""
    registry = ParserRegistry(fallback=GenericParser())
    for parser in (BacParser(), CuscatlanParser(), AgricolaParser(), PaywayParser(),
                   AnthropicParser(), NetflixParser()):
        registry.register(parser)
    return registry
