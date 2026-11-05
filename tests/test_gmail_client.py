import logging

import pytest
from googleapiclient.errors import HttpError

from gmailmcp.gmail.client import DryRunGmailClient, GmailClient
from gmailmcp.gmail.retry import RetryPolicy, call_with_retry
from tests.fakes import FakeGmailService, make_message

log = logging.getLogger("test")


class _Resp(dict):
    def __init__(self, status):
        super().__init__()
        self.status = status
        self.reason = "x"


def _http_error(status):
    return HttpError(_Resp(status), b"error")


def test_reintenta_errores_transitorios_y_luego_responde():
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise _http_error(429)
        return "ok"

    assert call_with_retry(flaky, RetryPolicy(retries=3, wait_seconds=0), log, sleep=lambda s: None) == "ok"
    assert len(attempts) == 3


def test_no_reintenta_errores_permanentes():
    attempts = []

    def not_found():
        attempts.append(1)
        raise _http_error(404)

    with pytest.raises(HttpError):
        call_with_retry(not_found, RetryPolicy(retries=3, wait_seconds=0), log, sleep=lambda s: None)
    assert len(attempts) == 1


def test_dry_run_lee_pero_no_modifica_ni_envia():
    """Liskov: el cliente dry-run se usa en lugar del real sin que el servicio note la diferencia."""
    service = FakeGmailService([make_message("m1", "a@b.com", "s", "b")])
    dry = DryRunGmailClient(GmailClient(service, RetryPolicy(wait_seconds=0), log), log)

    assert dry.list_messages(query="in:inbox")["messages"][0]["id"] == "m1"
    dry.modify_message("m1", add=["Label_3"])
    dry.trash_thread("tm1")
    dry.send_raw("abc")

    assert service.msgs["m1"]["labelIds"] == ["INBOX"]
    assert service.trashed == set() and service.sent == []
