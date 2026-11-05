"""Parseo de correos y estados de cuenta bancarios."""
from gmailmcp.parsers.banks import build_default_registry
from gmailmcp.parsers.base import BankParser, EmailContent, ParserRegistry
from gmailmcp.parsers.mime import get_body_and_attachments
from gmailmcp.parsers.pdf_statements import build_default_pdf_registry

__all__ = ["BankParser", "EmailContent", "ParserRegistry", "build_default_registry",
           "build_default_pdf_registry", "get_body_and_attachments"]
