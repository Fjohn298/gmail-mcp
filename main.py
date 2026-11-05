"""Servidor MCP de Gmail (transporte stdio) para clientes como Claude Desktop."""
import json
import os
from dataclasses import replace

from mcp.server.fastmcp import FastMCP

from gmailmcp.config import AppConfig
from gmailmcp.container import Container

mcp = FastMCP("gmail")


def _container() -> Container:
    config = AppConfig.from_env()
    # Las herramientas MCP las invoca el usuario a propósito: solo se simulan si DRY_RUN se pide.
    if 'DRY_RUN' not in os.environ:
        config = replace(config, dry_run=False)
    return Container(config)


def _gmail():
    return _container().gmail('mcp')


@mcp.tool()
def listar_correos(cantidad: int = 10, query: str = "") -> str:
    """Lista los correos más recientes del inbox (id, asunto, remitente, fecha y extracto)."""
    gmail = _gmail()
    correos = []
    for msg in gmail.list_messages(query=query, max_results=cantidad).get('messages', []):
        m = gmail.get_message(msg['id'], format='metadata', metadata_headers=['Subject', 'From', 'Date'])
        headers = {h['name']: h['value'] for h in m['payload']['headers']}
        correos.append({'id': msg['id'], 'asunto': headers.get('Subject', ''),
                        'de': headers.get('From', ''), 'fecha': headers.get('Date', ''),
                        'snippet': m.get('snippet', '')[:100]})
    return json.dumps(correos, ensure_ascii=False, indent=2)


@mcp.tool()
def leer_correo(message_id: str) -> str:
    """Devuelve asunto, remitente, fecha y el extracto (snippet) de un correo por su ID."""
    m = _gmail().get_message(message_id, format='full')
    headers = {h['name']: h['value'] for h in m['payload']['headers']}
    return json.dumps({'id': message_id, 'asunto': headers.get('Subject', ''),
                       'de': headers.get('From', ''), 'fecha': headers.get('Date', ''),
                       'contenido': m.get('snippet', '')}, ensure_ascii=False, indent=2)


@mcp.tool()
def mover_a_spam(message_id: str) -> str:
    """Mueve un correo a spam"""
    _gmail().modify_message(message_id, add=['SPAM'], remove=['INBOX'])
    return f"Correo {message_id} movido a spam"


@mcp.tool()
def archivar_correo(message_id: str) -> str:
    """Archiva un correo removiéndolo del inbox"""
    _gmail().modify_message(message_id, remove=['INBOX'])
    return f"Correo {message_id} archivado"


@mcp.tool()
def eliminar_correo(message_id: str) -> str:
    """Mueve un correo a la papelera (recuperable desde Gmail)"""
    _gmail().trash_message(message_id)
    return f"Correo {message_id} enviado a papelera"


if __name__ == "__main__":
    mcp.run(transport='stdio')
