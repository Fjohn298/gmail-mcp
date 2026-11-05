"""Adaptadores concretos de los puertos de Gmail."""
import logging

from gmailmcp.gmail.retry import RetryPolicy, call_with_retry


def _drop_none(**kwargs) -> dict:
    return {k: v for k, v in kwargs.items() if v is not None}


class GmailClient:
    """Implementa todos los puertos de gmailmcp.gmail.ports sobre el servicio de Google."""

    def __init__(self, service, policy: RetryPolicy, logger: logging.Logger):
        self._users = service.users()
        self._policy = policy
        self._logger = logger

    def _call(self, request):
        return call_with_retry(request.execute, self._policy, self._logger)

    # --- mensajes ---
    def list_messages(self, *, query=None, label_ids=None, max_results=None, page_token=None) -> dict:
        return self._call(self._users.messages().list(
            userId='me', **_drop_none(q=query, labelIds=label_ids, maxResults=max_results,
                                      pageToken=page_token)))

    def get_message(self, message_id, *, format="full", metadata_headers=None) -> dict:
        return self._call(self._users.messages().get(
            userId='me', id=message_id, format=format, **_drop_none(metadataHeaders=metadata_headers)))

    def get_attachment(self, message_id, attachment_id) -> dict:
        return self._call(self._users.messages().attachments().get(
            userId='me', messageId=message_id, id=attachment_id))

    def modify_message(self, message_id, *, add=None, remove=None) -> None:
        body = _drop_none(addLabelIds=add, removeLabelIds=remove)
        self._call(self._users.messages().modify(userId='me', id=message_id, body=body))

    def trash_message(self, message_id) -> None:
        self._call(self._users.messages().trash(userId='me', id=message_id))

    # --- hilos ---
    def list_threads(self, *, query, max_results=None, page_token=None) -> dict:
        return self._call(self._users.threads().list(
            userId='me', q=query, **_drop_none(maxResults=max_results, pageToken=page_token)))

    def get_thread(self, thread_id, *, format="metadata", metadata_headers=None) -> dict:
        return self._call(self._users.threads().get(
            userId='me', id=thread_id, format=format, **_drop_none(metadataHeaders=metadata_headers)))

    def trash_thread(self, thread_id) -> None:
        self._call(self._users.threads().trash(userId='me', id=thread_id))

    # --- etiquetas y envío ---
    def list_labels(self) -> list[dict]:
        return self._call(self._users.labels().list(userId='me')).get('labels', [])

    def send_raw(self, raw) -> None:
        self._call(self._users.messages().send(userId='me', body={'raw': raw}))


class DryRunGmailClient:
    """Sustituto de GmailClient para DEV: lee de verdad, pero no modifica ni envía nada."""

    def __init__(self, delegate: GmailClient, logger: logging.Logger):
        self._delegate = delegate
        self._logger = logger

    def list_messages(self, **kwargs) -> dict:
        return self._delegate.list_messages(**kwargs)

    def get_message(self, message_id, **kwargs) -> dict:
        return self._delegate.get_message(message_id, **kwargs)

    def get_attachment(self, message_id, attachment_id) -> dict:
        return self._delegate.get_attachment(message_id, attachment_id)

    def list_threads(self, **kwargs) -> dict:
        return self._delegate.list_threads(**kwargs)

    def get_thread(self, thread_id, **kwargs) -> dict:
        return self._delegate.get_thread(thread_id, **kwargs)

    def list_labels(self) -> list[dict]:
        return self._delegate.list_labels()

    def modify_message(self, message_id, *, add=None, remove=None) -> None:
        self._logger.info(f"[DRY-RUN] modify {message_id} add={add} remove={remove}")

    def trash_message(self, message_id) -> None:
        self._logger.info(f"[DRY-RUN] trash message {message_id}")

    def trash_thread(self, thread_id) -> None:
        self._logger.info(f"[DRY-RUN] trash thread {thread_id}")

    def send_raw(self, raw) -> None:
        self._logger.info(f"[DRY-RUN] send email ({len(raw)} bytes)")
