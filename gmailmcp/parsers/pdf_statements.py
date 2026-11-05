"""Parsers de texto de PDFs de estado de cuenta, uno por banco."""
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime

_ROW = re.compile(r'(\d{2}/\d{2}/\d{4})\s+(.+?)\s+([\d,]+\.\d{2})', re.MULTILINE)
_ROW_WITH_CREDIT = re.compile(r'(\d{2}/\d{2}/\d{4})\s+(.+?)\s+([\d,]+\.\d{2})\s*(CR)?', re.MULTILINE)


def _iso(raw: str) -> str:
    try:
        return datetime.strptime(raw, '%d/%m/%Y').date().isoformat()
    except ValueError:
        return raw


class PdfStatementParser(ABC):
    banco: str = ""
    banco_key: str = ""        # fragmento que identifica al banco en el registro parseado
    path_fragment: str = ""    # o en el nombre del archivo PDF

    def matches(self, banco: str, pdf_path: str) -> bool:
        return self.banco_key in banco or self.path_fragment in pdf_path.lower()

    @abstractmethod
    def parse(self, text: str, pdf_path: str) -> list[dict]: ...

    def _record(self, fecha, tipo, comercio, monto, pdf_path) -> dict:
        return {'fecha_iso': fecha, 'banco': self.banco, 'tipo': tipo, 'comercio': comercio,
                'monto': monto, 'moneda': 'USD', 'fuente': 'pdf', 'pdf_path': pdf_path,
                'revisado': 'false'}


class BacPdfParser(PdfStatementParser):
    """Filas "DD/MM/AAAA DESCRIPCION MONTO [CR]"; CR marca un crédito."""
    banco = 'BAC Credomatic'
    path_fragment = 'bac'
    banco_key = 'BAC'

    def parse(self, text, pdf_path):
        return [self._record(_iso(m.group(1)), 'credito' if m.group(4) else 'debito',
                             m.group(2).strip(), m.group(3).replace(',', ''), pdf_path)
                for m in _ROW_WITH_CREDIT.finditer(text)]


class _DebitRowsPdfParser(PdfStatementParser):
    """Filas "DD/MM/AAAA DESCRIPCION MONTO", todas tratadas como débito."""

    def parse(self, text, pdf_path):
        return [self._record(_iso(m.group(1)), 'debito', m.group(2).strip(),
                             m.group(3).replace(',', ''), pdf_path) for m in _ROW.finditer(text)]


class AgricolaPdfParser(_DebitRowsPdfParser):
    banco = 'Banco Agrícola'
    path_fragment = 'agricola'
    banco_key = 'Agrícola'


class CuscatlanPdfParser(_DebitRowsPdfParser):
    banco = 'Banco Cuscatlán'
    path_fragment = 'cuscatlan'
    banco_key = 'Cuscatlán'


class PdfParserRegistry:
    def __init__(self, parsers: list[PdfStatementParser], logger: logging.Logger):
        self._parsers = parsers
        self._logger = logger

    def extract(self, pdf_path: str, banco: str) -> list[dict]:
        """Extrae transacciones del PDF; un PDF ilegible devuelve [] y se registra."""
        try:
            import pdfplumber
        except ImportError:
            self._logger.warning("pdfplumber no instalado — omitiendo extracción PDF")
            return []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                full_text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
            self._logger.info(f"  PDF texto ({len(full_text)} chars): {full_text[:200]!r}")
            parser = next((p for p in self._parsers if p.matches(banco, pdf_path)), None)
            return parser.parse(full_text, pdf_path) if parser else []
        except Exception as e:
            self._logger.error(f"  Error leyendo PDF {pdf_path}: {e}")
            return []


def build_default_pdf_registry(logger: logging.Logger) -> PdfParserRegistry:
    return PdfParserRegistry([BacPdfParser(), AgricolaPdfParser(), CuscatlanPdfParser()], logger)
