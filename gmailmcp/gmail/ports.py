"""Interfaces pequeñas sobre Gmail (Interface Segregation).

Cada servicio depende solo de las capacidades que usa: el extractor solo lee,
cleanup solo lee hilos y los manda a papelera, los correos de resumen solo envían.
"""
from typing import Protocol


class MessageReader(Protocol):
    def list_messages(self, *, query: str | None = None, label_ids: list[str] | None = None,
                      max_results: int | None = None, page_token: str | None = None) -> dict: ...

    def get_message(self, message_id: str, *, format: str = "full",
                    metadata_headers: list[str] | None = None) -> dict: ...

    def get_attachment(self, message_id: str, attachment_id: str) -> dict: ...


class MessageLabeler(Protocol):
    def modify_message(self, message_id: str, *, add: list[str] | None = None,
                       remove: list[str] | None = None) -> None: ...


class MessageMover(Protocol):
    def trash_message(self, message_id: str) -> None: ...


class ThreadReader(Protocol):
    def list_threads(self, *, query: str, max_results: int | None = None,
                     page_token: str | None = None) -> dict: ...

    def get_thread(self, thread_id: str, *, format: str = "metadata",
                   metadata_headers: list[str] | None = None) -> dict: ...


class ThreadTrasher(Protocol):
    def trash_thread(self, thread_id: str) -> None: ...


class LabelCatalog(Protocol):
    def list_labels(self) -> list[dict]: ...


class MailSender(Protocol):
    def send_raw(self, raw: str) -> None: ...
