"""reservations 마이그레이션 + 동시성·상태머신 왕복 통합 테스트 (Story 4.1 — 라이브 DB, 기본 skip).

``TEST_DATABASE_URL``(PostgreSQL DB)이 설정된 경우에만 실행한다(``upgrade head`` →
``downgrade base``가 파괴적이므로 라이브 Supabase가 아니라 **전용 테스트 DB**여야 한다).
CI에 라이브 DB가 없으면 자동 skip → 회귀 0(1.4/2.1 패턴).

검증(AC1·AC2·AC3): ``alembic upgrade head`` 후 ⓐ 2테이블 + 핵심 제약(복합 UNIQUE·CHECK) 존재,
ⓑ **UNIQUE 왕복**(중복 점유 → ``SLOT_CONFLICT``·부분 점유 0), ⓒ **all-or-nothing**(다중 슬롯 중
하나 충돌 시 전체 0건), ⓓ **재활성 왕복**(취소 → 슬롯 DELETE·예약 status 잔존 → 같은 슬롯 재점유
성공), ⓔ ``confirmed_slot_starts`` 차감 seam, ⓕ **CHECK**(비허용 status → IntegrityError)를
확인하고 ``downgrade base``로 정리한다.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

# alembic.ini는 apps/api 루트에 있다(tests/integration/ → parents[2] = apps/api).
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL or "supabase" in TEST_DATABASE_URL,
    # downgrade base = 전 테이블 DROP -> Supabase 등 데이터 보유 DB 금지(일회용 DB만).
    reason="TEST_DATABASE_URL 미설정, 또는 Supabase 등 데이터 보유 DB(downgrade base=전 테이블 DROP 방지) — 일회용 DB에서만 실행.",
)


def test_reservations_migration_concurrency_and_statemachine_roundtrip(monkeypatch):
    from alembic.config import Config
    from sqlalchemy import inspect
    from sqlalchemy.exc import IntegrityError
    from sqlmodel import Session, select

    from alembic import command
    from app.auth.models import User
    from app.core.config import get_settings
    from app.core.db import get_engine
    from app.core.errors import DomainError, ErrorCode
    from app.core.security import hash_password
    from app.reservations.models import Reservation, ReservationSlot, ReservationStatus
    from app.reservations.service import (
        cancel_reservation,
        confirmed_slot_starts,
        create_reservation,
    )
    from app.rooms.models import Room

    # env.py가 settings에서 URL을 읽으므로 필수 키 + 테스트 DB를 환경에 주입한다.
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test")
    monkeypatch.setenv("KAKAO_JS_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-bytes-long-xx")
    get_settings.cache_clear()
    get_engine.cache_clear()

    cfg = Config(str(ALEMBIC_INI))
    try:
        command.upgrade(cfg, "head")

        engine = get_engine()
        inspector = inspect(engine)
        names = set(inspector.get_table_names())
        for t in ("reservations", "reservation_slots"):
            assert t in names, f"마이그레이션 후 {t} 테이블 존재 필요"

        # ⓐ 복합 UNIQUE + CHECK 존재.
        slot_uniques = {
            uc["name"] for uc in inspector.get_unique_constraints("reservation_slots")
        }
        assert "uq_reservation_slots_room_slot" in slot_uniques
        resv_checks = {ck["name"] for ck in inspector.get_check_constraints("reservations")}
        assert "ck_reservations_status" in resv_checks

        # 제공자 + 룸 + 예약자 시드.
        provider = User(
            email="prov-resv@example.com",
            password_hash=hash_password("Test1234!"),
            role="provider",
        )
        booker = User(
            email="booker-resv@example.com",
            password_hash=hash_password("Test1234!"),
            role="booker",
        )
        room = Room(
            provider_id=provider.id,
            name="예약테스트룸",
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
            room_id = room.id
            booker_id = booker.id

        slot_a = datetime(2026, 7, 1, 9, tzinfo=UTC)
        slot_b = slot_a + timedelta(hours=1)

        def _slot_count() -> int:
            with Session(engine) as s:
                return len(s.exec(select(ReservationSlot)).all())

        with Session(engine) as session:
            # ⓑ UNIQUE 왕복: 첫 점유 성공 → 동일 (room_id, slot_a) 재점유 → SLOT_CONFLICT.
            reservation = create_reservation(
                session, booker_id=booker_id, room_id=room_id, slot_starts=[slot_a]
            )
            assert reservation.status == ReservationStatus.CONFIRMED
            assert _slot_count() == 1

            with pytest.raises(DomainError) as exc_info:
                create_reservation(
                    session, booker_id=booker_id, room_id=room_id, slot_starts=[slot_a]
                )
            assert exc_info.value.code is ErrorCode.SLOT_CONFLICT
            assert exc_info.value.status_code == 409
            assert _slot_count() == 1  # 부분 점유 0 — 행 수 불변

            # ⓒ all-or-nothing: [slot_a(점유됨), slot_b] → 전체 실패·0건(slot_b도 미점유).
            with pytest.raises(DomainError) as exc_info:
                create_reservation(
                    session,
                    booker_id=booker_id,
                    room_id=room_id,
                    slot_starts=[slot_a, slot_b],
                )
            assert exc_info.value.code is ErrorCode.SLOT_CONFLICT
            assert _slot_count() == 1  # slot_b가 새지 않음(전체 ROLLBACK)
            assert confirmed_slot_starts(session, room_id) == {slot_a}  # ⓔ 차감 seam

            # ⓓ 재활성 왕복(AC3): 취소 → 슬롯 DELETE + 예약 status='cancelled' 잔존 → 재점유 성공.
            cancelled = cancel_reservation(session, reservation)
            assert cancelled.status == ReservationStatus.CANCELLED
            assert _slot_count() == 0  # 점유 행 제거(재활성)
            assert confirmed_slot_starts(session, room_id) == set()

        with Session(engine) as session:
            # 예약 단위는 히스토리에 cancelled로 잔존(4.7·4.8).
            histories = session.exec(
                select(Reservation).where(Reservation.id == reservation.id)
            ).all()
            assert len(histories) == 1
            assert histories[0].status == ReservationStatus.CANCELLED

            # 같은 슬롯 재점유 성공(슬롯이 재활성됨).
            reservation2 = create_reservation(
                session, booker_id=booker_id, room_id=room_id, slot_starts=[slot_a]
            )
            assert reservation2.status == ReservationStatus.CONFIRMED
            assert _slot_count() == 1

        # ⓕ CHECK: 비허용 status('pending') ORM 삽입 → ck_reservations_status 위반.
        with Session(engine) as session:
            session.add(
                Reservation(booker_id=booker_id, room_id=room_id, status="pending")
            )
            with pytest.raises(IntegrityError):
                session.commit()
    finally:
        command.downgrade(cfg, "base")
        get_settings.cache_clear()
        get_engine.cache_clear()


def test_create_reservation_endpoint_roundtrip(monkeypatch):
    """POST 엔드포인트 통한 신선 재검증 + all-or-nothing 라이브 왕복 (Story 4.5 — AC1·AC2).

    4.1 통합이 service 레벨 UNIQUE/all-or-nothing을 증명했고, 여기선 **엔드포인트 경로**(라우터 →
    신선 재검증 → create_reservation)를 라이브 DB로 1건 보강한다: ① booker 201 ② 같은 슬롯 재요청
    409(UNIQUE를 엔드포인트가 SLOT_CONFLICT로) ③ [점유, 신규] 혼합 → 409 + 신규 슬롯 미점유(전체
    ROLLBACK). 동시성(겹치는 구간 동시 확정)은 4.6.
    """
    from collections.abc import Iterator
    from datetime import date, time

    from alembic.config import Config
    from fastapi.testclient import TestClient
    from sqlmodel import Session

    from alembic import command
    from app.auth.models import User
    from app.core.config import get_settings
    from app.core.db import get_engine, get_session
    from app.core.security import create_access_token, hash_password
    from app.core.time import ROOM_TZ
    from app.main import app
    from app.reservations.service import confirmed_slot_starts
    from app.rooms.models import BusinessHours, Room

    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test")
    monkeypatch.setenv("KAKAO_JS_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-bytes-long-xx")
    get_settings.cache_clear()
    get_engine.cache_clear()

    cfg = Config(str(ALEMBIC_INI))
    # 먼 미래 날짜(신선 재검증 available 결정성 — now 의존 제거). 그 요일 영업시간 09–22 시드.
    future = date(2027, 6, 1)

    def _slot(kst_hour: int) -> str:
        wall = datetime.combine(future, time(kst_hour, 0)).replace(tzinfo=ROOM_TZ)
        return wall.astimezone(UTC).isoformat()

    try:
        command.upgrade(cfg, "head")
        engine = get_engine()

        provider = User(
            email="prov-ep@example.com",
            password_hash=hash_password("Test1234!"),
            role="provider",
        )
        booker = User(
            email="booker-ep@example.com",
            password_hash=hash_password("Test1234!"),
            role="booker",
        )
        room = Room(
            provider_id=provider.id,
            name="엔드포인트룸",
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
            session.add(
                BusinessHours(
                    room_id=room.id,
                    weekday=future.weekday(),
                    open_time=time(9, 0),
                    close_time=time(22, 0),
                )
            )
            session.commit()
            room_id = room.id
            booker_id = booker.id

        def _fake_get_session() -> Iterator[Session]:
            with Session(engine) as s:
                yield s

        app.dependency_overrides[get_session] = _fake_get_session
        token = create_access_token(booker_id, "booker")
        auth = {"Authorization": f"Bearer {token}"}
        url = f"/api/v1/rooms/{room_id}/reservations"
        try:
            client = TestClient(app)

            # ① 신선 재검증 통과 → 201 확정.
            resp = client.post(url, json={"slot_starts": [_slot(14)]}, headers=auth)
            assert resp.status_code == 201, resp.text
            assert resp.json()["status"] == "confirmed"

            # ② 같은 슬롯 재요청 → UNIQUE를 엔드포인트가 409 SLOT_CONFLICT로 변환.
            resp = client.post(url, json={"slot_starts": [_slot(14)]}, headers=auth)
            assert resp.status_code == 409
            assert resp.json()["detail"]["code"] == "SLOT_CONFLICT"

            # ③ [점유(14), 신규(15)] 혼합 → 409 + 신규도 미점유(전체 ROLLBACK · all-or-nothing).
            resp = client.post(
                url, json={"slot_starts": [_slot(14), _slot(15)]}, headers=auth
            )
            assert resp.status_code == 409
            with Session(engine) as session:
                occupied = confirmed_slot_starts(session, room_id)
            assert len(occupied) == 1  # slot 15 가 새지 않음(부분 점유 0)
        finally:
            app.dependency_overrides.clear()
    finally:
        command.downgrade(cfg, "base")
        get_settings.cache_clear()
        get_engine.cache_clear()


def test_availability_deduction_roundtrip(monkeypatch):
    """Story 4.9: 확정 → 가용성 차감 반영 → 취소 → 슬롯 재활성 라이브 왕복(AC1·AC2·AC4).

    rooms.service의 차감 배선(aggregate_availability·get_room_slots)이 **실 SQL reader**
    (confirmed_slot_starts[_by_room])와 **실 DELETE 재활성**(취소)을 통해 정확히 동작함을 라이브
    DB로 검증한다(Fake가 모사하지 못하는 진짜 room_id/on_or_after 필터 + 점유 행 DELETE 왕복):
      ① 확정 전: aggregate=13·get_room_slots reserved 0.
      ② 확정 후: aggregate=12·해당 슬롯 status="reserved"(소멸 아님·len 13 유지).
      ③ 취소 후: aggregate=13 복원·reserved 0(슬롯 재활성).
    """
    from datetime import date, time

    from alembic.config import Config
    from sqlmodel import Session

    from alembic import command
    from app.auth.models import User
    from app.core.config import get_settings
    from app.core.db import get_engine
    from app.core.security import hash_password
    from app.core.time import ROOM_TZ
    from app.reservations.models import Reservation
    from app.reservations.service import cancel_reservation, create_reservation
    from app.rooms.models import BusinessHours, Room
    from app.rooms.service import aggregate_availability, get_room_slots

    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test")
    monkeypatch.setenv("KAKAO_JS_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-bytes-long-xx")
    get_settings.cache_clear()
    get_engine.cache_clear()

    cfg = Config(str(ALEMBIC_INI))
    future = date(2028, 6, 5)  # 결정성용 먼 미래 날짜(그 요일 영업시간 09–22 시드)
    # 주입 now = future 01:00 KST(= future-1 16:00 UTC) → today_in_tz=future, 전 슬롯 미래.
    now_inject = datetime.combine(future, time(1, 0)).replace(tzinfo=ROOM_TZ).astimezone(UTC)
    # 14:00 KST 슬롯 = future 05:00 UTC(derive_slots 출력과 동형 인스턴트).
    slot_14 = datetime.combine(future, time(14, 0)).replace(tzinfo=ROOM_TZ).astimezone(UTC)

    try:
        command.upgrade(cfg, "head")
        engine = get_engine()

        provider = User(
            email="prov-49@example.com",
            password_hash=hash_password("Test1234!"),
            role="provider",
        )
        booker = User(
            email="booker-49@example.com",
            password_hash=hash_password("Test1234!"),
            role="booker",
        )
        room = Room(
            provider_id=provider.id,
            name="차감왕복룸",
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
            session.add(
                BusinessHours(
                    room_id=room.id,
                    weekday=future.weekday(),
                    open_time=time(9, 0),
                    close_time=time(22, 0),
                )
            )
            session.commit()
            room_id = room.id
            booker_id = booker.id

        def _remaining() -> int:
            with Session(engine) as s:
                return next(
                    r.remaining_slots
                    for r in aggregate_availability(s, now=now_inject)
                    if r.room_id == room_id
                )

        def _reserved_starts() -> set[datetime]:
            with Session(engine) as s:
                resp = get_room_slots(s, room_id, future, now=now_inject)
                assert len(resp.slots) == 13  # 소멸 아님 — 항상 전 슬롯 유지
                return {sl.slot_start for sl in resp.slots if sl.status == "reserved"}

        # ① 확정 전.
        assert _remaining() == 13
        assert _reserved_starts() == set()

        # ② 확정 후 — 차감 반영(13→12) + 해당 슬롯 reserved 표시.
        with Session(engine) as session:
            reservation = create_reservation(
                session, booker_id=booker_id, room_id=room_id, slot_starts=[slot_14]
            )
        assert _remaining() == 12
        assert _reserved_starts() == {slot_14}

        # ③ 취소 후 — 슬롯 DELETE(재활성) → 카운트 복원·reserved 0.
        with Session(engine) as session:
            fresh = session.get(Reservation, reservation.id)
            cancel_reservation(session, fresh)
        assert _remaining() == 13
        assert _reserved_starts() == set()
    finally:
        command.downgrade(cfg, "base")
        get_settings.cache_clear()
        get_engine.cache_clear()


def test_reject_endpoint_and_cross_transition_race_roundtrip(monkeypatch):
    """Story 6.2: 거절 엔드포인트 + ★cancel↔reject 조건부 UPDATE 결정화 라이브 왕복(AC1~AC4).

    Fake가 모사 못 하는 **실 SQL rowcount**(``WHERE status='confirmed'``)와 통지 행 생성을 실DB로:
      ① 거절 엔드포인트: provider 본인 룸 confirmed 예약(시작 전) 거절 → 200·rejected·슬롯 DELETE
         (재활성) + 예약자 status_change/reason='rejected' 통지 1행 생성(FR-18a 배선).
      ② 시작 후 거절 → 409 REJECT_WINDOW_PASSED.
      ③ ★조건부 원자 UPDATE 결정화: 같은 confirmed 예약을 두 세션이 stale confirmed로 보고
         reject(승자 rowcount=1)·cancel(패자 rowcount=0) 순차 실행 → 둘째는 슬롯·commit 없이
         현재 상태(rejected)로 수렴. 최종 status·슬롯이 **첫-전이-승자**로 결정적(LWW 제거).
    """
    from collections.abc import Iterator
    from datetime import date, time

    from alembic.config import Config
    from fastapi.testclient import TestClient
    from sqlmodel import Session, select

    from alembic import command
    from app.auth.models import User
    from app.core.config import get_settings
    from app.core.db import get_engine, get_session
    from app.core.security import create_access_token, hash_password
    from app.core.time import ROOM_TZ
    from app.main import app
    from app.notifications.models import Notification, NotificationType
    from app.reservations.models import Reservation, ReservationStatus
    from app.reservations.service import (
        cancel_reservation,
        confirmed_slot_starts,
        create_reservation,
        reject_reservation,
    )
    from app.rooms.models import Room

    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test")
    monkeypatch.setenv("KAKAO_JS_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-bytes-long-xx")
    get_settings.cache_clear()
    get_engine.cache_clear()

    cfg = Config(str(ALEMBIC_INI))
    future = date(2029, 6, 4)  # 먼 미래(시작 전 게이트 결정성 — now_utc()와 무관하게 미래)
    past = date(2020, 1, 6)  # 먼 과거(시작 후 게이트 결정성)

    def _slot(target: date, kst_hour: int) -> datetime:
        wall = datetime.combine(target, time(kst_hour, 0)).replace(tzinfo=ROOM_TZ)
        return wall.astimezone(UTC)

    try:
        command.upgrade(cfg, "head")
        engine = get_engine()

        provider = User(
            email="prov-62@example.com",
            password_hash=hash_password("Test1234!"),
            role="provider",
        )
        booker = User(
            email="booker-62@example.com",
            password_hash=hash_password("Test1234!"),
            role="booker",
        )
        room = Room(
            provider_id=provider.id,
            name="거절왕복룸",
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
            provider_id = provider.id
            room_id = room.id
            booker_id = booker.id

        def _fake_get_session() -> Iterator[Session]:
            with Session(engine) as s:
                yield s

        app.dependency_overrides[get_session] = _fake_get_session
        auth = {"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"}
        try:
            client = TestClient(app)

            # ① 시작 전 confirmed 예약 거절 → 200·rejected·슬롯 DELETE + 통지 1행.
            with Session(engine) as session:
                r1 = create_reservation(
                    session,
                    booker_id=booker_id,
                    room_id=room_id,
                    slot_starts=[_slot(future, 14)],
                )
                r1_id = r1.id
            resp = client.post(f"/api/v1/provider/reservations/{r1_id}/reject", headers=auth)
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "rejected"
            assert resp.json()["slot_starts"] == []
            with Session(engine) as session:
                assert confirmed_slot_starts(session, room_id) == set()  # 슬롯 재활성
                fresh = session.get(Reservation, r1_id)
                assert fresh.status == ReservationStatus.REJECTED  # 히스토리 잔존
                notes = session.exec(
                    select(Notification).where(Notification.reservation_id == r1_id)
                ).all()
                assert len(notes) == 1  # AC2 — 예약자 통지 1행
                assert notes[0].user_id == booker_id
                assert notes[0].type == str(NotificationType.STATUS_CHANGE)
                assert notes[0].reason == "rejected"

            # ② 시작 후 예약 거절 → 409 REJECT_WINDOW_PASSED.
            with Session(engine) as session:
                r_past = create_reservation(
                    session,
                    booker_id=booker_id,
                    room_id=room_id,
                    slot_starts=[_slot(past, 14)],
                )
                r_past_id = r_past.id
            resp = client.post(
                f"/api/v1/provider/reservations/{r_past_id}/reject", headers=auth
            )
            assert resp.status_code == 409
            assert resp.json()["detail"]["code"] == "REJECT_WINDOW_PASSED"
        finally:
            app.dependency_overrides.clear()

        # ③ ★조건부 UPDATE 결정화 — 두 세션이 stale confirmed로 보고 reject·cancel 경합.
        with Session(engine) as session:
            r2 = create_reservation(
                session,
                booker_id=booker_id,
                room_id=room_id,
                slot_starts=[_slot(future, 16)],
            )
            r2_id = r2.id

        s_win = Session(engine)
        s_lose = Session(engine)
        try:
            r_win = s_win.get(Reservation, r2_id)  # stale confirmed
            r_lose = s_lose.get(Reservation, r2_id)  # stale confirmed(같은 행)
            assert r_win.status == ReservationStatus.CONFIRMED
            assert r_lose.status == ReservationStatus.CONFIRMED

            # 거절이 승자(rowcount=1) — status flip + 슬롯 DELETE + commit.
            reject_reservation(s_win, r_win)
            assert r_win.status == ReservationStatus.REJECTED

            # 취소가 패자(WHERE status='confirmed'에 0행 매칭 — DB는 이미 rejected) → rowcount=0.
            cancel_reservation(s_lose, r_lose)
            assert r_lose.status == ReservationStatus.REJECTED  # 결정적 수렴(첫-전이-승자)
        finally:
            s_win.close()
            s_lose.close()

        # 최종 DB 상태·슬롯 결정성 확인(둘째 전이가 덮어쓰지 않음 — last-write-wins 제거).
        with Session(engine) as session:
            final = session.get(Reservation, r2_id)
            assert final.status == ReservationStatus.REJECTED
            assert confirmed_slot_starts(session, room_id) == set()  # 슬롯 1회만 DELETE(중복 0)
    finally:
        command.downgrade(cfg, "base")
        get_settings.cache_clear()
        get_engine.cache_clear()
