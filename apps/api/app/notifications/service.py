"""notifications 도메인 서비스: 통지 생성/조회/소멸 프리미티브 (Story 5.1, AC2).

**자기완결(도메인 경계 architecture.md L354):** notifications는 자기 ``Notification`` 테이블만
직접 쓴다. 점유/상태/룸 도메인을 침범하지 않는다 — ``room_name`` 합성(룸 PK 조회)은 **라우터**가
하고(service는 rooms import 금지·순환 회피, 4.8 ``list_booker_reservations`` 선례), 통지 생성
트리거(도래 도출=5.2·거절/취소=6.2/8.3)는 **후속 스토리**가 이 프리미티브를 호출해 배선한다.

**프리미티브 3종(AC2):**

- ``create_notification``: 멱등 INSERT(``uq_notifications_user_reservation_type`` 위반 시 기존 행
  반환 — favorites ``add_favorite`` 선별 변환 패턴). 같은 예약·같은 종류 통지는 1건.
- ``list_pending``: ``dismissed_at IS NULL`` 행만 최신순(GET이 소비 — 소멸한 건 안 보임).
- ``dismiss_notification``: 소유권 검증(타 사용자/미존재=404 ``NOTIFICATION_NOT_FOUND``, 누설
  금지 — 4.7 cancel 선례) + ``dismissed_at`` 설정(멱등). '다시 보지 않기'·'확인' 공통 진입점.

**에러:** 신규 ``ErrorCode.NOTIFICATION_NOT_FOUND``(404) 1건. 미인증은 라우터 의존성
(``get_current_principal``)이 401 ``UNAUTHENTICATED``로 막는다.
"""
from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.core.db import violated_constraint
from app.core.errors import DomainError, ErrorCode
from app.core.time import now_utc
from app.notifications.models import Notification, NotificationType


def create_notification(
    session: Session,
    user_id: uuid.UUID,
    reservation_id: uuid.UUID,
    type: NotificationType | str,
    reason: str | None = None,
) -> Notification:
    """사용자에게 표시할 통지를 생성한다(멱등 — AC2).

    ``Notification`` add+commit. 경합/중복으로 ``uq_notifications_user_reservation_type``가
    위반되면(같은 사용자·예약·종류 통지 이미 존재) rollback 후 **기존 행을 조회 반환**(멱등 —
    favorites ``add_favorite``의 ``violated_constraint`` 선별 변환 패턴). 무관한 제약 위반은
    오변환 없이 그대로 re-raise(과대캐치 금지, 회고 P2). 멱등 근거: status_change 재생성(거절 후
    재거절 등 비정상)·reminder 억제행 중복 시 1건으로 수렴한다.

    후속(5.2/6.2/8.3)이 이 프리미티브를 호출해 도래/거절/취소 통지를 배선한다. ``type``은
    ``NotificationType``(또는 그 값 문자열) — DB CHECK가 최종 검증한다.
    """
    notification = Notification(
        user_id=user_id,
        reservation_id=reservation_id,
        type=str(type),
        reason=reason,
    )
    session.add(notification)
    try:
        session.commit()
    except IntegrityError as exc:  # 경합·중복: 이미 같은 (user, reservation, type) 통지 존재
        session.rollback()
        if violated_constraint(exc) == "uq_notifications_user_reservation_type":
            existing = session.exec(
                select(Notification).where(
                    Notification.user_id == user_id,
                    Notification.reservation_id == reservation_id,
                    Notification.type == str(type),
                )
            ).first()
            if existing is not None:
                return existing  # 멱등 — 기존 행 반환
        raise  # 무관한 제약 위반은 그대로 전파(P2)
    session.refresh(notification)
    return notification


def stage_status_change_notification(
    session: Session,
    *,
    user_id: uuid.UUID,
    reservation_id: uuid.UUID,
    reason: str,
) -> None:
    """status_change 통지를 **동일 트랜잭션 편입용**으로 add만 한다(commit/flush 없음 — Story 8.3).

    **왜 별도 프리미티브(★deferred L42 회수 핵심):** 기존 ``create_notification``은 자기
    ``commit`` + ``IntegrityError`` 멱등 처리(별도 트랜잭션 경계 필요)라 상태 전이와의 **원자
    편입에 부적합**하다. 거절/취소 통지를 전이 *후* 별도 트랜잭션으로 만들면, 통지 INSERT가
    실패해도 전이·슬롯 재활성은 이미 영속이라(부분 영속) 재시도가 "이미 종료"로 통지를 건너뛰어
    **통지가 영구 손실**된다(deferred-work L42). 이 함수는 ``session.add``만 하고 **commit을
    호출처(전이 트랜잭션)에 위임**해, status flip + 슬롯 DELETE + 통지 INSERT가 **단일 commit**으로
    묶이게 한다(``_release_slots``의 "commit은 호출처가" 정신). 통지 실패 ⇒ 전이도 롤백 ⇒ 재시도가
    전부 재수행이 성립해 영구 손실이 불가능해진다.

    **멱등(IntegrityError 불요):** 통지는 전이 **winner**(조건부 UPDATE ``rowcount==1``)일 때만
    staged되고, 예약은 ``confirmed→종료``로 **단 한 번** 전이(종료=흡수 상태)하므로 같은
    ``(user, reservation, STATUS_CHANGE)`` 통지는 트랜잭션당 최대 1 INSERT다 →
    ``uq_notifications_user_reservation_type`` 충돌이 발생할 수 없다(이미 종료면 전이 fast-path로
    staging 자체에 도달 안 함). reminder(5.2)는 다른 ``type``이라 충돌 없음.

    Args:
        session: DB 세션. **commit/flush/rollback을 하지 않는다**(호출처 전이가 단일 commit).
        user_id: 통지 수신자(예약자 ``booker_id``).
        reservation_id: 통지 대상 예약(``reservations.id``).
        reason: status_change 부가 사유(``'cancelled'``|``'rejected'`` — 배너 카피 분기 키).
    """
    session.add(
        Notification(
            user_id=user_id,
            reservation_id=reservation_id,
            type=str(NotificationType.STATUS_CHANGE),
            reason=reason,
        )
    )


