"""시드 관리자 스크립트 테스트 (Story 8.1, AC3 — 멱등 부트스트랩).

DB 불필요 — auth 도메인의 ``FakeSession``(exec/.first()·add·commit)을 재사용해 ``seed_admin()``의
도메인 분기를 단위로 실증한다. ``main()``의 env 미설정 가드는 ``get_settings``를 대체해 검증한다
(라이브 DB·env에 의존하지 않음).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.auth.models import User
from app.core.security import hash_password
from scripts.seed_admin import main, seed_admin
from tests.auth.test_service import FakeSession


def _existing(*, role: str, password: str = "OldPass123!", is_active: bool = True) -> User:
    return User(
        id=uuid.uuid4(),
        email="admin@desknow.kr",
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
        created_at=datetime(2026, 6, 18, tzinfo=UTC),
    )


def test_seed_admin_creates_when_missing() -> None:
    """미존재 → role=admin·is_active=True 계정 생성(이메일 정규화·해시 저장·평문 아님)."""
    session = FakeSession(existing=None)
    rc = seed_admin(session, "Admin@DeskNow.KR", "Str0ng!Pass")

    assert rc == 0
    created = [o for o in session.added if isinstance(o, User)]
    assert len(created) == 1
    user = created[0]
    assert user.email == "admin@desknow.kr"  # strip().lower() 정규화
    assert user.role == "admin"
    assert user.is_active is True
    assert user.password_hash.startswith("$argon2")  # 해시 저장(평문 아님)
    assert session.committed is True


def test_seed_admin_idempotent_rotates_password() -> None:
    """존재 & admin → 비밀번호 재해싱·is_active 보장(멱등 — 중복 행 없음)."""
    existing = _existing(role="admin", password="OldPass123!", is_active=False)
    old_hash = existing.password_hash
    session = FakeSession(existing=existing)

    rc = seed_admin(session, "admin@desknow.kr", "New!Pass456")

    assert rc == 0
    assert existing.password_hash != old_hash  # 비밀번호 로테이션
    assert existing.is_active is True  # 비활성이었어도 활성 보장
    # 새 User 행을 만들지 않는다(기존 행만 갱신 — 중복 없음).
    new_users = [o for o in session.added if isinstance(o, User) and o is not existing]
    assert new_users == []
    assert session.committed is True


def test_seed_admin_refuses_privilege_escalation() -> None:
    """존재 & 비-admin(booker/provider) → 권한 상승 거부(종료 1·미커밋·미추가)."""
    existing = _existing(role="booker")
    session = FakeSession(existing=existing)

    rc = seed_admin(session, "admin@desknow.kr", "New!Pass456")

    assert rc == 1
    assert existing.role == "booker"  # 조용한 역할 변경 없음
    assert session.added == []
    assert session.committed is False


def test_main_missing_env_returns_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """SEED_ADMIN_* 미설정 → main()이 종료 코드 1(DB 접근 전 안내)."""
    import scripts.seed_admin as mod

    monkeypatch.setattr(
        mod,
        "get_settings",
        lambda: SimpleNamespace(SEED_ADMIN_EMAIL=None, SEED_ADMIN_PASSWORD=None),
    )
    # get_engine 호출 시 즉시 실패시켜 "DB 접근 전 종료"를 보증한다(env 미설정 가드 선행).
    monkeypatch.setattr(
        mod, "get_engine", lambda: pytest.fail("env 미설정 시 DB에 접근하면 안 됩니다")
    )

    assert main() == 1
