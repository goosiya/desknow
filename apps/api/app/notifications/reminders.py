"""notifications 도래 리마인드 도출 **조합 헬퍼** (Story 5.2, AC1·AC5).

**service가 아니라 조합 계층이다(도메인 경계 architecture.md L354).** 도래 리마인드는
``reservations``(점유 시각)와 ``notifications``(억제건)를 **교차**해 도출하는데, 교차 도메인
합성은 라우터 계층의 책임이다(4.8 ``list_booker_reservations`` 라우터 합성·5.1 ``room_name``
2-홉 정신). 라우터에 다 넣으면 테스트가 어려워 **순수/조합 함수만 이 모듈로 추출**한다 —
``notifications.service``는 여전히 자기 테이블만 만지고(rooms/reservations import 0), 이
모듈이 ``reservations.service.list_booker_reservations`` + ``service.dismissed_reminder_
reservation_ids``를 조합한다.

**순환 회피:** ``reminders`` → ``reservations.service`` + ``notifications.service`` 단방향이다.
``notifications.service``는 ``notifications.models``만 import하고 ``reminders``/``reservations``를
import하지 않으므로 사이클이 없다(``reminders``는 라우터·테스트만 import한다).

**24h 경계 = ``timedelta`` 정수 비교(deferred-work.md L103 의무 회수):** 부동소수
``hours_until``/``is_within_hours``를 쓰지 않는다 — 4.7 ``cancel_reservation_for_booker``의
``(earliest - current) < _CANCEL_WINDOW``(``timedelta(hours=6)``) 선례를 미러해 6.0h/24.0h
경계의 1µs 모호성을 제거하고 경계 테스트로 회귀 고정한다.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from sqlmodel import Session

from app.notifications import service
from app.reservations import service as reservations_service
from app.reservations.models import Reservation, ReservationStatus

logger = logging.getLogger(__name__)

# 도래 리마인드 윈도우(FR-18 — "시작 24시간 이내"). 4.7 ``_CANCEL_WINDOW`` 선례 미러.
_REMINDER_WINDOW = timedelta(hours=24)


def earliest_slot_start(reservation: Reservation) -> datetime | None:
    """예약의 가장 이른 원래 점유 슬롯 시각을 안전 파싱해 반환한다(공유 헬퍼 — L7 의무 회수).

    ``slot_starts[0]`` = 생성 시 오름차순 ISO ``...Z`` 스냅샷이라 [0]=earliest(4.8 immutable,
    취소/거절로 ``reservation_slots`` 행이 DELETE돼도 보존 · **추가 쿼리 0**). reminder 도출(윈도
    판정)과 라우터 status_change slot_start 합성이 **양쪽** 이 헬퍼를 거쳐 동일 가드를 공유한다.

    **손상 데이터 방어(deferred-work.md L7 회수 · 코드리뷰 2026-06-17 KTH 결정):** ``slot_starts``는
    ``sa.JSON`` 자유 문자열이라 코드레벨 형식 강제가 없다(수동 DB 조작·마이그레이션 사고 시 비-ISO
    또는 tz 없는 naive ISO 가능). 두 손상 클래스를 **동일하게** 처리한다 — 전파(GET 500) 대신
    ``logger.warning`` + ``None``을 반환해 부분 손상이 전체 GET을 죽이지 않게 한다(reminder는 skip·
    status_change는 slot_start None 폴백): ① ``fromisoformat``이 ``ValueError``(비-ISO) ② 파싱은
    성공했으나 tz 없는 **naive** 결과(``...Z`` 누락 — 윈도 판정 ``_require_aware`` / 직렬화
    ``isoformat_utc``가 둘 다 naive에 ``ValueError``→500이라 비-ISO와 비대칭 500이 되던 갭). 정상
    write는 항상 ``...Z``라 라이브 트리거는 없고 수동 손상 방어심층이다.

    Returns:
        가장 이른 슬롯 시각(aware 파싱 성공) · ``slot_starts`` 비었거나 [0]이 비-ISO/naive면 None.
    """
    if not reservation.slot_starts:
        return None
    raw = reservation.slot_starts[0]
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        logger.warning(
            "손상된 slot_starts[0] 파싱 실패 — None 폴백 (reservation_id=%s, raw=%r)",
            reservation.id,
            raw,
        )
        return None
    # naive(무-Z·tz 없음)도 손상 클래스로 통일(비-ISO와 동일 200 유지). naive가 윈도
    # _require_aware / 직렬화 isoformat_utc에 닿으면 ValueError→GET 500이 되므로 여기서 차단.
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        logger.warning(
            "naive slot_starts[0] (tz 없음) — None 폴백 (reservation_id=%s, raw=%r)",
            reservation.id,
            raw,
        )
        return None
    return parsed


def _require_aware(dt: datetime, label: str) -> None:
    """tz-aware datetime인지 검증한다(naive 거부 — reservations.service ``_require_aware`` 철학).

    slot_start·now는 UTC aware로 저장·전달된다. naive를 받으면 시각 차 비교가 비결정적이 되어
    경계 판정이 틀어지므로(조용한 오판) 경계에서 즉시 ``ValueError``로 차단한다.
    """
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(
            f"{label}은(는) tz-aware여야 합니다 (naive datetime 금지) — "
            "slot_start·now는 UTC로 저장·전달됩니다."
        )


def is_within_reminder_window(earliest: datetime, now: datetime) -> bool:
    """가장 이른 점유 슬롯이 지금부터 ``[0, 24h]`` 미래 안인지(양 경계 포함) — 순수 함수(AC1·AC5).

    ``timedelta(0) <= (earliest - now) <= _REMINDER_WINDOW``. **부동소수 미사용**(L103 회수):
    하한 0(``earliest == now`` = 지금 시작 → 포함)·상한 정확히 24h(포함). 이미 시작한 과거 슬롯
    (음수 delta)·24h 초과는 제외한다. 도메인 import 0(``earliest``/``now``만 받는 순수 비교).
    ``earliest``/``now`` 모두 tz-aware여야 한다(naive면 ``ValueError`` — fail-fast).
    """
    _require_aware(earliest, "earliest")
    _require_aware(now, "now")
    return timedelta(0) <= (earliest - now) <= _REMINDER_WINDOW


def due_reminder_reservations(
    session: Session, user_id: uuid.UUID, now: datetime
) -> list[Reservation]:
    """24h 이내 도래하는 **도출 대상 확정 예약**을 반환한다(읽기 전용·행 생성 0 — AC1).

    조합(라우터 계층 책임): ``reservations.service.list_booker_reservations``로 본인 예약을 받아
    ① ``status == confirmed``(취소/거절은 점유 슬롯 DELETE라 도래 의미 없음·status_change가 별도
    처리) ② ``service.dismissed_reminder_reservation_ids``로 '다시 보지 않기'한 예약 제외
    ③ 가장 이른 슬롯(``slot_starts[0]`` — 생성 시 오름차순 ISO ...Z 스냅샷이라 [0]=earliest,
    추가 쿼리 0)이 24h 윈도우 안인 예약만 남긴다. ``slot_starts`` 빈 예약은 방어 skip(confirmed는
    ≥1 보장이나 fail-safe). **DB 쓰기 0**(억제건 조회만) — 행 없이 도출한다.

    Args:
        session: DB 세션(**읽기 전용**).
        user_id: 조회 대상 사용자(인증 principal).
        now: 판정 기준 시각(UTC aware — 라우터가 ``now_utc()``로 1회 캡처해 일관 주입). naive면
            ``ValueError``.

    Returns:
        도출 대상 ``Reservation`` 리스트(``list_booker_reservations`` 순서 = ``created_at`` desc;
        slot_start 임박순 정렬은 라우터가 ``NotificationItem`` 변환 시 수행).
    """
    _require_aware(now, "now")
    reservations = reservations_service.list_booker_reservations(session, user_id)
    suppressed = service.dismissed_reminder_reservation_ids(session, user_id)
    due: list[Reservation] = []
    for reservation in reservations:
        if reservation.status != ReservationStatus.CONFIRMED:
            continue  # 종료 상태(취소/거절)는 도래 의미 없음
        if reservation.id in suppressed:
            continue  # '다시 보지 않기' 억제
        # slot_starts[0] = 가장 이른 슬롯(생성 시 오름차순 ISO ...Z 스냅샷). 빈 slot_starts(방어,
        # confirmed는 ≥1 보장이나 fail-safe)·손상 비-ISO/naive(L7·코드리뷰 2026-06-17)는 헬퍼가
        # None을 반환 → 안전 skip(이전엔 ValueError→GET 500이던 경로).
        earliest = earliest_slot_start(reservation)
        if earliest is None:
            continue
        if is_within_reminder_window(earliest, now):
            due.append(reservation)
    return due
