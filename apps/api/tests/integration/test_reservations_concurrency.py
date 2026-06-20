"""reservations 동시성 본격 검증 — 진짜 멀티스레드 race + 겹치는 구간 (Story 4.6 — AC1·AC2·SM-4).

``TEST_DATABASE_URL``(전용 테스트 PostgreSQL)이 설정된 경우에만 실행한다 — ``upgrade head`` →
``downgrade base``가 파괴적이므로 **라이브 Supabase 금지**(전용 테스트 DB만). CI에 라이브 DB가
없으면 자동 skip → 회귀 0(4.1 ``test_reservations_migration.py`` 선례 동형).

여기서 증명하는 것(결정적 직렬 단위 테스트 ``tests/reservations/test_concurrency.py``를 보완):

- **진짜 멀티스레드 race(SM-4·AC1):** N개 스레드가 **각자 독립 Session/connection**으로 동일 슬롯을
  ``threading.Barrier``로 동시 출발해 확정 → Postgres가 UNIQUE 위반을 커밋 시점에 직렬화하므로
  **정확히 1건 성공·나머지 N-1건 ``SLOT_CONFLICT``·해당 슬롯 점유 행 정확히 1개**(중복 점유 0).
- **겹치는 연속 구간 부분 점유 0(AC2):** A가 14·15·16 확정 후 B가 16·17·18 확정 시도 → 16 겹침
  → ``SLOT_CONFLICT``이고 **B는 18시 빈 슬롯조차 점유 0건**(전체 ROLLBACK) → A의 3행만 잔존.
  역방향(B 먼저)도 대칭 확인.

SQLite로는 무의미(단일 라이터 → 진짜 동시성 부재)하므로 skipif로 라이브 DB에서만 돈다.
"""
from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

# alembic.ini는 apps/api 루트에 있다(tests/integration/ → parents[2] = apps/api).
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL or "supabase" in TEST_DATABASE_URL,
    # downgrade base = 전 테이블 DROP -> Supabase 등 데이터 보유 DB 금지(일회용 DB만).
    reason="TEST_DATABASE_URL 미설정, 또는 Supabase 등 데이터 보유 DB(downgrade base=전 테이블 DROP 방지) — 일회용 DB에서만 실행(SQLite 무의미).",
)


def _seed_provider_booker_room(engine):
    """제공자 1·예약자 1·룸 1을 시드하고 ``(room_id, booker_id)``를 반환한다(테스트 공용)."""
    from sqlmodel import Session

    from app.auth.models import User
    from app.core.security import hash_password
    from app.rooms.models import Room

    provider = User(
        email=f"prov-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("Test1234!"),
        role="provider",
    )
    booker = User(
        email=f"booker-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("Test1234!"),
        role="booker",
    )
    room = Room(
        provider_id=provider.id,
        name="동시성테스트룸",
        price_per_hour=10000,
        capacity=4,
        room_type="open",
        amenities=["wifi"],
        lat=37.5,
        lng=127.0,
        admin_dong_code="1168010100",
    )
    with Session(engine) as session:
        session.add(provider)
        session.add(booker)
        session.add(room)
        session.commit()
        return room.id, booker.id


def _inject_test_env(monkeypatch):
    """env.py가 settings에서 읽는 필수 키 + 전용 테스트 DB를 주입하고 캐시를 비운다."""
    from app.core.config import get_settings
    from app.core.db import get_engine

    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test")
    monkeypatch.setenv("KAKAO_JS_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-bytes-long-xx")
    get_settings.cache_clear()
    get_engine.cache_clear()


