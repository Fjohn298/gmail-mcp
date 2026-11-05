"""Construcción del servicio de Gmail con OAuth (token.json / variables de entorno)."""
import logging
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from gmailmcp.config import AppConfig


def _bootstrap_from_env(config: AppConfig, token_file: str, credentials_file: str,
                        logger: logging.Logger) -> None:
    """En Railway no hay navegador: los archivos OAuth se escriben desde variables de entorno."""
    if config.gmail_token_json and not os.path.exists(token_file):
        with open(token_file, 'w', encoding='utf-8') as f:
            f.write(config.gmail_token_json)
        logger.info("token.json cargado desde variable de entorno GMAIL_TOKEN_JSON")
    if config.gmail_credentials_json and not os.path.exists(credentials_file):
        with open(credentials_file, 'w', encoding='utf-8') as f:
            f.write(config.gmail_credentials_json)
        logger.info("credentials.json cargado desde GMAIL_CREDENTIALS_JSON")


def build_gmail_service(config: AppConfig, auth_settings: dict, logger: logging.Logger):
    token_file = auth_settings['token_file']
    credentials_file = auth_settings['credentials_file']
    scopes = auth_settings['scopes']
    _bootstrap_from_env(config, token_file, credentials_file, logger)

    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, scopes)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'w', encoding='utf-8') as f:
            f.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)
