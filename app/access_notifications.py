"""Bounded request and approval notifications through ACS Email."""

from __future__ import annotations

import os
from html import escape
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import requests
from azure.core.pipeline.transport import RequestsTransport
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

from app.brands import get_current_brand_profile


def _html(title: str, paragraphs: list[str], button: str, url: str, contact: str) -> str:
    brand = get_current_brand_profile()
    body = "".join(f'<p style="margin:0 0 16px">{escape(text)}</p>' for text in paragraphs)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"></head>'
        '<body style="margin:0;padding:24px;background:#F5F7FA;'
        'font-family:Arial,sans-serif;color:#17395C">'
        '<table role="presentation" style="width:100%;max-width:600px;margin:0 auto;'
        'border:1px solid #DAE2EB;border-radius:12px;background:#FFFFFF"><tr>'
        '<td style="padding:32px">'
        f'<p style="margin:0 0 24px;font-size:22px;font-weight:bold">{escape(brand.app_name)}</p>'
        f'<h1 style="margin:0 0 20px;font-size:24px">{escape(title)}</h1>{body}'
        f'<p style="margin:24px 0"><a href="{escape(url, quote=True)}" '
        f'style="display:inline-block;background:{brand.primary};color:#FFFFFF;'
        'padding:14px 24px;border-radius:6px;font-weight:bold;text-decoration:none">'
        f"{escape(button)}</a></p>"
        '<p style="margin:24px 0 0;padding-top:20px;border-top:1px solid #DAE2EB;'
        'font-size:14px">Questions? Contact / Contacter : '
        f'<a href="mailto:{escape(contact, quote=True)}" style="color:{brand.primary}">'
        f"{escape(contact)}</a></p></td></tr></table></body></html>"
    )


def _send(email: str, name: str | None, date: str, *, approved: bool) -> str:
    """Return the operation ID after ACS accepts the message, not mailbox delivery."""
    endpoint = os.getenv("ACCESS_EMAIL_ENDPOINT", "").rstrip("/")
    sender = os.getenv("ACCESS_EMAIL_SENDER", "")
    contact = os.getenv("ACCESS_REQUEST_EMAIL", "")
    admin_url = os.getenv("ACCESS_ADMIN_URL", "")
    if not all((endpoint, sender, contact, admin_url)):
        raise ValueError("access email configuration is incomplete")
    if urlsplit(endpoint).scheme != "https" or urlsplit(admin_url).scheme != "https":
        raise ValueError("access email endpoints must use HTTPS")
    brand = get_current_brand_profile()
    if approved:
        recipient = email
        title = f"Your {brand.app_name} access is approved"
        button = f"Open {brand.app_name}"
        parsed = urlsplit(admin_url)
        url = urlunsplit((parsed.scheme, parsed.netloc, "/login", "", ""))
        paragraphs = [
            f"Hello {name or email},",
            "Your demo access has been approved. Votre acces a la demo est approuve.",
            f"Account: {email}",
            f"Approved on: {date}",
            "Use the button below and sign in with this approved Microsoft Entra ID account.",
            "This approval grants demo user access only, not administration.",
        ]
    else:
        recipient = contact
        title = f"New {brand.app_name} access request"
        button = "Review access requests"
        url = admin_url
        paragraphs = [
            "A Microsoft Entra ID user is requesting demo access.",
            "Un utilisateur Microsoft Entra ID demande l'acces a la demo.",
            f"Name: {name or email}",
            f"Email: {email}",
            f"Requested on: {date}",
            "Sign in as administrator to approve or refuse. This email does not grant access.",
        ]
    recipients = {"to": [{"address": recipient}]}
    if approved and recipient.casefold() != contact.casefold():
        recipients["cc"] = [{"address": contact}]
    content = {
        "subject": title,
        "plainText": "\n\n".join(paragraphs + [f"{button}: {url}", f"Contact: {contact}"]),
        "html": _html(title, paragraphs, button, url, contact),
    }
    operation_id = str(uuid4())
    transport = RequestsTransport(connection_timeout=3, read_timeout=3)
    client_id = os.getenv("AZURE_CLIENT_ID")
    credential = (
        ManagedIdentityCredential(client_id=client_id, transport=transport, retry_total=0)
        if client_id
        else DefaultAzureCredential(transport=transport, retry_total=0)
    )
    with credential:
        token = credential.get_token("https://communication.azure.com/.default").token
        response = requests.post(
            f"{endpoint}/emails:send?api-version=2023-03-31",
            headers={"Authorization": f"Bearer {token}", "Operation-Id": operation_id},
            json={
                "senderAddress": sender,
                "recipients": recipients,
                "replyTo": [{"address": contact}],
                "content": content,
            },
            timeout=(3, 10),
        )
    if response.status_code != 202:
        raise requests.HTTPError(f"ACS submission returned HTTP {response.status_code}")
    return operation_id


def submit(email: str, name: str | None, requested_at: str) -> str:
    return _send(email, name, requested_at, approved=False)


def submit_approval(email: str, name: str | None, approved_at: str) -> str:
    return _send(email, name, approved_at, approved=True)
