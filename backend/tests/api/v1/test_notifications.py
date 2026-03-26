"""Tests for notification endpoints."""
from decimal import Decimal

import pytest


BASE_URL = "/api/v1/notifications"


class TestUnreadCount:
    def test_unread_count_empty(self, client):
        response = client.get(f"{BASE_URL}/unread-count")
        assert response.status_code == 200
        data = response.json()
        assert "unread_count" in data

    def test_unread_count_after_create(self, client, db):
        from app.services import notification_service

        notification_service.create_notification(
            db,
            thread_subject="Test thread",
            body="Hello",
        )
        response = client.get(f"{BASE_URL}/unread-count")
        assert response.status_code == 200
        assert response.json()["unread_count"] >= 1


class TestListThreads:
    def test_list_empty(self, client):
        response = client.get(BASE_URL)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_with_thread(self, client, db):
        from app.services import notification_service

        notification_service.create_notification(
            db,
            thread_subject="Order SO-2026-001 confirmed",
            body="Your order has been confirmed.",
            sender_type="system",
        )
        response = client.get(BASE_URL)
        assert response.status_code == 200
        threads = response.json()
        assert len(threads) >= 1
        thread = threads[0]
        assert "thread_id" in thread
        assert "thread_subject" in thread
        assert "message_count" in thread
        assert "unread_count" in thread

    def test_list_unread_only(self, client, db):
        from app.services import notification_service

        n = notification_service.create_notification(
            db, thread_subject="Read thread", body="Read message"
        )
        notification_service.mark_read(db, n.id)

        response = client.get(f"{BASE_URL}?unread_only=true")
        assert response.status_code == 200
        # The read thread should not appear in unread_only
        threads = response.json()
        read_thread_ids = [t["thread_id"] for t in threads]
        assert n.thread_id not in read_thread_ids


class TestGetThread:
    def test_get_thread(self, client, db):
        from app.services import notification_service

        n = notification_service.create_notification(
            db,
            thread_subject="Test thread",
            body="First message",
        )
        response = client.get(f"{BASE_URL}/{n.thread_id}")
        assert response.status_code == 200
        messages = response.json()
        assert len(messages) >= 1
        assert messages[0]["body"] == "First message"

    def test_get_thread_not_found(self, client):
        response = client.get(f"{BASE_URL}/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestReplyToThread:
    def test_reply(self, client, db):
        from app.services import notification_service

        n = notification_service.create_notification(
            db, thread_subject="Test", body="Original"
        )
        response = client.post(
            f"{BASE_URL}/{n.thread_id}/reply",
            json={"body": "Reply message"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["body"] == "Reply message"
        assert data["thread_id"] == n.thread_id
        assert data["sender_type"] == "admin"

    def test_reply_not_found(self, client):
        response = client.post(
            f"{BASE_URL}/00000000-0000-0000-0000-000000000000/reply",
            json={"body": "Reply"},
        )
        assert response.status_code == 404


class TestMarkRead:
    def test_mark_thread_read(self, client, db):
        from app.services import notification_service

        n = notification_service.create_notification(
            db, thread_subject="Test", body="Unread"
        )
        assert n.read_at is None

        response = client.post(f"{BASE_URL}/{n.thread_id}/read")
        assert response.status_code == 200
        assert response.json()["marked_read"] >= 1

    def test_mark_single_read(self, client, db):
        from app.services import notification_service

        n = notification_service.create_notification(
            db, thread_subject="Test", body="Unread"
        )
        response = client.post(f"{BASE_URL}/{n.id}/mark-read")
        assert response.status_code == 200
        assert response.json()["read_at"] is not None
