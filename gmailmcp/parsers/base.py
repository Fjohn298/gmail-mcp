"""Contrato común de los parsers de banco (Strategy) y su registro (Registry)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class EmailContent:
    from_header: str
    subject: str
    body: str


class BankParser(ABC):
    """Una estrategia por emisor. Todas reciben lo mismo y devuelven un dict de transacción."""

    name: str = ""
    sender_fragments: tuple[str, ...] = ()

    def matches(self, from_header: str) -> bool:
        f = from_header.lower()
        return any(fragment in f for fragment in self.sender_fragments)

    @abstractmethod
    def parse(self, email: EmailContent) -> dict: ...


class ParserRegistry:
    """Elige el primer parser cuyo remitente coincide; si ninguno, usa el de respaldo.

    Añadir un banco = crear su clase y registrarla; este código no se toca (Open/Closed).
    """

    def __init__(self, fallback: BankParser):
        self._parsers: list[BankParser] = []
        self._fallback = fallback

    def register(self, parser: BankParser) -> "ParserRegistry":
        self._parsers.append(parser)
        return self

    @property
    def parsers(self) -> tuple[BankParser, ...]:
        return tuple(self._parsers)

    def parser_for(self, from_header: str) -> BankParser:
        return next((p for p in self._parsers if p.matches(from_header)), self._fallback)

    def parse(self, from_header: str, subject: str, body: str) -> dict:
        return self.parser_for(from_header).parse(EmailContent(from_header, subject, body))
