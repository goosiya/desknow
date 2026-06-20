"""notifications 라우터: 통지 조회(도래 리마인드 도출 + status_change 머지) + 소멸 (Story 5.1·5.2).

``main.py``가 ``api_router``(``/api/v1``) 아래에 포함하므로 최종 경로는:

- ``GET /api/v1/notifications`` — 본인 통지 목록. **두 종류를 머지**한다(5.2): ① 도래 리마인드
  (24h 이내 확정 예약에서 **행 없이 도출** — ``reminders.due_reminder_reservations``)
  ② status_change pending(``service.list_pending``). GET은 **읽기전용**(DB 쓰기 0 — 억제건 조회만).
- ``POST /api/v1/notifications/reminders/{reservation_id}/dismiss`` — 도래 리마인드 '다시 보지
  않기'(204·멱등, 5.2). ``reservation_id`` 키 억제행을 born-dismissed 생성.
- ``POST /api/v1/notifications/{notification_id}/dismiss`` — status_change '확인'(204·멱등, 5.1).

**규약:**

- **인증 = ``get_current_principal``**(로그인만·역할 무관, 5.1). 미인증=401. ``principal``로 식별.
- **상태코드:** list=200, dismiss=204(본문 없음·멱등). 비소유/미존재 dismiss는 404
  ``NOTIFICATION_NOT_FOUND``(소유권 누설 금지).
- **두 종류 비대칭(5.2):** 리마인드 항목 = ``id=None``·``slot_start=earliest``·``reason=None``·
  ``created_at=None``. status_change 항목 = ``id=행id``·``slot_start=None``·``created_at=행값``.
  **결정적 순서**: 리마인드(``slot_start`` asc·임박순) 먼저, 그다음 status_change(``list_pending``
  created_at desc). ``now``는 ``now_utc()``로 1회 캡처해 도출 전체에 일관 주입한다.
- **``room_name`` 합성은 라우터에서**(``session.get(Room)``): notifications.service가 rooms/
  reservations를 import하면 도메인 경계(L354·순환)를 깨므로, 룸 메타 합성은 조합 계층인 라우터가
  한다(4.8·5.1 선례). 리마인드는 ``Reservation``을 이미 들고 있어(도출 결과) ``room_id`` 1-홉,
  status_change는 ``notification → reservation → room`` 2-홉. 룸/예약 누락은 ``None`` 폴백.
- **리마인드 dismiss 소유권 가드 먼저(반복함정 #5·FK 500 회피):** ``session.get(Reservation, id)``
  미존재/비소유면 404 ``NOTIFICATION_NOT_FOUND``. 이 가드 없이 ``suppress_reminder``를 바로 부르면
  미존재 ``reservation_id``가 FK(``fk_notifications_reservation_id_reservations``)를 위반해 raw
  IntegrityError 500이 될 수 있다(uq 아니라 멱등 변환에 안 걸림).
- **operationId(1.9):** ``{tag}_{name}`` = ``notifications_list_notifications``·
  ``notifications_dismiss_reminder``·``notifications_dismiss_notification`` → SDK
  ``notificationsListNotifications``·``notificationsDismissReminder``·``notificationsDismissNotification``.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlmodel import Session

from app.core.db import get_session
from app.core.errors import DomainError, ErrorCode, ErrorResponse
from app.core.security import AuthPrincipal, get_current_principal
from app.core.time import now_utc
from app.notifications import reminders, service
from app.notifications.models import NotificationType
from app.notifications.schemas import NotificationItem
from app.reservations.models import Reservation
from app.rooms.models import Room

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    response_model=list[NotificationItem],
    responses={401: {"model": ErrorResponse}},
)
def list_notifications(
    principal: AuthPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> list[NotificationItem]:
    """현재 사용자의 통지를 반환한다 → 200(로그인 필요·읽기전용, AC1·AC3·AC4).

    **두 종류를 머지**한다: ① 도래 리마인드(``reminders.due_reminder_reservations`` — 24h 이내
    확정 예약을 **행 없이 도출**, 억제건 제외) ② status_change pending(``service.list_pending``).
    각 항목의 ``room_name``은 라우터가 PK 조회로 합성한다(service rooms import 금지·순환 회피).
    리마인드(``slot_start`` asc·임박순) 먼저, status_change(created_at desc) 다음의 **결정적 순서**.
    ``now``는 1회 캡처해 도출 전체에 일관 주입한다. DB 쓰기 0(억제건 조회만). 미인증은 401.
    """
    now = now_utc()  # 도출 판정 일관성 — 1회 캡처

    # ① 도래 리마인드 도출(행 없음) — 이미 Reservation을 들고 있어 room_id 1-홉 합성.
    reminder_items: list[NotificationItem] = []
    for reservation in reminders.due_reminder_reservations(session, principal.user_id, now):
        room = session.get(Room, reservation.room_id)
        # earliest = 가장 이른 슬롯(due 필터가 통과시킨 예약이라 항상 존재하나, 안전 파싱 헬퍼로
        # 통일 — 중복 파싱 제거·손상 None 폴백 동일 가드 경유, DRY·L7). isoformat ...Z aware(3.12).
        earliest = reminders.earliest_slot_start(reservation)
        reminder_items.append(
            NotificationItem(
                id=None,  # 도출 — 행 없음(FE는 reservation_id 키로 dismiss)
                type=str(NotificationType.RESERVATION_REMINDER),
                reservation_id=reservation.id,
                reason=None,
                room_name=room.name if room is not None else None,
                slot_start=earliest,
                created_at=None,
            )
        )
    # slot_start asc(임박순) — None은 뒤로(방어; 정상 리마인드는 slot_start 보유).
    reminder_items.sort(key=lambda item: (item.slot_start is None, item.slot_start))

    # ② status_change pending(억제행은 born-dismissed라 list_pending 미반환 → 머지 중복 0).
    status_items: list[NotificationItem] = []
    for notification in service.list_pending(session, principal.user_id):
        linked = session.get(Reservation, notification.reservation_id)
        room = session.get(Room, linked.room_id) if linked is not None else None
        # 원래 점유 슬롯 시각 표면화(본 스토리 핵심): 이미 들고 있는 ``linked``(room_name 합성용
        # 조회)에서 slot_starts[0]을 합성 → **추가 쿼리 0**(N+1 미증가). 4.8 immutable 스냅샷이라
        # 취소/거절로 reservation_slots 행이 DELETE돼도 보존. linked/slot_starts 누락·손상은 헬퍼가
        # None 폴백(AC4 L7 — GET 500 금지). 정렬 키는 created_at 유지(slot_start로 재정렬 금지).
        status_items.append(
            NotificationItem(
                id=notification.id,
                type=notification.type,
                reservation_id=notification.reservation_id,
                reason=notification.reason,
                room_name=room.name if room is not None else None,
                slot_start=(
                    reminders.earliest_slot_start(linked) if linked is not None else None
                ),
                created_at=notification.created_at,
            )
        )

    # 결정적 순서: 리마인드(임박순) → status_change(최신순).
    return reminder_items + status_items


@router.post(
    "/reminders/{reservation_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def dismiss_reminder(
    reservation_id: uuid.UUID,
    principal: AuthPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> Response:
    """도래 리마인드를 '다시 보지 않기'로 영속 억제한다 → 204(로그인 필요·멱등, AC2).

    **소유권 가드 먼저(반복함정 #5·FK 500 회피):** ``session.get(Reservation, id)`` → 미존재이거나
    ``booker_id``가 요청자가 아니면 404 ``NOTIFICATION_NOT_FOUND``(타인/미존재 예약 누설 금지 —
    403 아님). 이 가드 없이 ``suppress_reminder``를 바로 부르면 미존재 ``reservation_id``가 FK를
    위반해 raw 500이 된다. 통과 시 ``service.suppress_reminder``(born-dismissed 억제행·멱등)에
    위임한다. 경로 세그먼트 3개라 ``/{notification_id}/dismiss``(2개)와 충돌 없음. 미인증=401.
    """
    reservation = session.get(Reservation, reservation_id)
    if reservation is None or reservation.booker_id != principal.user_id:
        # 미존재·비소유를 동일 404로 합쳐 타인 예약 존재를 누설하지 않는다(소유권 누설 금지).
        raise DomainError(ErrorCode.NOTIFICATION_NOT_FOUND, "알림을 찾을 수 없습니다.")
    service.suppress_reminder(session, principal.user_id, reservation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{notification_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def dismiss_notification(
    notification_id: uuid.UUID,
    principal: AuthPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> Response:
    """status_change 통지 한 건을 소멸 처리한다 → 204(로그인 필요·멱등, 5.1 AC5).

    '확인'(5.3)이 이 generic 엔드포인트를 소비한다. 소유권 검증(타인/미존재=404
    ``NOTIFICATION_NOT_FOUND``·누설 금지) + ``dismissed_at`` 설정(멱등 — 이미 소멸이면 no-op)은
    ``service.dismiss_notification``에 위임한다. 도래 리마인드 '다시 보지 않기'는 행 id가 없어
    별도 ``/reminders/{reservation_id}/dismiss``를 쓴다(KTH 확정 — 동일 dismiss 메커니즘·다른 키).
    미인증은 401.
    """
    service.dismiss_notification(session, principal.user_id, notification_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
