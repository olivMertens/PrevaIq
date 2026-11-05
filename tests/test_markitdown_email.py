"""E-mails (.eml) become readable Markdown: headers, decoded body, attachment names only."""

from __future__ import annotations

from email.message import EmailMessage

from app.config import MarkItDownSettings
from app.markitdown_service import convert_bytes_to_markdown


def _message() -> EmailMessage:
    message = EmailMessage()
    message["From"] = "Andrea Keller <a.keller@eulachblick-schoggi.example>"
    message["To"] = "PrevaIQ Schadenservice <schaden@prevaiq.example>"
    message["Subject"] = "Schadenmeldung Hagelunwetter – Police PIQ-CH-KMU-2026-048213"
    message["Date"] = "Fri, 28 Aug 2026 16:52:00 +0200"
    return message


def test_plain_text_email_keeps_accents_and_lists_attachments_by_name() -> None:
    message = _message()
    message.set_content("Heute Morgen hat ein Hagelzug unser Schaufenster zerstört.\nGrüsse")
    message.add_attachment(
        b"\xff\xd8\xff\xe0" + b"0" * 4000,
        maintype="image",
        subtype="jpeg",
        filename="IMG_20260828_104112.jpg",
    )

    result = convert_bytes_to_markdown(bytes(message), "email-01.eml", MarkItDownSettings())

    assert result.backend == "email-parser"
    assert result.markdown.startswith("# Schadenmeldung Hagelunwetter")
    assert "**From:** Andrea Keller <a.keller@eulachblick-schoggi.example>" in result.markdown
    assert "**Attachments:** IMG_20260828_104112.jpg" in result.markdown
    assert "zerstört" in result.markdown and "Grüsse" in result.markdown
    assert "base64" not in result.markdown and "/9j/" not in result.markdown
    assert result.pages


def test_html_email_body_becomes_text() -> None:
    message = _message()
    message.set_content(
        "<html><body><p>Hagel bis <b>5 cm</b> in Winterthur.</p></body></html>", subtype="html"
    )

    markdown = convert_bytes_to_markdown(bytes(message), "mail.eml", MarkItDownSettings()).markdown

    assert "Hagel bis" in markdown and "5 cm" in markdown and "<p>" not in markdown