def list_pending(session: Session, user_id: uuid.UUID) -> list[Notification]:
    """사용자의 미확인 통지를 최신순으로 반환한다(읽기 전용 — AC2).

    ``dismissed_at IS NULL`` 행만(소멸한 건 제외) ``created_at`` 내림차순으로 반환한다. 동시각
    동률은 ``id``로 안정 정렬(결정성). 미확인 통지가 없으면 ``[]``(정상). GET 엔드포인트가
    이 결과를 ``NotificationItem``으로 변환하며 ``room_name``을 합성한다(라우터).
    """
    return list(
        session.exec(
            select(Notification)
            .where(
                Notification.user_id == user_id,
                col(Notification.dismissed_at).is_(None),  # 미확인만
            )
            .order_by(
                col(Notification.created_at).desc(),  # 최신 먼저
                col(Notification.id).desc(),  # 동시각 안정 정렬(결정성)
            )
        ).all()
    )


def dismiss_notification(
    session: Session, user_id: uuid.UUID, notification_id: uuid.UUID
) -> None:
    """사용자의 통지 한 건을 소멸 처리한다(소유권 검증 + 멱등 — AC2·AC5).

    ① 소유권 가드: ``session.get(Notification, id)`` → 미존재이거나 ``user_id``가 요청자가
    아니면 **404 ``NOTIFICATION_NOT_FOUND``**. 타인 통지를 403이 아니라 404로 막아 **타인 통지
    존재 여부를 누설하지 않는다**(4.7 cancel ``RESERVATION_NOT_FOUND`` 선례). ② 이미
    ``dismissed_at``이 설정돼 있으면 멱등 no-op(에러 아님 — 중복 dismiss·재시도 견고성).
    아니면 ``dismissed_at = now_utc()`` + commit해 사용자별 상태를 영속한다('다시 보지 않기'·
    '확인' 공통). 미인증은 라우터 의존성이 401로 먼저 막는다.
    """
    notification = session.get(Notification, notification_id)
    if notification is None or notification.user_id != user_id:
        # 미존재·비소유를 동일 404로 합쳐 타인 통지 존재를 누설하지 않는다(소유권 누설 금지).
        raise DomainError(ErrorCode.NOTIFICATION_NOT_FOUND, "알림을 찾을 수 없습니다.")
    if notification.dismissed_at is not None:
        return  # 이미 소멸 — 멱등 no-op(중복 dismiss 견고성)
    notification.dismissed_at = now_utc()
    session.add(notification)
    session.commit()


def dismissed_reminder_reservation_ids(
    session: Session, user_id: uuid.UUID
) -> set[uuid.UUID]:
    """'다시 보지 않기'한 도래 리마인드의 ``reservation_id`` 집합을 반환한다(읽기 전용·5.2 AC1).

    ``reservation_reminder`` 종류 + ``dismissed_at IS NOT NULL``(억제행 = born-dismissed) 행의
    ``reservation_id``만 조회한다. ``reminders.due_reminder_reservations``가 도출 시 이 집합에 든
    예약을 제외해 **재노출을 막는다**(사용자별 영속). 자기 테이블(``notifications``)만 만진다(도메인
    경계 — rooms/reservations import 0). ``commit``/``add`` 0(읽기 전용).
    """
    statement = select(Notification.reservation_id).where(
        Notification.user_id == user_id,
        Notification.type == str(NotificationType.RESERVATION_REMINDER),
        col(Notification.dismissed_at).is_not(None),  # 억제행(born-dismissed)만
    )
    return set(session.exec(statement).all())


def suppress_reminder(
    session: Session, user_id: uuid.UUID, reservation_id: uuid.UUID
) -> None:
    """도래 리마인드를 사용자별로 영속 억제한다(born-dismissed 억제행 생성·멱등 — Story 5.2 AC2).

    **기존 프리미티브 재사용으로 born-dismissed 행을 만든다(새 dismiss 로직 작성 금지 — KTH 확정):**
    ``create_notification``(멱등 INSERT — uq 위반 시 기존 행 반환)으로 ``reservation_reminder``
    행을 만든 뒤 ``dismiss_notification``(소유권 검증 + ``dismissed_at`` 설정·멱등)으로 소멸시킨다.
    두 프리미티브 모두 멱등이라 전체가 멱등이다 — 재클릭·재시도에도 추가 행 0·``dismissed_at`` 유지.
    소유권은 ``dismiss_notification``이 방금 만든 행에 대해 자명히 통과한다(같은 ``user_id``).

    리마인드는 평소 행 없이 도출되므로(읽기전용), '다시 보지 않기' 시에만 이 함수가 억제행을 1건
    남긴다 → ``dismissed_reminder_reservation_ids``가 그 행을 보고 재도출을 막는다(KTH 확정 #1).
    """
    notification = create_notification(
        session, user_id, reservation_id, NotificationType.RESERVATION_REMINDER
    )
    dismiss_notification(session, user_id, notification.id)
