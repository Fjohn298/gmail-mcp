"""Extracción del texto plano y de los PDF adjuntos de un payload MIME de Gmail."""
import base64


def get_body_and_attachments(payload: dict) -> tuple[str, list[tuple[str, str, str]]]:
    """Retorna (texto_plano, [(filename, attachment_id, mime_type)])."""
    body_text = ''
    attachments = []

    def walk(part):
        nonlocal body_text
        mime = part.get('mimeType', '')
        if mime == 'text/plain':
            data = part.get('body', {}).get('data', '')
            if data:
                body_text += base64.urlsafe_b64decode(data + '==').decode('utf-8', errors='ignore')
        elif mime == 'application/pdf':
            att_id = part.get('body', {}).get('attachmentId', '')
            fname = part.get('filename', 'attachment.pdf')
            if att_id:
                attachments.append((fname, att_id, mime))
        for sub in part.get('parts', []):
            walk(sub)

    walk(payload)
    return body_text, attachments
