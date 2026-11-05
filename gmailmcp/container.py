"""Composition root: el único lugar que decide qué implementación concreta usa cada servicio.

Los servicios reciben interfaces (puertos) por constructor y no saben si hablan con Gmail
real, con el cliente dry-run de desarrollo o con un doble de test.
"""
from collections.abc import Callable

from gmailmcp.classification import TransactionClassifier
from gmailmcp.config import AppConfig
from gmailmcp.gmail.auth import build_gmail_service
from gmailmcp.gmail.client import DryRunGmailClient, GmailClient
from gmailmcp.gmail.retry import RetryPolicy
from gmailmcp.logging_setup import get_logger
from gmailmcp.notifications.notifier import EmailNotifier
from gmailmcp.parsers import build_default_pdf_registry, build_default_registry
from gmailmcp.repositories.settings_repo import JsonSettingsRepository
from gmailmcp.repositories.state_repo import (
    JsonBalanceRepository,
    JsonPlanRepository,
    JsonRecommendationsRepository,
    LogDirectory,
    TextNotesRepository,
)
from gmailmcp.repositories.transactions_repo import CsvTransactionRepository
from gmailmcp.services.cleanup import CleanupService
from gmailmcp.services.daily_summary import DailySummaryService
from gmailmcp.services.extractor import FinancialExtractor
from gmailmcp.services.labeler import LabelerService
from gmailmcp.services.payment_planner import PaymentPlannerService


class _LazyMailSender:
    """MailSender que solo se autentica con Gmail cuando de verdad hay que enviar."""

    def __init__(self, factory: Callable):
        self._factory = factory

    def send_raw(self, raw: str) -> None:
        self._factory().send_raw(raw)


class Container:
    def __init__(self, config: AppConfig, gmail_service_factory: Callable | None = None):
        self.config = config
        self.settings = JsonSettingsRepository(config.settings_path)
        self.transactions = CsvTransactionRepository(self.settings)
        self.balances = JsonBalanceRepository(self.settings)
        self.plans = JsonPlanRepository()
        self.notes = TextNotesRepository()
        self.recommendations = JsonRecommendationsRepository()
        self.logs = LogDirectory()
        self.parsers = build_default_registry()
        self.classifier = TransactionClassifier()
        self._gmail_service_factory = gmail_service_factory or self._build_google_service

    def _build_google_service(self, logger):
        return build_gmail_service(self.config, self.settings.load()['auth'], logger)

    def gmail(self, logger_name: str = 'gmail'):
        """Cliente nuevo por uso (igual que antes: se autentica en cada job/request)."""
        logger = get_logger(logger_name)
        client = GmailClient(self._gmail_service_factory(logger),
                             RetryPolicy.from_settings(self.settings.load()), logger)
        return DryRunGmailClient(client, logger) if self.config.dry_run else client

    def cleanup_service(self) -> CleanupService:
        return CleanupService(self.gmail('cleanup'), self.settings, get_logger('cleanup'))

    def labeler_service(self) -> LabelerService:
        return LabelerService(self.gmail('labeler'), self.settings, get_logger('labeler'))

    def extractor_service(self) -> FinancialExtractor:
        logger = get_logger('financial_extractor')
        return FinancialExtractor(self.gmail('financial_extractor'), self.parsers,
                                  build_default_pdf_registry(logger), self.transactions,
                                  self.balances, self.settings, logger)

    def planner_service(self) -> PaymentPlannerService:
        return PaymentPlannerService(self.settings, self.plans, self._notifier('payment_planner'),
                                     get_logger('payment_planner'))

    def _notifier(self, logger_name: str) -> EmailNotifier:
        return EmailNotifier(_LazyMailSender(lambda: self.gmail(logger_name)))

    def summary_service(self) -> DailySummaryService:
        domain = self.config.public_domain
        return DailySummaryService(self.settings, self._notifier('daily_summary'),
                                   get_logger('daily_summary'),
                                   dashboard_url=f"https://{domain}" if domain else '')
