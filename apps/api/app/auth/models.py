"""auth 도메인 ORM 모델: ``User`` + ``UserRole`` (Story 1.7).

``users``는 **첫 도메인 테이블**이다 — Story 1.4가 깐 네이밍 규약(``uq_users_email``·
``pk_users``)과 Alembic autogenerate 파이프라인을 처음 실증한다.

**규약(아키텍처 §Naming Patterns L228-241):**

- **테이블 ``users``**(복수 snake_case). ``email``의 ``unique=True``는 1.4 네이밍 규약에 의해
  ``uq_users_email``로 자동 생성되며, **이 UNIQUE 제약이 이메일 중복 차단의 진실의 원천**이다
  (서비스 선검사는 친절한 메시지, UNIQUE는 경합 안전망 — defense-in-depth).
- **``created_at``** = ``*_at`` 규약상 UTC ``timestamptz``. ``Column(DateTime(timezone=True))`` +
  ``default_factory=now_utc``(Story 1.5 단일 출처 — ``datetime.now()`` 직접 호출 금지).
- **``password_hash``**(평문 ``password`` 절대 아님, NFR-6). Argon2 해시만 저장한다.
- **``is_active``**는 계정 본연의 속성이다. Story 1.8 로그인이 비활성 계정을 거부하고
  Epic 8(FR-31)이 비활성화에 사용한다 — 지금 포함해 즉시 후속 마이그레이션을 피한다
  (가입은 항상 ``True``로 시작).

스키마는 Alembic이 단독 소유한다(``SQLModel.metadata.create_all`` 금지 — 1.4 규약).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Uuid
from sqlmodel import Field, SQLModel

from app.core.time import now_utc


class UserRole(StrEnum):
    """사용자 역할. 가입(register)으로는 ``booker``/``provider``만 생성 가능하다."""

    BOOKER = "booker"
    PROVIDER = "provider"
    ADMIN = "admin"  # 시드 전용 — 가입으로는 생성 불가(스키마에서 차단)


class User(SQLModel, table=True):
    """사용자 계정(첫 도메인 테이블). 가입·로그인(1.8)·RBAC·비활성화(E8)의 기반.

    **``__table_args__`` role CHECK(Story 2.2 P3 회수):** ``role``은 1.7이 자유 문자열로
    도입했다(가입 스키마 ``Literal``이 1차 차단). 쓰기 경로가 늘어난 지금 ``role IN
    ('booker','provider','admin')`` DB CHECK로 최종 강제한다(시드 admin 포함 3종 허용 —
    가입은 booker/provider만, admin은 시드 전용이나 DB는 셋 다 허용). ck 규약이 접두하므로
    ``name``엔 접미사만 → 최종명 ``ck_users_role``. ``rooms.room_type`` CHECK와 한데 묶어
    회수한다(P3).
    """

    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # unique=True → uq_users_email(1.4 규약 자동 생성). PG는 UNIQUE에 인덱스를 자동 생성하므로
    # 별도 index=True 불필요. 이 제약이 중복가입 차단의 진실의 원천이다.
    email: str = Field(unique=True, max_length=320)
    password_hash: str  # ⚠️ Argon2 해시만 — 평문 password 절대 저장 금지(NFR-6)
    role: str  # UserRole 값(가입은 booker/provider, admin은 시드 전용; DB CHECK가 최종 강제)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(
        default_factory=now_utc,  # core/time 단일 출처(datetime.now() 직접 호출 금지)
        sa_column=Column(DateTime(timezone=True), nullable=False),  # *_at = UTC timestamptz
    )

    __table_args__ = (
        # P3 회수 — role 자유 문자열에 DB CHECK(defense-in-depth). ck 규약 접두 → ck_users_role.
        CheckConstraint("role IN ('booker', 'provider', 'admin')", name="role"),
    )


class RefreshToken(SQLModel, table=True):
    """리프레시 토큰의 **해시**를 보관하는 테이블(Story 1.8 — 두 번째 도메인 테이블·첫 FK).

    원문이 아니라 ``token_hash``(sha256 hex 64자)만 저장한다(DB 유출 내성). 로그인·회전 시
    행을 생성하고, 로그아웃·회전 시 행을 삭제(즉시 무효화)한다. 검증은 JWT 디코드(stateless)
    + 이 테이블 해시 조회(stateful)의 이중이다.

    제약명은 1.4 ``NAMING_CONVENTION``이 자동 부여한다(손으로 짓지 않는다): PK
    ``pk_refresh_tokens``, FK ``fk_refresh_tokens_user_id_users``, UNIQUE
    ``uq_refresh_tokens_token_hash``, INDEX ``idx_refresh_tokens_user_id``.
    """

    __tablename__ = "refresh_tokens"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid(),
            # SQLModel foreign_key= 단축형은 ondelete 미지원 → 명시 Column(ForeignKey(...)).
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,  # idx_refresh_tokens_user_id — 사용자별 조회/CASCADE 보조
        ),
    )
    # sha256 hex(정확히 64자) → uq_refresh_tokens_token_hash. 조회 키이자 회전/로그아웃 삭제 대상.
    token_hash: str = Field(unique=True, max_length=64)
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),  # *_at = UTC timestamptz
    )
    created_at: datetime = Field(
        default_factory=now_utc,  # core/time 단일 출처(datetime.now() 직접 호출 금지)
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