def test_true_concurrent_same_slot_exactly_one_wins(monkeypatch):
    """N개 스레드가 동일 슬롯 동시 확정 → 정확히 1건 성공·N-1건 SLOT_CONFLICT·점유 행 1개(AC1·SM-4).

    스레드별 독립 ``Session``(공유 세션 금지 — 진짜 커넥션 경합 재현)으로 ``threading.Barrier``에
    모두 도달한 뒤 동시에 ``create_reservation``을 호출한다. Postgres가 UNIQUE를 커밋 시점에
    직렬화하므로 하나만 통과한다.
    """
    from alembic.config import Config
    from sqlmodel import Session, select

    from alembic import command
    from app.core.config import get_settings
    from app.core.db import get_engine
    from app.core.errors import DomainError, ErrorCode
    from app.reservations.models import ReservationSlot
    from app.reservations.service import create_reservation

    _inject_test_env(monkeypatch)
    cfg = Config(str(ALEMBIC_INI))
    n_threads = 8
    slot = datetime(2027, 7, 1, 9, tzinfo=UTC)

    try:
        command.upgrade(cfg, "head")
        engine = get_engine()
        room_id, booker_id = _seed_provider_booker_room(engine)

        barrier = threading.Barrier(n_threads)
        results: list[str] = []
        results_lock = threading.Lock()

        def _attempt(_index: int) -> None:
            # 스레드별 독립 Session/connection — 공유 세션이면 진짜 동시성이 아니다.
            barrier.wait()  # 모든 스레드 동시 출발 정렬
            with Session(engine) as session:
                try:
                    create_reservation(
                        session,
                        booker_id=booker_id,
                        room_id=room_id,
                        slot_starts=[slot],
                    )
                    outcome = "ok"
                except DomainError as exc:
                    assert exc.code is ErrorCode.SLOT_CONFLICT
                    assert exc.status_code == 409
                    outcome = "conflict"
            with results_lock:
                results.append(outcome)

        with ThreadPoolExecutor(max_workers=n_threads) as pool:
            futures = [pool.submit(_attempt, i) for i in range(n_threads)]
            for future in futures:
                future.result()  # 스레드 내 예외(예: 예상 못한 IntegrityError) 전파

        assert results.count("ok") == 1, f"정확히 1건만 성공해야 함: {results}"
        assert results.count("conflict") == n_threads - 1

        # 점유 행은 그 슬롯에 정확히 1개(중복 점유 0).
        with Session(engine) as session:
            rows = session.exec(
                select(ReservationSlot).where(ReservationSlot.slot_start == slot)
            ).all()
            assert len(rows) == 1
    finally:
        command.downgrade(cfg, "base")
        get_settings.cache_clear()
        get_engine.cache_clear()


@pytest.mark.parametrize("b_first", [False, True])
def test_overlapping_contiguous_no_partial_occupancy(monkeypatch, b_first: bool):
    """겹치는 연속 구간 — 한쪽 전체 성립·다른 쪽 부분 점유 0 (AC2).

    A=14·15·16, B=16·17·18(16 겹침). 먼저 확정한 쪽이 전체 성립하고, 나중 쪽은 ``SLOT_CONFLICT``로
    **단 하나의 슬롯도 점유하지 않는다**(18시 빈 슬롯조차 — 전체 ROLLBACK). 양방향(A 먼저/B 먼저)
    대칭 확인.
    """
    from alembic.config import Config
    from sqlmodel import Session

    from alembic import command
    from app.core.config import get_settings
    from app.core.db import get_engine
    from app.core.errors import DomainError, ErrorCode
    from app.reservations.service import confirmed_slot_starts, create_reservation

    _inject_test_env(monkeypatch)
    cfg = Config(str(ALEMBIC_INI))

    def _slots(*hours: int) -> list[datetime]:
        base = datetime(2027, 8, 1, 0, tzinfo=UTC)
        return [base + timedelta(hours=h) for h in hours]

    a_slots = _slots(14, 15, 16)
    b_slots = _slots(16, 17, 18)
    first, second = (b_slots, a_slots) if b_first else (a_slots, b_slots)

    try:
        command.upgrade(cfg, "head")
        engine = get_engine()
        room_id, booker_id = _seed_provider_booker_room(engine)

        with Session(engine) as session:
            # 먼저 확정한 쪽은 전체 성립.
            create_reservation(
                session, booker_id=booker_id, room_id=room_id, slot_starts=first
            )
            # 나중 쪽은 16 겹침으로 SLOT_CONFLICT.
            with pytest.raises(DomainError) as exc_info:
                create_reservation(
                    session, booker_id=booker_id, room_id=room_id, slot_starts=second
                )
            assert exc_info.value.code is ErrorCode.SLOT_CONFLICT

            # 부분 점유 0 — 점유된 슬롯은 먼저 확정한 쪽의 3개뿐(나중 쪽의 비겹침 슬롯 미점유).
            occupied = confirmed_slot_starts(session, room_id)
            assert occupied == set(first)
            assert len(occupied) == 3
    finally:
        command.downgrade(cfg, "base")
        get_settings.cache_clear()
        get_engine.cache_clear()


