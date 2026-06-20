"""rooms 마이그레이션 + 제약 왕복 통합 테스트 (Story 2.1 — 라이브 DB 필요, 기본 skip).

``TEST_DATABASE_URL``(PostgreSQL+pgvector 가능 DB)이 설정된 경우에만 실행한다.
CI에 라이브 DB가 없으면 자동 skip → 회귀 0(1.4/1.7 패턴).

검증: ``alembic upgrade head`` 후 ⓐ 3테이블 + 핵심 제약(복합 UNIQUE) 존재,
ⓑ 룸 INSERT 후 동일 (room_id, weekday) business_hours 재삽입 시 복합 UNIQUE 위반,
ⓒ ``close_time <= open_time`` 삽입 시 CHECK 위반을 확인하고, ``downgrade base``로 정리한다.
"""
from __future__ import annotations

import os
from datetime import time
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


def test_rooms_migration_and_constraint_roundtrip(monkeypatch):
    from alembic.config import Config
    from sqlalchemy import inspect
    from sqlalchemy.exc import IntegrityError
    from sqlmodel import Session

    from alembic import command
    from app.auth.models import User
    from app.core.config import get_settings
    from app.core.db import get_engine
    from app.core.security import hash_password
    from app.rooms.models import BusinessHours, Room

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
        for t in ("rooms", "business_hours", "holiday_exceptions"):
            assert t in names, f"마이그레이션 후 {t} 테이블 존재 필요"

        bh_uniques = {uc["name"] for uc in inspector.get_unique_constraints("business_hours")}
        assert "uq_business_hours_room_id_weekday" in bh_uniques
        hx_uniques = {uc["name"] for uc in inspector.get_unique_constraints("holiday_exceptions")}
        assert "uq_holiday_exceptions_room_id_holiday_date" in hx_uniques

        # 제공자(룸 FK 대상) + 룸 1개 생성.
        provider = User(
            email="prov-rooms@example.com",
            password_hash=hash_password("Test1234!"),
            role="provider",
        )
        room = Room(
            provider_id=provider.id,
            name="테스트룸",
            price_per_hour=10000,
            capacity=4,
            room_type="open",
            amenities=["wifi", "기타"],
            lat=37.5,
            lng=127.0,
            admin_dong_code="1168010100",
        )
        with Session(engine) as session:
            session.add(provider)
            session.add(room)
            session.commit()
            room_id = room.id

        # ⓑ 동일 (room_id, weekday) 재삽입 → 복합 UNIQUE 위반.
        with Session(engine) as session:
            session.add(
                BusinessHours(room_id=room_id, weekday=0, open_time=time(9), close_time=time(22))
            )
            session.commit()
        with Session(engine) as session:
            session.add(
                BusinessHours(room_id=room_id, weekday=0, open_time=time(10), close_time=time(20))
            )
            with pytest.raises(IntegrityError):
                session.commit()

        # ⓒ close_time <= open_time → CHECK(ck_business_hours_hours_order) 위반.
        with Session(engine) as session:
            session.add(
                BusinessHours(room_id=room_id, weekday=1, open_time=time(22), close_time=time(9))
            )
            with pytest.raises(IntegrityError):
                session.commit()

        # ⓓ amenities JSONB 배열이 그대로 왕복.
        with Session(engine) as session:
            fetched = session.get(Room, room_id)
            assert fetched is not None
            assert fetched.amenities == ["wifi", "기타"]
            assert fetched.is_active is True

        # ── Story 2.2 신규 제약(b2c4f1a9d3e7) ─────────────────────────────────
        # ⓔ uq_rooms_provider_id — 같은 provider 2번째 룸 → UNIQUE 위반(AC4).
        rooms_uniques = {uc["name"] for uc in inspector.get_unique_constraints("rooms")}
        assert "uq_rooms_provider_id" in rooms_uniques
        with Session(engine) as session:
            session.add(
                Room(
                    provider_id=provider.id,
                    name="두번째룸",
                    price_per_hour=10000,
                    capacity=4,
                    room_type="open",
                    amenities=[],
                    lat=37.5,
                    lng=127.0,
                    admin_dong_code="1168010100",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()

        # ⓕ ck_rooms_room_type — 비허용 room_type(자유 문자열로 ORM 삽입) → CHECK 위반(P3).
        #    FK·UNIQUE 충돌을 피하려 룸 없는 새 provider를 만들어 사용한다.
        def _new_provider(email: str) -> User:
            p = User(email=email, password_hash=hash_password("Test1234!"), role="provider")
            with Session(engine) as s:
                s.add(p)
                s.commit()
                s.refresh(p)
            return p

        prov_bad_type = _new_provider("prov-badtype@example.com")
        with Session(engine) as session:
            session.add(
                Room(
                    provider_id=prov_bad_type.id, name="x", price_per_hour=1000, capacity=1,
                    room_type="shared", amenities=[], lat=37.5, lng=127.0,
                    admin_dong_code="1",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()

        # ⓖ 값 범위 CHECK — 음수 price → ck_rooms_price_per_hour_nonneg 위반(2.1 defer 회수).
        prov_neg = _new_provider("prov-neg@example.com")
        with Session(engine) as session:
            session.add(
                Room(
                    provider_id=prov_neg.id, name="x", price_per_hour=-1, capacity=1,
                    room_type="open", amenities=[], lat=37.5, lng=127.0, admin_dong_code="1",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()

        # ⓗ ck_users_role — 비허용 role(자유 문자열로 ORM 삽입) → CHECK 위반(P3).
        with Session(engine) as session:
            session.add(
                User(
                    email="bad-role@example.com",
                    password_hash=hash_password("Test1234!"),
                    role="superuser",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
    finally:
        command.downgrade(cfg, "base")
        get_settings.cache_clear()
        get_engine.cache_clear()


def test_create_room_service_fk_ordering_roundtrip(monkeypatch):
    """``create_room`` 서비스가 실 Postgres FK 순서로 룸+영업시간을 원자 저장한다(E2E 회귀).

    유닛 테스트(``FakeRoomSession``)는 실 FK를 경유하지 않아, 자식(``business_hours``)이
    부모(``rooms``)보다 먼저 INSERT되는 순서 위반을 못 잡는다 — psycopg3 + 실 Postgres에서만
    재현되는 ``fk_business_hours_room_id_rooms`` 위반(미처리 500)이었다(E2E 검증 중 발견).
    ``service.create_room``의 **room flush 선행** 수정(service.py L857)이 이 경로를 막는지
    라이브로 못 박는다 — flush가 빠지면 아래 ``create_room`` 호출이 IntegrityError로 실패한다.
    """
    from datetime import time

    from sqlmodel import Session, select

    from alembic.config import Config
    from alembic import command
    from app.auth.models import User
    from app.core.config import get_settings
    from app.core.db import get_engine
    from app.core.security import hash_password
    from app.rooms.models import BusinessHours, Room
    from app.rooms.schemas import BusinessHoursInput, RoomCreateRequest
    from app.rooms.service import create_room

    # env.py가 settings에서 URL을 읽으므로 필수 키 + 테스트 DB를 환경에 주입한다(상단 테스트 동일).
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

        # 룸 FK 대상 provider 1명 생성(룸 미보유 → 제공자당 1개 선검사 통과).
        provider = User(
            email="prov-create-room@example.com",
            password_hash=hash_password("Test1234!"),
            role="provider",
        )
        with Session(engine) as session:
            session.add(provider)
            session.commit()
            provider_id = provider.id

        # 서비스 경로로 등록 — 영업시간 2행(자식)이 룸(부모) FK를 참조한다. flush 선행 수정이
        # 없으면 자식 INSERT가 부모보다 앞서 FK 위반(IntegrityError)이 난다 → 이 호출이 회귀 가드.
        req = RoomCreateRequest(
            name="회귀룸",
            price_per_hour=12000,
            capacity=4,
            room_type="open",
            amenities=["wifi"],
            lat=37.5,
            lng=127.0,
            admin_dong_code="1168010100",
            business_hours=[
                BusinessHoursInput(weekday=0, open_time=time(9), close_time=time(18)),
                BusinessHoursInput(weekday=1, open_time=time(10), close_time=time(20)),
            ],
        )
        with Session(engine) as session:
            room = create_room(session, provider_id, req)
            room_id = room.id
            assert room.provider_id == provider_id

        # 룸 + 영업시간 2행이 실제로 영속됐는지 별도 세션에서 확인(원자 커밋).
        with Session(engine) as session:
            fetched = session.get(Room, room_id)
            assert fetched is not None
            assert fetched.provider_id == provider_id
            bhs = session.exec(
                select(BusinessHours).where(BusinessHours.room_id == room_id)
            ).all()
            assert {bh.weekday for bh in bhs} == {0, 1}  # 자식 2행이 부모 FK로 정착
    finally:
        command.downgrade(cfg, "base")
        get_settings.cache_clear()
        get_engine.cache_clear()
