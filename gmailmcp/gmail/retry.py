"""Reintentos ante errores transitorios de la API de Gmail."""
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from googleapiclient.errors import HttpError

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    retries: int = 3
    wait_seconds: float = 5
    retriable_statuses: frozenset[int] = frozenset({429, 500, 503})

    @classmethod
    def from_settings(cls, settings: dict) -> "RetryPolicy":
        gmail = settings['gmail']
        return cls(retries=gmail['rate_limit_retries'], wait_seconds=gmail['rate_limit_wait_seconds'])


def call_with_retry(func: Callable[[], T], policy: RetryPolicy, logger: logging.Logger,
                    sleep: Callable[[float], None] = time.sleep) -> T:
    for attempt in range(policy.retries):
        try:
            return func()
        except HttpError as e:
            if e.resp.status in policy.retriable_statuses and attempt < policy.retries - 1:
                logger.warning(f"Rate limit / error {e.resp.status}, reintento {attempt + 1}/"
                               f"{policy.retries} en {policy.wait_seconds}s")
                sleep(policy.wait_seconds * (attempt + 1))
            else:
                raise
