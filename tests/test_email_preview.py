"""The document viewer shows e-mails as a mail client does, instead of downloading the .eml."""

from __future__ import annotations

from email.message import EmailMessage

from app.email_preview import email_preview, html_text


def _message() -> EmailMessage:
    message = EmailMessage()
    message["From"] = "Daniel Hartley <d.hartley@eulachblick-schoggi.example>"
    message["To"] = "PrevaIQ Claims Service <schaden@prevaiq.example>"
    message["Cc"] = "Andrea Keller <a.keller@eulachblick-schoggi.example>"
    message["Subject"] = "Claim PIQ-S-2026-082814 – consolidated loss estimate"
    message["Date"] = "Tue, 01 Sep 2026 18:05:00 +0200"
    return message


def test_plain_email_has_headers_body_and_attachments_flagged_when_in_the_case() -> None:
    message = _message()
    message.set_content("Dear Sir or Madam,\n\nOur estimate amounts to CHF 1,697,400.00.\nGrüsse")
    message.add_attachment(
        b"%PDF-1.7 claim", maintype="application", subtype="pdf", filename="schadenmeldung.pdf"
    )
    message.add_attachment(
        b"\xff\xd8\xff" + b"0" * 997, maintype="image", subtype="jpeg", filename="IMG_1.jpg"
    )

    preview = email_preview(bytes(message), case_files=["SCHADENMELDUNG.pdf", "other.jpg"])

    assert preview["subject"] == "Claim PIQ-S-2026-082814 – consolidated loss estimate"
    assert preview["from"] == "Daniel Hartley <d.hartley@eulachblick-schoggi.example>"
    assert preview["cc"] == "Andrea Keller <a.keller@eulachblick-schoggi.example>"
    assert preview["date"] == "Tue, 01 Sep 2026 18:05:00 +0200"
    assert preview["date_iso"] == "2026-09-01T18:05:00+02:00"
    assert preview["body_format"] == "text"
    assert (
        preview["body"] == "Dear Sir or Madam,\n\nOur estimate amounts to CHF 1,697,400.00.\nGrüsse"
    )
    assert preview["attachments"] == [
        {
            "filename": "schadenmeldung.pdf",
            "content_type": "application/pdf",
            "size": 14,
            "in_case": True,
        },
        {"filename": "IMG_1.jpg", "content_type": "image/jpeg", "size": 1000, "in_case": False},
    ]


def test_html_body_becomes_markdown_or_plain_text() -> None:
    message = _message()
    message.set_content(
        "<html><head><style>p{color:red}</style></head><body><p>Hagel bis <b>5 cm</b>.</p>"
        "<script>alert(1)</script><div>Grüsse</div></body></html>",
        subtype="html",
    )

    converted = email_preview(bytes(message), html_to_markdown=lambda html: "Hagel bis **5 cm**.")
    assert (converted["body"], converted["body_format"]) == ("Hagel bis **5 cm**.", "markdown")

    fallback = email_preview(bytes(message), html_to_markdown=lambda html: None)
    assert (fallback["body"], fallback["body_format"]) == ("Hagel bis 5 cm.\n\nGrüsse", "text")
    assert "alert" not in fallback["body"] and "color" not in fallback["body"]


def test_unknown_date_and_missing_headers_stay_empty() -> None:
    message = EmailMessage()
    message["Date"] = "sometime last week"
    message.set_content("Body")

    preview = email_preview(bytes(message))

    assert (preview["subject"], preview["from"], preview["cc"]) == ("", "", "")
    assert preview["date_iso"] is None
    assert preview["attachments"] == []


def test_html_text_keeps_one_line_per_block() -> None:
    assert (
        html_text("<p>One</p><p>Two <i>three</i></p><ul><li>a</li><li>b</li></ul>")
        == "One\n\nTwo three\n\na\nb"
    )
