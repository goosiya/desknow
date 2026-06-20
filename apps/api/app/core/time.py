"""시간 규약 단일 출처 (Story 1.5).

**규약(아키텍처 §Enforcement L283-296 / §Cross-Cutting L378-382):**

- **저장·전송 = UTC(tz-aware).** 시스템 경계를 넘는 모든 datetime은 tz-aware이며,
  와이어 직렬화는 ISO-8601 ``...Z``(``isoformat_utc``)로 일관한다.
- **판정("오늘 / 현재 / N시간 전 / 24시간 이내") = 룸 소재지 타임존(MVP=Asia/Seoul).**
  날짜 경계는 ``ROOM_TZ`` 기준으로 계산하며 **절대 프로세스/클라이언트 로컬 타임존에
  의존하지 않는다**(architecture.md L296 금지 안티패턴 = NFR-1 결정성).
- **naive datetime 거부.** tzinfo 없는 datetime은 ``ValueError``로 즉시 거부한다
  (애매한 로컬 타임존 해석 금지). ``_require_aware``로 일원화한다.
- **now 단일 진입점.** 도메인 코드는 ``datetime.now()``를 직접 호출하지 않는다.
  ``now_utc()``가 유일한 현재시각 출처이며, 판정 함수는 테스트 결정성을 위해
  ``now``를 주입받을 수 있다(미지정 시 ``now_utc()``).

소비처(NFR-1, 구현은 각 스토리): FR-5(핀색 today_in_tz)·FR-12(슬롯)·
FR-16(6h 취소 is_within_hours)·FR-18(24h 리마인드)·FR-20(이용완료 hours_until).
표준 라이브러리(``datetime`` + ``zoneinfo``)만 사용한다 — pytz/pendulum 도입 금지.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from math import isnan
from zoneinfo import ZoneInfo

# MVP 단일 룸 타임존. 룸 다중 타임존 확장 여지를 위해 함수는 tz 파라미터를 받되 기본값=ROOM_TZ.
ROOM_TZ: ZoneInfo = ZoneInfo("Asia/Seoul")


def _require_aware(dt: datetime) -> None:
    """tz-aware datetime인지 검증한다. naive면 ``ValueError``로 거부한다.

    naive datetime을 룸/로컬 타임존으로 암묵 해석하면 날짜 경계 판정이 비결정적이
    되므로(architecture.md L296 금지) 경계에서 즉시 차단한다.
    """
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(
            "naive datetime은 허용되지 않습니다 (tz-aware 필요). "
            "UTC로 만들려면 datetime(..., tzinfo=UTC)를 사용하세요."
        )


def now_utc() -> datetime:
    """현재시각을 tz-aware UTC로 반환한다(현재시각의 유일 진입점).

    도메인 코드는 ``datetime.now()``(naive·로컬 tz)를 직접 호출하지 말고 이 함수를 쓴다.
    """
    return datetime.now(UTC)


def to_tz(dt: datetime, tz: ZoneInfo = ROOM_TZ) -> datetime:
    """aware datetime을 지정 타임존으로 변환한다(표시·날짜 경계 판정 보조).

    naive 입력은 ``ValueError``로 거부한다.
    """
    _require_aware(dt)
    return dt.astimezone(tz)


def today_in_tz(tz: ZoneInfo = ROOM_TZ, now: datetime | None = None) -> date:
    """주어진 순간의 *그 타임존 기준* 날짜("오늘")를 반환한다.

    FR-5("오늘 남은 빈 슬롯")의 날짜 경계 전제. KST는 UTC+9이므로 UTC 15:00 이후는
    KST 익일이 된다(UTC 날짜와 달라지는 지점). now 미지정 시 ``now_utc()``를 쓴다.
    """
    moment = now if now is not None else now_utc()
    return to_tz(moment, tz).date()


def hours_until(target: datetime, now: datetime | None = None) -> float:
    """``target - now``의 시간(hour) 차를 부호 있는 float으로 반환한다.

    양수=아직 남음, 음수=이미 지남. FR-16(6h 취소)·FR-18(24h 리마인드)·
    FR-20(이용완료) 시간 산술의 단일 출처. target/now 모두 tz-aware여야 한다.
    now 미지정 시 ``now_utc()``를 쓴다.
    """
    _require_aware(target)
    current = now if now is not None else now_utc()
    _require_aware(current)
    return (target - current).total_seconds() / 3600


def is_within_hours(target: datetime, hours: float, now: datetime | None = None) -> bool:
    """``target``이 지금부터 ``hours`` 시간 *이내(양 경계 포함)* 미래인지 여부.

    ``0 <= hours_until(target, now) <= hours``. 경계는 **양쪽 모두 포함**한다: 상한은
    정확히 ``hours``만큼 남은 시각(예: 6.0h → "6h 이내"=True), 하한은 현재 그 순간
    (``target == now`` → ``hours_until==0`` → True)이다. 이미 지난 시각(음수)은 False.
    ``hours``가 ``inf``면 미래 전체가 "이내"가 된다. 소비 스토리는 이 경계 규칙을 전제로
    ``<`` vs ``<=`` 정책을 명확히 한다(FR-18 "24h 이내", FR-16 "6h 이내" 등).

    ``hours``는 음수·NaN을 허용하지 않는다 — 무의미한 윈도우가 조용히 항상 False가 되어
    판정 누락을 숨기는 것을 막기 위해 ``ValueError``로 거부한다(결정성/fail-fast).
    """
    if isnan(hours) or hours < 0:
        raise ValueError(f"hours는 음수·NaN을 허용하지 않습니다 (받은 값: {hours!r}).")
    return 0 <= hours_until(target, now) <= hours


def isoformat_utc(dt: datetime) -> str:
    """aware datetime을 ISO-8601 UTC ``...Z`` 문자열로 직렬화한다(와이어 단일 출처).

    Python ``isoformat()``/Pydantic v2 기본은 ``+00:00``을 내므로 UTC로 정규화 후
    ``Z``로 치환한다(architecture.md L263 ``2026-06-14T05:00:00Z`` 규약). naive 거부.
    """
    _require_aware(dt)
    # astimezone(UTC) 후 오프셋은 항상 문자열 끝의 ``+00:00`` → 접미사만 ``Z``로 치환.
    return dt.astimezone(UTC).isoformat().removesuffix("+00:00") + "Z"