def test_true_concurrent_cancel_is_harmless_and_reactivates(monkeypatch):
    """진짜 멀티스레드 동시 취소 → 데이터 손상 0·둘 다 cancelled 수렴·슬롯 재활성 (AC5·NFR-7).

    같은 confirmed 예약(6h+ 미래 슬롯)을 N개 스레드가 **각자 독립 Session**으로 ``Barrier`` 동시
    출발해 취소한다. read-then-flip race(둘 다 confirmed로 읽고 진입)에서도 ① 예외 0(둘째의 슬롯
    DELETE는 이미 0행 = 무해 no-op) ② 예약은 cancelled로 수렴 ③ **점유 행 0개 잔존**(중복/잔존
    손상 0) ④ 같은 슬롯 재예약 성공. → 낙관적 락 미도입이 sound(deferred L12 회수)임을 실DB로 증명.
    """
    from alembic.config import Config
    from sqlmodel import Session, select

    from alembic import command
    from app.core.config import get_settings
    from app.core.db import get_engine
    from app.reservations.models import (
        Reservation,
        ReservationSlot,
        ReservationStatus,
    )
    from app.reservations.service import (
        cancel_reservation_for_booker,
        create_reservation,
    )

    _inject_test_env(monkeypatch)
    cfg = Config(str(ALEMBIC_INI))
    n_threads = 6
    slot = datetime(2099, 9, 1, 9, tzinfo=UTC)  # 먼 미래 — 6h 게이트 통과

    try:
        command.upgrade(cfg, "head")
        engine = get_engine()
        room_id, booker_id = _seed_provider_booker_room(engine)

        # 확정 예약 1건 생성.
        with Session(engine) as session:
            reservation = create_reservation(
                session, booker_id=booker_id, room_id=room_id, slot_starts=[slot]
            )
            reservation_id = reservation.id

        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []
        errors_lock = threading.Lock()

        def _cancel(_index: int) -> None:
            barrier.wait()  # 동시 출발 정렬(둘 다 confirmed로 읽도록)
            try:
                with Session(engine) as session:
                    loaded = session.get(Reservation, reservation_id)
                    cancel_reservation_for_booker(session, loaded)
            except Exception as exc:  # noqa: BLE001 — 무해성 단언을 위해 수집
                with errors_lock:
                    errors.append(exc)

        with ThreadPoolExecutor(max_workers=n_threads) as pool:
            futures = [pool.submit(_cancel, i) for i in range(n_threads)]
            for future in futures:
                future.result()

        assert errors == [], f"동시 취소는 무해해야 함(예외 0): {errors}"

        with Session(engine) as session:
            # ② cancelled 수렴.
            row = session.get(Reservation, reservation_id)
            assert row is not None
            assert row.status == ReservationStatus.CANCELLED
            # ③ 점유 행 0개 잔존(슬롯 재활성·손상 0).
            slot_rows = session.exec(
                select(ReservationSlot).where(
                    ReservationSlot.reservation_id == reservation_id
                )
            ).all()
            assert slot_rows == []

            # ④ 같은 슬롯 재예약 성공(재활성됨).
            reused = create_reservation(
                session, booker_id=booker_id, room_id=room_id, slot_starts=[slot]
            )
            assert reused.status == ReservationStatus.CONFIRMED
    finally:
        command.downgrade(cfg, "base")
        get_settings.cache_clear()
        get_engine.cache_clear()
