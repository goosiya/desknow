"""admin 라우터 통합 테스트 (Story 8.1, AC2·AC4 — RBAC + 페이지네이션).

**DB 불필요** — ``app.dependency_overrides[get_session]``로 세션을 Fake로 교체하고,
``TestClient(app)``(모듈 레벨, lifespan 미실행 — 1.4 불변식)로 엔드포인트를 검증한다. 실 admin/
booker/provider access 토큰으로 RBAC(admin 200·비-admin 403·무토큰 401)를 실증한다.
"""
from __future__ import annotations

import inspect
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.admin.schemas import (
    AdminIngestDocument,
    AdminIngestDocumentList,
    AdminIngestFailure,
    AdminIngestReport,
)
from app.core.db import get_session
from app.core.security import create_access_token
from app.main import app
from app.reservations.models import ReservationStatus
from tests.admin.test_service import (
    FakeAdminSession,
    FakeDeactivateSession,
    FakeForceCancelSession,
    FakeReservationListSession,
    _reservation,
    _room,
    _user,
)

client = TestClient(app)


@contextmanager
def _override_session(session: Any) -> Iterator[None]:
    def _fake_get_session() -> Iterator[Any]:
        yield session

    app.dependency_overrides[get_session] = _fake_get_session
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def _admin_token() -> str:
    return create_access_token(uuid.uuid4(), "admin")


def _booker_token() -> str:
    return create_access_token(uuid.uuid4(), "booker")


def _provider_token() -> str:
    return create_access_token(uuid.uuid4(), "provider")


def _sample_session() -> FakeAdminSession:
    return FakeAdminSession(
        [
            _user(role="booker", created_at=datetime(2026, 6, 18, tzinfo=UTC)),
            _user(role="provider", created_at=datetime(2026, 6, 17, tzinfo=UTC)),
        ]
    )


