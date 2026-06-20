"""notifications 서비스 테스트 (Story 5.1 — AC2 멱등 생성·미확인 조회·소유권 dismiss).

DB 불필요 — ``FakeNotificationSession``으로 멱등 create(중복=기존 반환·무관 제약 re-raise)·
list_pending(dismissed 제외·최신순)·dismiss(소유권 404·멱등 no-op)를 실증한다(favorites
``test_service.py`` FakeSession 충실도 선례 — exec 엔티티 라우팅·commit IntegrityError 주입).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import DomainError, ErrorCode
from app.notifications import service
from app.notifications.models import Notification, NotificationType


# ── psycopg orig 모방(P2 violated_constraint 실증 — favorites 선례) ──────────────────
class _FakeDiag:
    def __init__(self, constraint_name: str | None) -> None:
        self.constraint_name = constraint_name


class _FakeOrig(Exception):
    def __init__(self, constraint_name: str | None) -> None:
        super().__init__("integrity violation")
        self.diag = _FakeDiag(constraint_name)


class _Result:
    """exec 결과 — ``.first()``(첫 행/None)·``.all()``(리스트) 양쪽 지원."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)


class FakeNotificationSession:
    """notifications 서비스용 Fake 세션(create/list_pending/dismiss — favorites 충실도 계승).

    - ``exec(select(Notification))`` → ``notifications``(``.all()``/``.first()``). where/order_by는
      서비스 결과 단언이 아니라 호출 자체를 검증하므로 Fake는 보유 리스트를 그대로 돌려준다
      (멱등 재조회는 단일 후보를 넣어 검증, list_pending 필터링은 별도 단언).
    - ``get(Notification, pk)`` → PK 일치 행(실 ``Session.get`` 모사) 또는 ``None``.
    - ``commit``은 ``raise_on_commit`` 시 제약명 있는 ``IntegrityError``를 던진다(P2 분기 실증).
    """

    def __init__(
        self,
        *,
        notifications: list[Notification] | None = None,
        raise_on_commit: bool = False,
        commit_violation: str | None = None,
    ) -> None:
        self.notifications = notifications or []
        self.raise_on_commit = raise_on_commit
        self.commit_violation = commit_violation
        self.added: list[Any] = []
        self.committed = False
        self.rolled_back = False

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> _Result:
        return _Result(self.notifications)

    def get(self, model: Any, pk: Any) -> Any:
        for notification in self.notifications:
            if getattr(notification, "id", None) == pk:
                return notification
        return None

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        if self.raise_on_commit:
            raise IntegrityError("stmt", {}, _FakeOrig(self.commit_violation))
        self.committed = True

    def refresh(self, obj: Any) -> None:
        pass

    def rollback(self) -> None:
        self.rolled_back = True


def _notification(
    user_id: uuid.UUID,
    *,
    type: NotificationType = NotificationType.STATUS_CHANGE,
    reason: str | None = "cancelled",
    dismissed: bool = False,
) -> Notification:
    return Notification(
        user_id=user_id,
        reservation_id=uuid.uuid4(),
        type=str(type),
        reason=reason,
        dismissed_at=datetime(2026, 6, 17, 0, 0, tzinfo=UTC) if dismissed else None,
    )


# ── create_notification (AC2 — 멱등·선별 변환) ────────────────────────────────────
def test_create_notification_inserts_and_commits() -> None:
    """신규 → Notification add+commit 후 반환(type/reason 기록)."""
    user_id = uuid.uuid4()
    reservation_id = uuid.uuid4()
    session = FakeNotificationSession()

    result = service.create_notification(
        session,
        user_id,
        reservation_id,
        NotificationType.STATUS_CHANGE,
        reason="rejected",
    )

    assert isinstance(result, Notification)
    assert result.user_id == user_id
    assert result.reservation_id == reservation_id
    assert result.type == "status_change"
    assert result.reason == "rejected"
    assert session.committed is True
    assert result in session.added


def test_create_notification_reminder_has_no_reason() -> None:
    """reminder 종류는 reason 없이 생성(reason 기본 None)."""
    session = FakeNotificationSession()
    result = service.create_notification(
        session, uuid.uuid4(), uuid.uuid4(), NotificationType.RESERVATION_REMINDER
    )
    assert result.type == "reservation_reminder"
    assert result.reason is None


