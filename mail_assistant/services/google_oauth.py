
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet
from django.conf import settings
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import base64
from datetime import datetime, timezone as dt_timezone

import base64
from email.mime.text import MIMEText

import os

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def get_encryption_key():
    key = os.getenv("FERNET_KEY")

    if not key:
        raise RuntimeError("FERNET_KEY is missing from .env")

    return key.encode()


def encrypt_credentials(credentials):
    fernet = Fernet(get_encryption_key())
    credentials_json = credentials.to_json()

    return fernet.encrypt(
        credentials_json.encode()
    ).decode()


def decrypt_credentials(encrypted_data):
    fernet = Fernet(get_encryption_key())

    decrypted = fernet.decrypt(
        encrypted_data.encode()
    )

    return json.loads(decrypted.decode())



def get_client_secrets_path():
    path = os.getenv("GOOGLE_CLIENT_SECRETS_FILE")

    print("DEBUG OAuth path:", repr(path))
    print("DEBUG OAuth file exists:", os.path.isfile(path) if path else False)

    if not path:
        raise ValueError("GOOGLE_CLIENT_SECRETS_FILE is not configured.")

    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Google OAuth credentials file not found: {path}"
        )

    return path    



def create_oauth_flow(state=None):
    flow = Flow.from_client_secrets_file(
        get_client_secrets_path(),
        scopes=SCOPES,
        state=state,
        autogenerate_code_verifier=True,
    )

    flow.redirect_uri = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "http://127.0.0.1:8000/gmail/oauth/callback/"
)

    return flow



def get_gmail_profile(credentials):
    service = build(
        "gmail",
        "v1",
        credentials=credentials
    )

    return service.users().getProfile(
        userId="me"
    ).execute()


def get_gmail_service(account):
    credentials_data = decrypt_credentials(
        account.encrypted_credentials
    )

    credentials = Credentials.from_authorized_user_info(
        credentials_data,
        SCOPES
    )

    service = build(
        "gmail",
        "v1",
        credentials=credentials
    )

    return service


def fetch_recent_messages(account, max_results=20):
    service = get_gmail_service(account)

    response = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        maxResults=max_results
    ).execute()

    message_ids = response.get("messages", [])
    emails = []

    for item in message_ids:
        message = service.users().messages().get(
            userId="me",
            id=item["id"],
            format="full"
        ).execute()

        emails.append(message)

    return emails



def extract_email_data(message):
    headers = message.get("payload", {}).get("headers", [])

    header_map = {
        header["name"].lower(): header["value"]
        for header in headers
    }

    sender = header_map.get("from", "Unknown")
    subject = header_map.get("subject", "(No subject)")
    date_value = message.get("internalDate")

    sender_name = ""
    sender_email = sender

    if "<" in sender and ">" in sender:
        sender_name = sender.split("<")[0].strip().strip('"')
        sender_email = sender.split("<")[1].split(">")[0].strip()

    def extract_body(payload):
        mime_type = payload.get("mimeType", "")
        body_data = payload.get("body", {}).get("data")

        if mime_type == "text/plain" and body_data:
            decoded = base64.urlsafe_b64decode(
                body_data + "=" * (-len(body_data) % 4)
            )
            return decoded.decode("utf-8", errors="replace")

        for part in payload.get("parts", []):
            result = extract_body(part)
            if result:
                return result

        return ""

    body = extract_body(message.get("payload", {}))

    if not body:
        body = message.get("snippet", "")

    received_at = None

    if date_value:
        received_at = datetime.fromtimestamp(
            int(date_value) / 1000,
            tz=dt_timezone.utc
        )

    labels = message.get("labelIds", [])

    return {
        "gmail_message_id": message["id"],
        "thread_id": message.get("threadId", ""),
        "sender_email": sender_email,
        "sender_name": sender_name,
        "subject": subject,
        "body": body,
        "snippet": message.get("snippet", ""),
        "received_at": received_at,
        "is_read": "UNREAD" not in labels,
    }

def send_email_reply(account, recipient, subject, body):
    service = get_gmail_service(account)

    message = MIMEText(body, "plain", "utf-8")
    message["to"] = recipient
    message["subject"] = (
        subject if subject.lower().startswith("re:") else f"Re: {subject}"
    )

    raw_message = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode("utf-8")

    result = service.users().messages().send(
        userId="me",
        body={"raw": raw_message}
    ).execute()

    return result
 