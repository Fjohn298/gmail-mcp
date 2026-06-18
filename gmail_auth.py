import os
import json
import time
import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

def load_settings():
    with open('config/settings.json', 'r') as f:
        return json.load(f)

def _bootstrap_credentials_from_env():
    """On Railway: write token.json and credentials.json from env vars if files are absent."""
    token_env = os.environ.get('GMAIL_TOKEN_JSON')
    creds_env = os.environ.get('GMAIL_CREDENTIALS_JSON')
    if token_env and not os.path.exists('token.json'):
        with open('token.json', 'w') as f:
            f.write(token_env)
        logger.info("token.json cargado desde variable de entorno GMAIL_TOKEN_JSON")
    if creds_env and not os.path.exists('credentials.json'):
        with open('credentials.json', 'w') as f:
            f.write(creds_env)
        logger.info("credentials.json cargado desde GMAIL_CREDENTIALS_JSON")

def get_service():
    _bootstrap_credentials_from_env()
    settings = load_settings()
    token_file = settings['auth']['token_file']
    credentials_file = settings['auth']['credentials_file']
    scopes = settings['auth']['scopes']

    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, scopes)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'w') as f:
            f.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def api_call_with_retry(func, *args, **kwargs):
    """Ejecuta una llamada a la API con reintentos ante rate limiting."""
    settings = load_settings()
    retries = settings['gmail']['rate_limit_retries']
    wait = settings['gmail']['rate_limit_wait_seconds']

    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except HttpError as e:
            if e.resp.status in (429, 500, 503) and attempt < retries - 1:
                logger.warning(f"Rate limit / error {e.resp.status}, reintento {attempt + 1}/{retries} en {wait}s")
                time.sleep(wait * (attempt + 1))
            else:
                raise
