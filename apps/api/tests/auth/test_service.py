"""auth 서비스 테스트 (Story 1.7 가입 + 1.8 인증/발급/회전/무효화).

DB 불필요 — **Fake 세션**으로 도메인 로직을 실증한다. 라이브 DB 왕복은
tests/integration/test_auth_*.py(skipif 가드)가 담당.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app.auth.models import RefreshToken, User
from app.auth.schemas import RegisterRequest
from app.auth.service import (
    authenticate_user,
    get_user_by_id,
    issue_token_pair,
    register_user,
    revoke_refresh_token,
    rotate_token_pair,
)
from app.core.errors import DomainError, ErrorCode
from app.core.security import (
    create_refresh_token,
    hash_password,
    hash_token,
)
from app.core.time import now_utc


class _FakeResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def first(self) -> Any:
        return self._value


class _FakeDiag:
    """psycopg ``Diagnostic`` 모방 — ``constraint_name``만 노출한다(P2 violated_constraint 실증)."""

    def __init__(self, constraint_name: str | None) -> None:
        self.constraint_name = constraint_name


class _FakeOrig(Exception):
    """psycopg ``exc.orig`` 모방 — ``diag.constraint_name``을 노출한다(P2 선별 변환 실증).

    실제 psycopg3는 ``IntegrityError.orig.diag.constraint_name``으로 위반 제약명을 준다.
    이 Fake가 그 경로를 충실히 재현해 ``core/db.violated_constraint``의 분기를 실증한다
    (인자 무시 자기충족 Fake 금지 — 회고 A2).
    """

    def __init__(self, constraint_name: str | None) -> None:
        super().__init__("duplicate key value violates unique constraint")
        self.diag = _FakeDiag(constraint_name)


class FakeSession:
    """Session 인터페이스(exec/get/add/delete/commit/refresh/rollback)를 흉내낸다.

    - ``existing``: ``select(User).where(email==...)``가 반환할 User(가입/로그인 선검사).
    - ``users_by_id``: ``session.get(User, id)`` 조회 맵(``/me``·회전).
    - ``tokens_by_hash``: ``select(RefreshToken).where(token_hash==...)`` 조회 맵(회전/로그아웃).
    - ``raise_on_commit``: True면 commit 시 ``IntegrityError``를 던진다. 그 orig.diag의
      ``constraint_name``은 ``commit_violation``(기본 ``uq_users_email`` — 가입 경합 기본
      시나리오). 무관 제약 re-raise 분기는 다른 값을 준다(Story 2.2 P2).
    register 테스트와의 하위호환을 위해 ``existing``/``raise_on_commit`` 시그니처를 보존한다.
    """

    def __init__(
        self,
        existing: User | None = None,
        raise_on_commit: bool = False,
        *,
        users_by_id: dict[uuid.UUID, User] | None = None,
        tokens_by_hash: dict[str, RefreshToken] | None = None,
        commit_violation: str | None = "uq_users_email",
    ) -> None:
        self.existing = existing
        self.raise_on_commit = raise_on_commit
        self.commit_violation = commit_violation
        self.users_by_id = users_by_id or {}
        self.tokens_by_hash = tokens_by_hash or {}
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.rolled_back = False
        self.committed = False
        self.commit_count = 0

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> _FakeResult:
        entity = statement.column_descriptions[0]["entity"]
        if entity is RefreshToken:
            value = statement.whereclause.right.value  # token_hash == <value>
            return _FakeResult(self.tokens_by_hash.get(value))
        return _FakeResult(self.existing)  # User(가입/로그인) — 하위호환

    def get(self, model: Any, pk: Any) -> Any:
        return self.users_by_id.get(pk)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def delete(self, obj: Any) -> None:
        self.deleted.append(obj)

    def commit(self) -> None:
        if self.raise_on_commit:
            # orig.diag.constraint_name을 단 IntegrityError(psycopg3 충실 재현) → P2 선별 변환.
            raise IntegrityError("stmt", {}, _FakeOrig(self.commit_violation))
        self.committed = True
        self.commit_count += 1

    def refresh(self, obj: Any) -> None:
        pass

    def rollback(self) -> None:
        self.rolled_back = True


def _request(email: str = "User@Example.com", role: str = "booker") -> RegisterRequest:
    return RegisterRequest(email=email, password="Test1234!", role=role)


def _user(
    *, email: str = "user@example.com", role: str = "booker", is_active: bool = True,
    password: str = "Test1234!", password_hash: str | None = None,
) -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash=password_hash if password_hash is not None else hash_password(password),
        role=role,
        is_active=is_active,
        created_at=datetime(2026, 6, 15, tzinfo=UTC),
    )


# ── 가입(1.7) ─────────────────────────────────────────────────────────────────
def test_register_user_creates_account_with_normalized_email_and_hash() -> None:
    """신규 가입: 이메일 소문자 정규화·해시 저장(평문 아님)·역할 보존·is_active=True(AC1)."""
    session = FakeSession(existing=None)
    user = register_user(session, _request(email="User@Example.com", role="provider"))

    assert isinstance(user, User)
    assert user.email == "user@example.com"  # 소문자 정규화
    assert user.role == "provider"
    assert user.is_active is True
    assert user.password_hash != "Test1234!"  # 평문 저장 금지
    assert user.password_hash.startswith("$argon2")
    assert session.committed is True
    assert user in session.added


def test_register_user_rejects_existing_email() -> None:
    """기존 이메일 존재 시 DomainError(EMAIL_TAKEN, 409)로 거부한다(AC3 선검사)."""
    session = FakeSession(existing=_user())

    with pytest.raises(DomainError) as exc_info:
        register_user(session, _request())

    assert exc_info.value.code is ErrorCode.EMAIL_TAKEN
    assert exc_info.value.status_code == 409
    assert session.added == []  # 삽입 시도 없음


def test_register_user_converts_integrity_error_to_email_taken() -> None:
    """경합 시 uq_users_email 위반 IntegrityError → rollback + EMAIL_TAKEN 변환(AC3 이중방어).

    Story 2.2 P2 정합화 후에도 보존되는 회귀: 제약명이 uq_users_email일 때만 변환한다.
    """
    # commit_violation 기본값 = uq_users_email (가입 경합 기본 시나리오).
    session = FakeSession(existing=None, raise_on_commit=True)

    with pytest.raises(DomainError) as exc_info:
        register_user(session, _request())

    assert exc_info.value.code is ErrorCode.EMAIL_TAKEN
    assert exc_info.value.status_code == 409
    assert session.rolled_back is True


def test_register_user_reraises_unrelated_integrity_error() -> None:
    """무관한 제약 위반(uq_users_email 아님)은 EMAIL_TAKEN으로 오변환하지 않고 re-raise한다(P2).

    포괄 캐치(과대캐치)를 제약명 선별 변환으로 교체한 회수의 핵심 — 다른 제약 위반을
    EMAIL_TAKEN으로 둔갑시키면 디버깅 불가한 거짓 409가 된다.
    """
    session = FakeSession(
        existing=None, raise_on_commit=True, commit_violation="some_other_constraint"
    )

    with pytest.raises(IntegrityError):
        register_user(session, _request())

    assert session.rolled_back is True
    assert session.committed is False


# ── 로그인 인증(1.8, AC2) ─────────────────────────────────────────────────────
def test_authenticate_user_success() -> None:
    """올바른 자격 증명이면 User를 반환한다(이메일 대소문자 무관)."""
    user = _user(email="user@example.com", password="Test1234!")
    session = FakeSession(existing=user)
    result = authenticate_user(session, "User@Example.com", "Test1234!")
    assert result is user


@pytest.mark.parametrize(
    "session_kwargs, email, password",
    [
        ({"existing": None}, "missing@example.com", "Test1234!"),  # 미존재
    ],
)
def test_authenticate_user_unknown_email_401(
    session_kwargs: dict[str, Any], email: str, password: str
) -> None:
    """미존재 이메일은 401 UNAUTHENTICATED(enumeration 차단)."""
    session = FakeSession(**session_kwargs)
    with pytest.raises(DomainError) as exc_info:
        authenticate_user(session, email, password)
    assert exc_info.value.code is ErrorCode.UNAUTHENTICATED
    assert exc_info.value.status_code == 401


def test_authenticate_user_wrong_password_401() -> None:
    """틀린 비밀번호는 401 UNAUTHENTICATED(미존재와 동일 코드)."""
    session = FakeSession(existing=_user(password="Test1234!"))
    with pytest.raises(DomainError) as exc_info:
        authenticate_user(session, "user@example.com", "WrongPass9!")
    assert exc_info.value.code is ErrorCode.UNAUTHENTICATED


def test_authenticate_user_inactive_account_401() -> None:
    """비활성 계정은 401 UNAUTHENTICATED(자격 증명이 맞아도 거부)."""
    session = FakeSession(existing=_user(password="Test1234!", is_active=False))
    with pytest.raises(DomainError) as exc_info:
        authenticate_user(session, "user@example.com", "Test1234!")
    assert exc_info.value.code is ErrorCode.UNAUTHENTICATED


def test_authenticate_user_corrupt_hash_fail_closed_401() -> None:
    """손상 해시 User는 fail-closed로 401(verify_password가 예외 대신 False)."""
    session = FakeSession(existing=_user(password_hash="not-a-valid-hash"))
    with pytest.raises(DomainError) as exc_info:
        authenticate_user(session, "user@example.com", "Test1234!")
    assert exc_info.value.code is ErrorCode.UNAUTHENTICATED


# ── 토큰 발급(1.8, AC1) ───────────────────────────────────────────────────────
def test_issue_token_pair_stores_hash_not_raw(auth_env: None) -> None:
    """issue_token_pair는 refresh 해시를 add+commit하고 원문은 응답으로만 반환한다."""
    user = _user(role="provider")
    session = FakeSession()
    tokens = issue_token_pair(session, user)

    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.token_type == "bearer"
    assert session.committed is True
    # 정확히 RefreshToken 한 행이 추가되고, 저장된 것은 해시(원문 아님)다.
    stored = [o for o in session.added if isinstance(o, RefreshToken)]
    assert len(stored) == 1
    assert stored[0].token_hash == hash_token(tokens.refresh_token)
    assert stored[0].token_hash != tokens.refresh_token  # 원문 미저장
    assert stored[0].user_id == user.id


# ── 토큰 회전(1.8, AC3) ───────────────────────────────────────────────────────
def test_rotate_token_pair_rotates_and_issues_new(auth_env: None) -> None:
    """유효한 refresh로 기존 행을 삭제(무효화)하고 새 쌍을 발급한다(회전)."""
    user = _user(role="booker")
    raw = create_refresh_token(user.id)
    old_row = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw),
        expires_at=now_utc() + timedelta(days=14),
    )
    session = FakeSession(
        users_by_id={user.id: user},
        tokens_by_hash={hash_token(raw): old_row},
    )

    tokens = rotate_token_pair(session, raw)

    assert old_row in session.deleted  # 기존 refresh 무효화
    new_rows = [o for o in session.added if isinstance(o, RefreshToken)]
    assert len(new_rows) == 1  # 새 행 발급
    assert new_rows[0].token_hash == hash_token(tokens.refresh_token)
    assert session.committed is True


def test_rotate_token_pair_unknown_hash_401(auth_env: None) -> None:
    """DB에 해시가 없으면(로그아웃·이미 회전·위조) 401."""
    user = _user()
    raw = create_refresh_token(user.id)
    session = FakeSession(users_by_id={user.id: user}, tokens_by_hash={})  # 해시 부재
    with pytest.raises(DomainError) as exc_info:
        rotate_token_pair(session, raw)
    assert exc_info.value.code is ErrorCode.UNAUTHENTICATED
    assert session.added == []  # 새 토큰 발급 없음


def test_rotate_token_pair_inactive_user_401(auth_env: None) -> None:
    """행은 있으나 사용자가 비활성이면 401(회전 시 비활성 거부)."""
    user = _user(is_active=False)
    raw = create_refresh_token(user.id)
    old_row = RefreshToken(
        user_id=user.id, token_hash=hash_token(raw), expires_at=now_utc() + timedelta(days=14)
    )
    session = FakeSession(
        users_by_id={user.id: user}, tokens_by_hash={hash_token(raw): old_row}
    )
    with pytest.raises(DomainError) as exc_info:
        rotate_token_pair(session, raw)
    assert exc_info.value.code is ErrorCode.UNAUTHENTICATED


# ── 로그아웃 무효화(1.8, AC4 — 멱등) ──────────────────────────────────────────
def test_revoke_refresh_token_deletes_existing() -> None:
    """존재하는 refresh 해시 행을 삭제하고 commit 한다."""
    raw = "some-raw-refresh"
    row = RefreshToken(
        user_id=uuid.uuid4(), token_hash=hash_token(raw), expires_at=now_utc()
    )
    session = FakeSession(tokens_by_hash={hash_token(raw): row})
    revoke_refresh_token(session, raw)
    assert row in session.deleted
    assert session.committed is True


def test_revoke_refresh_token_none_is_noop() -> None:
    """토큰이 None이면 no-op(멱등 — 삭제·commit 없음)."""
    session = FakeSession()
    revoke_refresh_token(session, None)
    assert session.deleted == []
    assert session.committed is False


def test_revoke_refresh_token_missing_is_noop() -> None:
    """해시 행이 없어도 no-op(멱등 — 만료/위조 토큰도 에러 없이 로그아웃 성공)."""
    session = FakeSession(tokens_by_hash={})
    revoke_refresh_token(session, "nonexistent-token")
    assert session.deleted == []
    assert session.committed is False


# ── 사용자 조회(1.8, /me·회전 공용) ───────────────────────────────────────────
def test_get_user_by_id_found() -> None:
    user = _user()
    session = FakeSession(users_by_id={user.id: user})
    assert get_user_by_id(session, user.id) is user


def test_get_user_by_id_missing_401() -> None:
    session = FakeSession(users_by_id={})
    with pytest.raises(DomainError) as exc_info:
        get_user_by_id(session, uuid.uuid4())
    assert exc_info.value.code is ErrorCode.UNAUTHENTICATED