def test_create_notification_duplicate_is_idempotent() -> None:
    """uq 위반(같은 사용자·예약·종류 이미 존재) → rollback 후 기존 행 반환(멱등)."""
    user_id = uuid.uuid4()
    existing = _notification(user_id)
    session = FakeNotificationSession(
        notifications=[existing],
        raise_on_commit=True,
        commit_violation="uq_notifications_user_reservation_type",
    )

    result = service.create_notification(
        session,
        user_id,
        existing.reservation_id,
        NotificationType.STATUS_CHANGE,
        reason="cancelled",
    )

    assert result is existing  # 기존 행 그대로 반환
    assert session.rolled_back is True


def test_create_notification_unknown_constraint_reraises() -> None:
    """무관한 제약 위반은 오변환 없이 re-raise(과대캐치 금지 — P2)."""
    session = FakeNotificationSession(
        raise_on_commit=True,
        commit_violation="some_other_constraint",
    )
    with pytest.raises(IntegrityError):
        service.create_notification(
            session, uuid.uuid4(), uuid.uuid4(), NotificationType.STATUS_CHANGE
        )
    assert session.rolled_back is True


# ── list_pending (AC2 — 미확인만·읽기전용) ─────────────────────────────────────────
def test_list_pending_returns_notifications() -> None:
    """미확인 통지를 리스트로 반환한다(읽기 전용 — exec 결과 그대로)."""
    user_id = uuid.uuid4()
    items = [_notification(user_id), _notification(user_id)]
    session = FakeNotificationSession(notifications=items)

    result = service.list_pending(session, user_id)

    assert result == items


def test_list_pending_empty_returns_empty_list() -> None:
    """미확인 통지 없음 → 빈 리스트(정상)."""
    assert service.list_pending(FakeNotificationSession(), uuid.uuid4()) == []


# ── dismiss_notification (AC2·AC5 — 소유권 404·멱등) ───────────────────────────────
def test_dismiss_notification_sets_dismissed_at_and_commits() -> None:
    """본인 미확인 통지 → dismissed_at 설정 + commit(소멸 영속)."""
    user_id = uuid.uuid4()
    notification = _notification(user_id)
    session = FakeNotificationSession(notifications=[notification])

    service.dismiss_notification(session, user_id, notification.id)

    assert notification.dismissed_at is not None
    assert session.committed is True


def test_dismiss_notification_missing_raises_404() -> None:
    """미존재 통지 dismiss → 404 NOTIFICATION_NOT_FOUND."""
    session = FakeNotificationSession(notifications=[])
    with pytest.raises(DomainError) as exc:
        service.dismiss_notification(session, uuid.uuid4(), uuid.uuid4())
    assert exc.value.code is ErrorCode.NOTIFICATION_NOT_FOUND
    assert exc.value.status_code == 404


def test_dismiss_notification_other_user_raises_404_no_leak() -> None:
    """타 사용자 통지 dismiss → 404(403 아님 — 존재 누설 금지, 소유권 가드)."""
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    notification = _notification(owner_id)
    session = FakeNotificationSession(notifications=[notification])

    with pytest.raises(DomainError) as exc:
        service.dismiss_notification(session, other_id, notification.id)
    assert exc.value.code is ErrorCode.NOTIFICATION_NOT_FOUND
    assert session.committed is False  # 소유권 실패 → 쓰기 없음


def test_dismiss_notification_already_dismissed_is_idempotent() -> None:
    """이미 소멸된 통지 dismiss → 멱등 no-op(에러·재쓰기 없음)."""
    user_id = uuid.uuid4()
    notification = _notification(user_id, dismissed=True)
    original = notification.dismissed_at
    session = FakeNotificationSession(notifications=[notification])

    service.dismiss_notification(session, user_id, notification.id)

    assert notification.dismissed_at == original  # 변경 없음
    assert session.committed is False  # 재쓰기 없음(멱등 no-op)


# ── dismissed_reminder_reservation_ids (Story 5.2 — AC1 도출 제외용·읽기전용) ────────
class _IdsSession:
    """``select(Notification.reservation_id)`` 스칼라 결과(reservation_id 목록)를 돌려주는 Fake.

    SQL WHERE(type='reservation_reminder'·dismissed_at NOT NULL)는 DB가 적용하므로 단위 테스트는
    set 변환·읽기전용만 검증한다(실 필터는 router 통합 테스트의 '억제 후 미도출'이 실증)."""

    def __init__(self, ids: list[uuid.UUID]) -> None:
        self._ids = ids
        self.committed = False

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> _Result:
        return _Result(self._ids)

    def commit(self) -> None:
        self.committed = True


