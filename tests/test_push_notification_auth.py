import asyncio

from app.a2a.push_notification_auth import PushNotificationSenderAuth


def test_push_url_rejects_loopback():
    assert not asyncio.run(
        PushNotificationSenderAuth._is_safe_push_url("https://127.0.0.1/callback")
    )


def test_push_url_rejects_private_network():
    assert not asyncio.run(
        PushNotificationSenderAuth._is_safe_push_url("https://10.0.0.10/callback")
    )


def test_push_url_requires_https_by_default():
    assert not asyncio.run(
        PushNotificationSenderAuth._is_safe_push_url("http://example.com/callback")
    )


def test_push_url_rejects_embedded_credentials():
    assert not asyncio.run(
        PushNotificationSenderAuth._is_safe_push_url(
            "https://user:password@example.com/callback"
        )
    )
