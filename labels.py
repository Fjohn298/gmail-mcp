import schedule
import time
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

# ── Mapeo remitente → etiqueta ──────────────────────────────────────────────
LABEL_RULES = {

    # FINANCIERO — Recibos (Label_3)
    "Label_3": [
        "info@baccredomatic.com",
        "alertas@baccredomatic.com",
        "noreply@baccredomatic.com",
        "canalesdigitales@notificacionesbancoagricola.com",
        "transacciones@notificacionesbancoagricola.com",
        "notificaciones@notificacionesbancoagricola.com",
        "invoice+statements@mail.anthropic.com",
        "no-reply@mail.anthropic.com",
        "facturacion@claro.com.sv",
        "noreply@claro.com.sv",
        "factura@tigo.com.sv",
        "billing@openai.com",
        "receipts@netflix.com",
    ],

    # FINANCIERO — Banco Cuscatlán (Label_1834638960901538876)
    "Label_1834638960901538876": [
        "notificaciones@bancocuscatlan.com",
        "alertas@bancocuscatlan.com",
        "transacciones@bancocuscatlan.com",
        "noreply@bancocuscatlan.com",
    ],

    # TRABAJO (Label_4)
    "Label_4": [
        "no-reply@classroom.google.com",
        "classroom-noreply@google.com",
        "PlatformNotifications-noreply@google.com",
        "noreply@github.com",
        "notifications@github.com",
        "no-reply@trello.com",
        "no-reply@atlassian.com",
        "notifications@asana.com",
        "notify@slack.com",
        "noreply@notion.so",
        "no-reply@zoom.us",
        "calendar-notification@google.com",
        "no-reply@meet.google.com",
    ],

    # CURSOS (Label_2)
    "Label_2": [
        "demand@mail.datacamp.com",
        "team@datacamp.com",
        "no-reply@datacamp.com",
        "info@datacamp.com",
        "noreply@kaggle.com",
        "no-reply@coursera.org",
        "no-reply@udacity.com",
        "netec@netec.com",
        "servicio@netec.com",
        "no-reply@platzi.com",
        "info@platzi.com",
        "noreply@edx.org",
        "noreply@moure.dev",
        "hello@jaspersoft.com",
    ],

    # NEWSLETTERS / PROMOCIONES (Label_13)
    "Label_13": [
        "alejoxadam@mail.beehiiv.com",
        "no-reply@substack.com",
        "isaca@em.isaca.org",
        "googlecommunityteam-noreply@google.com",
        "noreply@youtube.com",
        "info@members.netflix.com",
        "emercadeo@iseade.edu.sv",
        "marketing@iseade.edu.sv",
        "info@utec.edu.sv",
        "admisiones@utec.edu.sv",
        "noreply@linkedin.com",
        "messages-noreply@linkedin.com",
        "jobs-noreply@linkedin.com",
        "digest-noreply@linkedin.com",
    ],

    # PERSONAL / ARCHIVO (Label_6)
    "Label_6": [
        "noreply@google.com",
        "no-reply@accounts.google.com",
        "account-recovery-noreply@google.com",
        "googleplay-noreply@google.com",
        "noreply@googlemail.com",
        "info@sv.totto.com",
        "noreply@crunchyroll.com",
        "info@airbnb.com",
        "no-reply@airbnb.com",
        "no-reply@uber.com",
        "noreply@texaco.com.sv",
        "notificaciones@leal360.co",
        "noreply@notificacionesleal360.co",
        "contacto@biblioteca.gob.sv",
        "noreply@adoc.com",
    ],
}

def get_service():
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build('gmail', 'v1', credentials=creds)

def get_existing_labels(service):
    result = service.users().labels().list(userId='me').execute()
    return {l['id']: l['name'] for l in result.get('labels', [])}

def label_emails():
    print(f"\n[Etiquetado iniciado]")
    service = get_service()
    labels_map = get_existing_labels(service)
    total = 0

    for label_id, senders in LABEL_RULES.items():
        # Verificar que la etiqueta existe
        if label_id not in labels_map:
            print(f"  ⚠️  Etiqueta {label_id} no encontrada, saltando...")
            continue

        label_name = labels_map[label_id]
        query = '(' + ' OR '.join([f'from:{s}' for s in senders]) + ') in:inbox -label:' + label_name

        labeled = 0
        page_token = None

        while True:
            params = {'userId': 'me', 'q': query, 'maxResults': 50}
            if page_token:
                params['pageToken'] = page_token

            result = service.users().threads().list(**params).execute()
            threads = result.get('threads', [])

            if not threads:
                break

            for t in threads:
                service.users().threads().modify(
                    userId='me',
                    id=t['id'],
                    body={'addLabelIds': [label_id]}
                ).execute()
                labeled += 1
                total += 1

            page_token = result.get('nextPageToken')
            if not page_token:
                break

        if labeled > 0:
            print(f"  ✅ {label_name}: {labeled} correos etiquetados")

    print(f"[Etiquetado finalizado] — Total: {total} correos\n")

# Ejecutar al iniciar y luego cada hora
label_emails()
schedule.every(1).hours.do(label_emails)

print("Scheduler activo. Ctrl+C para detener.")
while True:
    schedule.run_pending()
    time.sleep(60)