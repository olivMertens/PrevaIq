"""Readable view of an e-mail file (.eml): headers, body and attachment list.

Shared by the extraction (Markdown for the analyses) and the document viewer, so both read
the same MIME structure. Attachment bytes are never returned, only their names and sizes.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Final, Optional

MAX_EMAIL_BYTES: Final = 25 * 1024 * 1024
HEADERS: Final = ("From", "To", "Cc", "Date")


def read_message(file_bytes: bytes) -> EmailMessage:
    message = BytesParser(policy=policy.default).parsebytes(file_bytes)
    assert isinstance(message, EmailMessage)
    return message


def readable_body(message: EmailMessage) -> tuple[str, bool]:
    """Body text (plain text preferred) and whether it is HTML."""
    body = message.get_body(preferencelist=("plain", "html"))
    if body is None:
        return "", False
    return str(body.get_content()), body.get_content_type() == "text/html"


def attachments(message: EmailMessage) -> list[dict[str, Any]]:
    """Name, type and size of each named attachment."""
    found = []
    for part in message.iter_attachments():
        name = part.get_filename()
        if not name:
            continue
        payload = part.get_payload(decode=True)
        found.append(
            {
                "filename": name,
                "content_type": part.get_content_type(),
                "size": len(payload) if isinstance(payload, bytes) else 0,
            }
        )
    return found


class _TextOnly(HTMLParser):
    """Visible text of an HTML body: blocks separated by a blank line, list items by a line."""

    _BLOCKS = {"p", "div", "table", "h1", "h2", "h3", "h4", "h5", "h6"}
    _LINES = {"br", "li", "tr"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag in {"script", "style", "head"}:
            self._hidden += 1
        elif tag in self._BLOCKS or tag in self._LINES:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "head"}:
            self._hidden = max(0, self._hidden - 1)
        elif tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._hidden:
            self.parts.append(data)


def html_text(html: str) -> str:
    parser = _TextOnly()
    parser.feed(html)
    parser.close()
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in "".join(parser.parts).splitlines())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _iso_date(value: str) -> Optional[str]:
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError, IndexError):
        return None


def email_preview(
    file_bytes: bytes,
    case_files: Iterable[str] = (),
    html_to_markdown: Optional[Callable[[str], str]] = None,
) -> dict[str, Any]:
    """What a mail client shows: headers, readable body, attachments (flagged when the case
    also holds a file with the same name, so the viewer can open it)."""
    message = read_message(file_bytes)
    body, is_html = readable_body(message)
    body_format = "text"
    if is_html:
        converted = html_to_markdown(body) if html_to_markdown else None
        body, body_format = (converted, "markdown") if converted else (html_text(body), "text")
    in_case = {name.lower() for name in case_files}
    date = str(message.get("Date") or "")
    return {
        "subject": str(message.get("Subject") or "").strip(),
        "from": str(message.get("From") or ""),
        "to": str(message.get("To") or ""),
        "cc": str(message.get("Cc") or ""),
        "date": date,
        "date_iso": _iso_date(date) if date else None,
        "body": body.replace("\r\n", "\n").strip(),
        "body_format": body_format,
        "attachments": [
            {**item, "in_case": item["filename"].lower() in in_case}
            for item in attachments(message)
        ],
    }
