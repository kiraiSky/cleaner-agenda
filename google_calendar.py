"""
Integração com Google Calendar.
Gere OAuth2 e sincronização de limpezas.
"""
import os
import json
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/calendar']
TOKEN_FILE = 'token.json'
CALENDAR_ID = 'primary'  # Agenda principal do utilizador


def get_flow(redirect_uri):
    """Cria o flow OAuth2."""
    client_config = {
        "web": {
            "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
            "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    return Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)


def get_credentials():
    """Carrega credenciais guardadas. Retorna None se não existirem."""
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            save_credentials(creds)
        return creds if creds and creds.valid else None
    except Exception:
        return None


def save_credentials(creds):
    """Guarda credenciais no ficheiro token.json."""
    with open(TOKEN_FILE, 'w') as f:
        f.write(creds.to_json())


def is_connected():
    """Verifica se há credenciais válidas."""
    return get_credentials() is not None


def get_service():
    """Retorna o serviço Google Calendar ou None."""
    creds = get_credentials()
    if not creds:
        return None
    try:
        return build('calendar', 'v3', credentials=creds)
    except Exception:
        return None


def limpeza_to_event(limpeza):
    """Converte uma Limpeza num evento Google Calendar."""
    inicio = limpeza.data_hora
    fim = inicio + timedelta(hours=limpeza.duracao_horas or 2)

    descricao_parts = []
    if limpeza.notas:
        descricao_parts.append(limpeza.notas)
    if limpeza.pagamento:
        descricao_parts.append(f"Valor: {limpeza.pagamento.valor:.0f}€")
        descricao_parts.append(f"Pagamento: {'Pago ✓' if limpeza.pagamento.pago else 'Por pagar'}")
    if limpeza.cliente.morada:
        descricao_parts.append(f"Morada: {limpeza.cliente.morada}")
    if limpeza.cliente.telefone:
        descricao_parts.append(f"Tel: {limpeza.cliente.telefone}")

    return {
        'summary': f"🧹 {limpeza.cliente.nome}",
        'description': '\n'.join(descricao_parts),
        'location': limpeza.cliente.morada or '',
        'start': {
            'dateTime': inicio.isoformat(),
            'timeZone': 'Europe/Lisbon',
        },
        'end': {
            'dateTime': fim.isoformat(),
            'timeZone': 'Europe/Lisbon',
        },
        'colorId': '2' if limpeza.estado == 'concluida' else '10',  # verde
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'popup', 'minutes': 60},
                {'method': 'popup', 'minutes': 15},
            ],
        },
    }


def sync_limpeza(limpeza):
    """
    Sincroniza uma limpeza individual.
    Cria ou atualiza o evento na Google Agenda.
    Retorna o ID do evento ou None em caso de erro.
    """
    service = get_service()
    if not service:
        return None
    try:
        event_body = limpeza_to_event(limpeza)
        # Se já existe um evento para esta limpeza, atualizar
        if limpeza.google_event_id:
            try:
                event = service.events().update(
                    calendarId=CALENDAR_ID,
                    eventId=limpeza.google_event_id,
                    body=event_body
                ).execute()
                return event.get('id')
            except HttpError as e:
                if e.resp.status == 404:
                    # Evento não existe mais, criar novo
                    pass
                else:
                    return None
        # Criar novo evento
        event = service.events().insert(
            calendarId=CALENDAR_ID,
            body=event_body
        ).execute()
        return event.get('id')
    except Exception:
        return None


def delete_event(event_id):
    """Apaga um evento da Google Agenda."""
    service = get_service()
    if not service or not event_id:
        return
    try:
        service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
    except Exception:
        pass


def sync_all(limpezas):
    """
    Sincroniza todas as limpezas agendadas.
    Retorna (sucesso, falha).
    """
    service = get_service()
    if not service:
        return 0, 0
    sucesso = 0
    falha = 0
    for l in limpezas:
        if l.estado == 'cancelada':
            continue
        event_id = sync_limpeza(l)
        if event_id:
            l.google_event_id = event_id
            sucesso += 1
        else:
            falha += 1
    return sucesso, falha