def test_dismissed_reminder_reservation_ids_returns_set() -> None:
    """억제건 reservation_id를 집합으로 반환한다(중복 제거·읽기 전용)."""
    ids = [uuid.uuid4(), uuid.uuid4()]
    session = _IdsSession(ids)

    result = service.dismissed_reminder_reservation_ids(session, uuid.uuid4())

    assert result == set(ids)
    assert session.committed is False  # 읽기 전용(commit 0)


def test_dismissed_reminder_reservation_ids_empty() -> None:
    """억제건 없음 → 빈 집합."""
    assert service.dismissed_reminder_reservation_ids(_IdsSession([]), uuid.uuid4()) == set()


# ── suppress_reminder (Story 5.2 — AC2 born-dismissed 억제행·멱등) ────────────────────
class _SuppressSession:
    """create_notification + dismiss_notification 재사용 경로를 실증하는 Fake(uq 멱등 모사).

    - ``add`` → 다음 ``commit``의 대상으로 보류(pending). ``commit``이 신규 INSERT면 uq 위반을
      모사(같은 user·reservation·type가 store에 있으면 ``IntegrityError``)하고, 기존 행 업데이트
      (dismiss의 add — 동일 객체)면 그냥 commit한다(identity 기준 구분).
    - ``get(Notification, pk)``·``exec``(멱등 재조회 ``.first()``)는 store를 본다.
    """

    def __init__(self, existing: list[Notification] | None = None) -> None:
        self.store: list[Notification] = list(existing or [])
        self.pending: Notification | None = None
        self.commits = 0

    def add(self, obj: Any) -> None:
        self.pending = obj

    def commit(self) -> None:
        obj = self.pending
        self.pending = None
        self.commits += 1
        if obj is None:
            return
        if any(row is obj for row in self.store):
            return  # 기존 행 업데이트(dismiss) — INSERT 아님
        dup = any(
            row.user_id == obj.user_id
            and row.reservation_id == obj.reservation_id
            and row.type == obj.type
            for row in self.store
        )
        if dup:  # uq 위반 모사(같은 user·reservation·type 이미 존재)
            raise IntegrityError(
                "stmt", {}, _FakeOrig("uq_notifications_user_reservation_type")
            )
        self.store.append(obj)

    def rollback(self) -> None:
        self.pending = None

    def refresh(self, obj: Any) -> None:
        pass

    def get(self, model: Any, pk: Any) -> Any:
        for row in self.store:
            if getattr(row, "id", None) == pk:
                return row
        return None

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> _Result:
        return _Result(self.store)


def test_suppress_reminder_creates_born_dismissed_row() -> None:
    """신규 억제 → reservation_reminder 억제행 1건 born-dismissed(dismissed_at 설정)."""
    user_id = uuid.uuid4()
    reservation_id = uuid.uuid4()
    session = _SuppressSession()

    service.suppress_reminder(session, user_id, reservation_id)

    assert len(session.store) == 1
    row = session.store[0]
    assert row.type == "reservation_reminder"
    assert row.user_id == user_id
    assert row.reservation_id == reservation_id
    assert row.dismissed_at is not None  # born-dismissed


def test_suppress_reminder_idempotent_on_repeat() -> None:
    """재호출(같은 예약) → 추가 행 0·기존 dismissed_at 유지(create/dismiss 멱등 재사용)."""
    user_id = uuid.uuid4()
    reservation_id = uuid.uuid4()
    original_at = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    existing = Notification(
        user_id=user_id,
        reservation_id=reservation_id,
        type=str(NotificationType.RESERVATION_REMINDER),
        dismissed_at=original_at,
    )
    session = _SuppressSession(existing=[existing])

    service.suppress_reminder(session, user_id, reservation_id)

    assert len(session.store) == 1  # 추가 행 0(uq 멱등)
    assert session.store[0] is existing
    assert existing.dismissed_at == original_at  # 유지(이미 소멸 — dismiss no-op)
