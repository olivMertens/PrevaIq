from __future__ import annotations

from unittest.mock import Mock

import pytest
from requests import HTTPError

from app import access_notifications


@pytest.fixture()
def sender(monkeypatch):
    for key, value in {
        "ACCESS_EMAIL_ENDPOINT": "https://email.communication.azure.com",
        "ACCESS_EMAIL_SENDER": "sender@example.com",
        "ACCESS_REQUEST_EMAIL": "owner@example.com",
        "ACCESS_ADMIN_URL": "https://demo.example.com/admin",
        "AZURE_CLIENT_ID": "managed-identity",
    }.items():
        monkeypatch.setenv(key, value)
    credential = Mock()
    credential.__enter__ = Mock(return_value=credential)
    credential.__exit__ = Mock(return_value=False)
    credential.get_token.return_value.token = "test-token"
    monkeypatch.setattr(
        access_notifications, "ManagedIdentityCredential", Mock(return_value=credential)
    )
    post = Mock(return_value=Mock(status_code=202))
    monkeypatch.setattr(access_notifications.requests, "post", post)
    return post


def test_submission_is_bounded_and_does_not_claim_delivery(sender) -> None:
    operation_id = access_notifications.submit("colleague@example.com", "Colleague", "2026-01-01")
    args, kwargs = sender.call_args
    assert args[0].endswith("/emails:send?api-version=2023-03-31")
    assert kwargs["timeout"] == (3, 10)
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert kwargs["headers"]["Operation-Id"] == operation_id
    assert kwargs["json"]["recipients"]["to"] == [{"address": "owner@example.com"}]
    assert "https://demo.example.com/admin" in kwargs["json"]["content"]["plainText"]
    html = kwargs["json"]["content"]["html"]
    assert 'href="https://demo.example.com/admin"' in html
    assert "Review access requests" in html
    assert 'href="mailto:owner@example.com"' in html
    assert kwargs["json"]["replyTo"] == [{"address": "owner@example.com"}]
    sender.assert_called_once()


def test_provider_rejection_is_not_success(sender) -> None:
    sender.return_value.status_code = 403
    with pytest.raises(HTTPError, match="403"):
        access_notifications.submit("colleague@example.com", None, "2026-01-01")


def test_missing_configuration_does_not_call_provider(sender, monkeypatch) -> None:
    monkeypatch.delenv("ACCESS_EMAIL_SENDER")
    with pytest.raises(ValueError, match="incomplete"):
        access_notifications.submit("colleague@example.com", None, "2026-01-01")
    sender.assert_not_called()


def test_approval_targets_requester_and_copies_administrator_with_login_button(sender) -> None:
    access_notifications.submit_approval("colleague@example.com", "Colleague", "2026-01-01")
    message = sender.call_args.kwargs["json"]
    assert message["recipients"] == {
        "to": [{"address": "colleague@example.com"}],
        "cc": [{"address": "owner@example.com"}],
    }
    assert "approved" in message["content"]["subject"]
    assert 'href="https://demo.example.com/login"' in message["content"]["html"]
    assert "Open PrevaIQ" in message["content"]["html"]
    assert 'href="mailto:owner@example.com"' in message["content"]["html"]
    assert "https://demo.example.com/login" in message["content"]["plainText"]
    assert message["replyTo"] == [{"address": "owner@example.com"}]


def test_approval_of_administrator_does_not_duplicate_the_recipient(sender) -> None:
    access_notifications.submit_approval("OWNER@example.com", None, "2026-01-01")
    assert "cc" not in sender.call_args.kwargs["json"]["recipients"]


def test_dynamic_email_content_is_escaped_and_no_remote_assets_are_loaded(sender) -> None:
    access_notifications.submit("colleague@example.com", '<img src=x onerror="bad()">', "today")
    html = sender.call_args.kwargs["json"]["content"]["html"]
    assert "<img" not in html
    assert "&lt;img" in html
    assert "<script" not in html


def test_approval_rejection_is_not_success(sender) -> None:
    sender.return_value.status_code = 429
    with pytest.raises(HTTPError, match="429"):
        access_notifications.submit_approval("colleague@example.com", None, "today")