# ── GET /api/v1/admin/accounts (RBAC — AC2·AC4) ───────────────────────────────
def test_list_accounts_admin_returns_200(auth_env: None) -> None:
    """admin 토큰 → 200 + {items, total, page, page_size}. items에 password_hash 부재."""
    with _override_session(_sample_session()):
        resp = client.get(
            "/api/v1/admin/accounts",
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["total"] == 2
    assert body["page"] == 1 and body["page_size"] == 20
    first = body["items"][0]
    assert set(first) == {"id", "email", "role", "is_active", "created_at"}
    assert "password_hash" not in first
    assert first["created_at"].endswith("Z")  # ...Z 와이어 규약


def test_list_accounts_booker_returns_403(auth_env: None) -> None:
    """booker 토큰 → 403 FORBIDDEN_ROLE(admin만 — 백엔드 최종 강제, AC2)."""
    with _override_session(_sample_session()):
        resp = client.get(
            "/api/v1/admin/accounts",
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_list_accounts_provider_returns_403(auth_env: None) -> None:
    """provider 토큰 → 403 FORBIDDEN_ROLE(admin만 — AC2)."""
    with _override_session(_sample_session()):
        resp = client.get(
            "/api/v1/admin/accounts",
            headers={"Authorization": f"Bearer {_provider_token()}"},
        )

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_list_accounts_no_token_returns_401(auth_env: None) -> None:
    """토큰 없음 → 401 UNAUTHENTICATED."""
    with _override_session(_sample_session()):
        resp = client.get("/api/v1/admin/accounts")

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


# ── 페이지네이션 파라미터 검증(Query → 1.5 핸들러, AC4) ────────────────────────
def test_list_accounts_page_size_over_limit_returns_422(auth_env: None) -> None:
    """page_size > 100 → 422 VALIDATION_ERROR(상한 강제 — 무제한 결과셋 차단)."""
    with _override_session(_sample_session()):
        resp = client.get(
            "/api/v1/admin/accounts?page_size=101",
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_list_accounts_page_below_one_returns_422(auth_env: None) -> None:
    """page < 1 → 422 VALIDATION_ERROR(ge=1)."""
    with _override_session(_sample_session()):
        resp = client.get(
            "/api/v1/admin/accounts?page=0",
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


# ── POST /api/v1/admin/accounts/{id}/deactivate (RBAC + 멱등 + 가드, Story 8.2) ──
def test_deactivate_admin_returns_200(auth_env: None) -> None:
    """admin 토큰 → 200 + 반환 item is_active=False, password_hash 부재."""
    booker = _user(role="booker", created_at=datetime(2026, 6, 18, tzinfo=UTC))
    with _override_session(FakeDeactivateSession([booker])):
        resp = client.post(
            f"/api/v1/admin/accounts/{booker.id}/deactivate",
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_active"] is False and body["id"] == str(booker.id)
    assert "password_hash" not in body


def test_deactivate_booker_returns_403(auth_env: None) -> None:
    """booker 토큰 → 403 FORBIDDEN_ROLE(admin만 — 백엔드 최종 강제)."""
    booker = _user(role="booker", created_at=datetime(2026, 6, 18, tzinfo=UTC))
    with _override_session(FakeDeactivateSession([booker])):
        resp = client.post(
            f"/api/v1/admin/accounts/{booker.id}/deactivate",
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_deactivate_provider_returns_403(auth_env: None) -> None:
    """provider 토큰 → 403 FORBIDDEN_ROLE(admin만)."""
    booker = _user(role="booker", created_at=datetime(2026, 6, 18, tzinfo=UTC))
    with _override_session(FakeDeactivateSession([booker])):
        resp = client.post(
            f"/api/v1/admin/accounts/{booker.id}/deactivate",
            headers={"Authorization": f"Bearer {_provider_token()}"},
        )

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_deactivate_no_token_returns_401(auth_env: None) -> None:
    """토큰 없음 → 401 UNAUTHENTICATED."""
    booker = _user(role="booker", created_at=datetime(2026, 6, 18, tzinfo=UTC))
    with _override_session(FakeDeactivateSession([booker])):
        resp = client.post(f"/api/v1/admin/accounts/{booker.id}/deactivate")

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_deactivate_admin_target_returns_404(auth_env: None) -> None:
    """admin 대상 → 404 ACCOUNT_NOT_FOUND(존재 누설·자기/타admin 비활성 금지)."""
    admin = _user(role="admin", created_at=datetime(2026, 6, 18, tzinfo=UTC))
    with _override_session(FakeDeactivateSession([admin])):
        resp = client.post(
            f"/api/v1/admin/accounts/{admin.id}/deactivate",
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ACCOUNT_NOT_FOUND"


def test_deactivate_missing_target_returns_404(auth_env: None) -> None:
    """미존재 account_id → 404 ACCOUNT_NOT_FOUND."""
    with _override_session(FakeDeactivateSession([])):
        resp = client.post(
            f"/api/v1/admin/accounts/{uuid.uuid4()}/deactivate",
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ACCOUNT_NOT_FOUND"


# ── GET /api/v1/admin/reservations (RBAC + 페이지네이션, Story 8.3 AC4·AC5) ──────
_RESERVATION_ITEM_KEYS = {
    "id",
    "room_id",
    "room_name",
    "booker_id",
    "booker_email",
    "status",
    "slot_starts",
    "created_at",
}


def _reservations_list_session() -> FakeReservationListSession:
    booker = _user(role="booker", created_at=datetime(2026, 6, 17, tzinfo=UTC))
    room = _room(provider_id=uuid.uuid4())
    reservation = _reservation(booker_id=booker.id, room_id=room.id)
    return FakeReservationListSession([reservation], [room], [booker])


def test_list_reservations_admin_returns_200(auth_env: None) -> None:
    """admin 토큰 → 200 + {items, total, page, page_size}. 항목은 실 이메일·룸 이름 포함."""
    with _override_session(_reservations_list_session()):
        resp = client.get(
            "/api/v1/admin/reservations",
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["total"] == 1
    first = body["items"][0]
    assert set(first) == _RESERVATION_ITEM_KEYS
    assert first["status"] == "confirmed"  # confirmed-only
    assert first["created_at"].endswith("Z")  # ...Z 와이어 규약
    assert "password_hash" not in first


def test_list_reservations_booker_returns_403(auth_env: None) -> None:
    """booker 토큰 → 403 FORBIDDEN_ROLE(admin만)."""
    with _override_session(_reservations_list_session()):
        resp = client.get(
            "/api/v1/admin/reservations",
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_list_reservations_provider_returns_403(auth_env: None) -> None:
    """provider 토큰 → 403 FORBIDDEN_ROLE(admin만)."""
    with _override_session(_reservations_list_session()):
        resp = client.get(
            "/api/v1/admin/reservations",
            headers={"Authorization": f"Bearer {_provider_token()}"},
        )

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_list_reservations_no_token_returns_401(auth_env: None) -> None:
    """토큰 없음 → 401 UNAUTHENTICATED."""
    with _override_session(_reservations_list_session()):
        resp = client.get("/api/v1/admin/reservations")

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_list_reservations_page_size_over_limit_returns_422(auth_env: None) -> None:
    """page_size > 100 → 422 VALIDATION_ERROR(상한 강제 — 무제한 결과셋 차단)."""
    with _override_session(_reservations_list_session()):
        resp = client.get(
            "/api/v1/admin/reservations?page_size=101",
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


# ── POST /api/v1/admin/reservations/{id}/cancel (RBAC + 멱등 + 가드, Story 8.3) ──
def _cancel_url(reservation_id: object) -> str:
    return f"/api/v1/admin/reservations/{reservation_id}/cancel"


def _confirmed_cancel_session() -> tuple[FakeForceCancelSession, object]:
    booker = _user(role="booker", created_at=datetime(2026, 6, 17, tzinfo=UTC))
    room = _room(provider_id=uuid.uuid4())
    reservation = _reservation(booker_id=booker.id, room_id=room.id)
    session = FakeForceCancelSession(reservation=reservation, room=room, booker=booker)
    return session, reservation


def test_cancel_reservation_admin_returns_200(auth_env: None) -> None:
    """admin 토큰 → 200 + AdminReservationItem(status=cancelled)·통지 생성·실 이메일."""
    session, reservation = _confirmed_cancel_session()
    with _override_session(session):
        resp = client.post(
            _cancel_url(reservation.id),
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == _RESERVATION_ITEM_KEYS
    assert body["status"] == "cancelled"
    assert body["id"] == str(reservation.id)
    assert session.committed == 1
    assert len(session.notifications) == 1  # status_change/cancelled 통지 생성
    assert "password_hash" not in body


def test_cancel_reservation_already_terminal_idempotent_200(auth_env: None) -> None:
    """이미 종료(cancelled) 예약 임의취소 → 200·현재 상태·통지 0(멱등 — 별도 409 없음)."""
    booker = _user(role="booker", created_at=datetime(2026, 6, 17, tzinfo=UTC))
    room = _room(provider_id=uuid.uuid4())
    reservation = _reservation(
        booker_id=booker.id, room_id=room.id, status=ReservationStatus.CANCELLED
    )
    session = FakeForceCancelSession(reservation=reservation, room=room, booker=booker)
    with _override_session(session):
        resp = client.post(
            _cancel_url(reservation.id),
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"
    assert session.committed == 0  # 멱등 no-op
    assert session.notifications == []  # 통지 0


def test_cancel_reservation_booker_returns_403(auth_env: None) -> None:
    """booker 토큰 → 403 FORBIDDEN_ROLE(admin만)."""
    session, reservation = _confirmed_cancel_session()
    with _override_session(session):
        resp = client.post(
            _cancel_url(reservation.id),
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"
    assert session.committed == 0  # 거절은 가드에서 차단 — 전이 0


def test_cancel_reservation_provider_returns_403(auth_env: None) -> None:
    """provider 토큰 → 403 FORBIDDEN_ROLE(admin만)."""
    session, reservation = _confirmed_cancel_session()
    with _override_session(session):
        resp = client.post(
            _cancel_url(reservation.id),
            headers={"Authorization": f"Bearer {_provider_token()}"},
        )

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_cancel_reservation_no_token_returns_401(auth_env: None) -> None:
    """토큰 없음 → 401 UNAUTHENTICATED."""
    session, reservation = _confirmed_cancel_session()
    with _override_session(session):
        resp = client.post(_cancel_url(reservation.id))

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_cancel_reservation_missing_returns_404(auth_env: None) -> None:
    """미존재 reservation_id → 404 RESERVATION_NOT_FOUND(누설 방지)."""
    session = FakeForceCancelSession(reservation=None)
    with _override_session(session):
        resp = client.post(
            _cancel_url(uuid.uuid4()),
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "RESERVATION_NOT_FOUND"


# ── POST /api/v1/admin/ingest (RBAC + 계약, Story 8.4 AC1·5) ────────────────────
_INGEST_REPORT_KEYS = {"succeeded", "skipped", "failed", "removed", "total"}


def _fake_ingest_report() -> AdminIngestReport:
    return AdminIngestReport(
        succeeded=["faq.md"],
        skipped=["guide.md"],
        failed=[AdminIngestFailure(path="broken.md", reason="DocumentLoadError: 빈 문서")],
        removed=["old.md"],
        total=3,
    )


def _patch_ingest(monkeypatch: pytest.MonkeyPatch) -> None:
    """service.trigger_ingest를 페이크 리포트로 치환(실 임베딩/DB 없이 계약만 검증)."""
    from app.admin import service as admin_service

    monkeypatch.setattr(
        admin_service, "trigger_ingest", lambda session: _fake_ingest_report()
    )


def test_trigger_ingest_admin_returns_200(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """admin 토큰 → 200 + AdminIngestReport(성공/스킵/실패/정리/총수). failed는 path+reason 객체."""
    _patch_ingest(monkeypatch)
    with _override_session(object()):
        resp = client.post(
            "/api/v1/admin/ingest",
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == _INGEST_REPORT_KEYS
    assert body["total"] == 3
    assert body["succeeded"] == ["faq.md"]
    assert body["removed"] == ["old.md"]  # stale 청크 정리 보고
    assert body["failed"][0] == {"path": "broken.md", "reason": "DocumentLoadError: 빈 문서"}


def test_trigger_ingest_booker_returns_403(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """booker 토큰 → 403 FORBIDDEN_ROLE(admin만 — 백엔드 최종 강제, AC5)."""
    _patch_ingest(monkeypatch)
    with _override_session(object()):
        resp = client.post(
            "/api/v1/admin/ingest",
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_trigger_ingest_provider_returns_403(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """provider 토큰 → 403 FORBIDDEN_ROLE(admin만)."""
    _patch_ingest(monkeypatch)
    with _override_session(object()):
        resp = client.post(
            "/api/v1/admin/ingest",
            headers={"Authorization": f"Bearer {_provider_token()}"},
        )

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_trigger_ingest_no_token_returns_401(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """토큰 없음 → 401 UNAUTHENTICATED."""
    _patch_ingest(monkeypatch)
    with _override_session(object()):
        resp = client.post("/api/v1/admin/ingest")

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_trigger_ingest_route_is_sync_def() -> None:
    """★라우터 핸들러는 동기 def여야 한다 — async def면 블로킹 인제스트가 이벤트 루프를 막음."""
    from app.admin.router import trigger_ingest as ingest_route

    assert not inspect.iscoroutinefunction(ingest_route)


# ── GET /api/v1/admin/ingest/documents (RBAC + 계약, 문서 목록) ──────────────────
def _fake_document_list() -> AdminIngestDocumentList:
    return AdminIngestDocumentList(
        documents=[
            AdminIngestDocument(source_path="faq.md", chunk_count=3, status="ingested"),
            AdminIngestDocument(source_path="guide.md", chunk_count=2, status="stale"),
            AdminIngestDocument(source_path="new.md", chunk_count=0, status="pending"),
            AdminIngestDocument(source_path="gone.md", chunk_count=1, status="orphan"),
        ],
        total=4,
    )


def _patch_list_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.admin import service as admin_service

    monkeypatch.setattr(
        admin_service, "list_ingest_documents", lambda session: _fake_document_list()
    )


def test_list_ingest_documents_admin_returns_200(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """admin 토큰 → 200 + 문서 목록(상태 배지). 4상태가 그대로 직렬화된다."""
    _patch_list_documents(monkeypatch)
    with _override_session(object()):
        resp = client.get(
            "/api/v1/admin/ingest/documents",
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 4
    statuses = {d["source_path"]: d["status"] for d in body["documents"]}
    assert statuses == {
        "faq.md": "ingested",
        "guide.md": "stale",
        "new.md": "pending",
        "gone.md": "orphan",
    }
    assert body["documents"][0]["chunk_count"] == 3


def test_list_ingest_documents_booker_returns_403(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """booker 토큰 → 403 FORBIDDEN_ROLE(admin만 — 읽기 전용이라도 운영 표면)."""
    _patch_list_documents(monkeypatch)
    with _override_session(object()):
        resp = client.get(
            "/api/v1/admin/ingest/documents",
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_list_ingest_documents_no_token_returns_401(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """토큰 없음 → 401 UNAUTHENTICATED."""
    _patch_list_documents(monkeypatch)
    with _override_session(object()):
        resp = client.get("/api/v1/admin/ingest/documents")

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_list_ingest_documents_route_is_sync_def() -> None:
    """읽기 핸들러도 동기 def — 블로킹 DB 집계/디스크 스캔이 이벤트 루프를 안 막게 스레드풀 실행."""
    from app.admin.router import list_ingest_documents as list_route

    assert not inspect.iscoroutinefunction(list_route)
