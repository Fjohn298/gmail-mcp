import os
import json
from mcp.server.fastmcp import FastMCP
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

mcp = FastMCP("gmail")

def get_gmail_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as t:
            t.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

@mcp.tool()
def listar_correos(cantidad: int = 10, query: str = "") -> str:
    """Lista los correos más recientes del inbox"""
    service = get_gmail_service()
    result = service.users().messages().list(
        userId='me', maxResults=cantidad, q=query
    ).execute()
    messages = result.get('messages', [])
    correos = []
    for msg in messages:
        m = service.users().messages().get(
            userId='me', id=msg['id'], format='metadata',
            metadataHeaders=['Subject','From','Date']
        ).execute()
        headers = {h['name']: h['value'] for h in m['payload']['headers']}
        correos.append({
            'id': msg['id'],
            'asunto': headers.get('Subject',''),
            'de': headers.get('From',''),
            'fecha': headers.get('Date',''),
            'snippet': m.get('snippet','')[:100]
        })
    return json.dumps(correos, ensure_ascii=False, indent=2)

@mcp.tool()
def leer_correo(message_id: str) -> str:
    """Lee el contenido completo de un correo por su ID"""
    service = get_gmail_service()
    m = service.users().messages().get(
        userId='me', id=message_id, format='full'
    ).execute()
    headers = {h['name']: h['value'] for h in m['payload']['headers']}
    snippet = m.get('snippet', '')
    return json.dumps({
        'id': message_id,
        'asunto': headers.get('Subject',''),
        'de': headers.get('From',''),
        'fecha': headers.get('Date',''),
        'contenido': snippet
    }, ensure_ascii=False, indent=2)

@mcp.tool()
def mover_a_spam(message_id: str) -> str:
    """Mueve un correo a spam"""
    service = get_gmail_service()
    service.users().messages().modify(
        userId='me', id=message_id,
        body={'addLabelIds': ['SPAM'], 'removeLabelIds': ['INBOX']}
    ).execute()
    return f"Correo {message_id} movido a spam"

@mcp.tool()
def archivar_correo(message_id: str) -> str:
    """Archiva un correo removiéndolo del inbox"""
    service = get_gmail_service()
    service.users().messages().modify(
        userId='me', id=message_id,
        body={'removeLabelIds': ['INBOX']}
    ).execute()
    return f"Correo {message_id} archivado"

@mcp.tool()
def eliminar_correo(message_id: str) -> str:
    """Mueve un correo a la papelera"""
    service = get_gmail_service()
    service.users().messages().trash(
        userId='me', id=message_id
    ).execute()
    return f"Correo {message_id} enviado a papelera"

if __name__ == "__main__":
    mcp.run(transport='stdio')