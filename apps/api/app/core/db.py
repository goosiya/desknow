"""데이터베이스 엔진·세션·연결 검증 (Story 1.4).

- **네이밍 규약**을 ``SQLModel.metadata``에 등록한다(AC3). 모델 정의 *이전*(import
  시점)에 설정해야 이후 스토리(1.7 users, 2.1 rooms, 4.1 reservations 등)의 제약명이
  규약을 자동으로 따른다.
- **엔진은 지연 생성**한다(``get_engine`` + ``lru_cache``). import 시점이 아니라 첫
  사용 시점에 ``DATABASE_URL``을 읽으므로, ``app.main``을 import만 하는 도구·테스트
  (예: ``tests/test_main.py``)는 DB 설정 없이도 안전하다(1.2의 test_main 패턴 보존).
- **스키마는 Alembic이 단독 소유**한다(AC2). 이 모듈은 ``SQLModel.metadata.create_all``을
  **절대 호출하지 않는다** — 테이블 생성은 마이그레이션만의 책임이다.
- ``verify_db_connection()``: 기동 시 연결(``SELECT 1``)과 pgvector 확장 존재를
  검증하고, 실패 시 한국어 actionable 오류로 fail-fast 한다(AC1).
"""
from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings

# 네이밍 규약(AC3) — 아키텍처 §Naming Patterns(uq_{table}_{cols}, idx_{table}_{cols})에 정렬.
# SQLAlchemy 기본 인덱스 접두사 ix_ 대신 idx_로 오버라이드한다.
# 모델 정의 이전(import 시점)에 등록해야 이후 모든 마이그레이션이 자동으로 따른다.
NAMING_CONVENTION = {
    "ix": "idx_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
SQLModel.metadata.naming_convention = NAMING_CONVENTION


class DatabaseConnectionError(RuntimeError):
    """DB 연결/확장 검증 실패를 사람이 읽을 수 있는 한국어 오류로 감싼다.

    raw ``OperationalError`` 스택만 노출하는 대신 어떤 호스트인지·무엇을 확인할지
    안내한다(비밀번호는 노출하지 않는다). 원본 예외는 ``__cause__``로 보존된다.
    """


@lru_cache
def get_engine() -> Engine:
    """프로세스 단일 SQLModel/SQLAlchemy 엔진(지연 생성).

    MVP는 동기 엔진(psycopg3 드라이버)이다 — 아키텍처가 async를 요구하지 않는다.
    ``pool_pre_ping``으로 끊긴 커넥션을 재사용 전에 걸러낸다.
    """
    settings = get_settings()
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=False)


def get_session() -> Iterator[Session]:
    """FastAPI 의존성: 요청 범위 세션.

    후속 스토리의 라우터가 ``session: Session = Depends(get_session)``로 사용한다.
    """
    with Session(get_engine()) as session:
        yield session


def violated_constraint(exc: IntegrityError) -> str | None:
    """``IntegrityError``에서 위반된 DB 제약 이름을 추출한다(Story 2.2 — P2 회수).

    psycopg3는 ``exc.orig``(원본 ``psycopg.errors.IntegrityError`` 계열)에 ``diag``
    진단 객체를 달고, 그 ``constraint_name``이 위반된 제약명(예 ``uq_rooms_provider_id``·
    ``uq_users_email``)이다. 이 헬퍼로 서비스가 **제약명을 식별해 선별 변환**한다 —
    포괄 ``except IntegrityError → 단일 도메인 에러``(과대캐치)는 무관한 제약 위반까지
    잘못된 코드로 둔갑시키므로 금지한다(회고 P2). 제약명을 못 얻으면(``orig``/``diag``
    부재, 비-psycopg 드라이버) ``None`` → 호출처는 안전하게 re-raise 한다.

    드라이버 비의존: ``getattr`` 체인으로 ``orig``/``diag``/``constraint_name`` 부재를
    모두 흡수한다(테스트는 가짜 ``orig.diag.constraint_name``으로 분기를 실증).
    """
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", None) if diag is not None else None


def verify_db_connection() -> None:
    """기동 시 DB 연결과 pgvector 확장 존재를 검증한다(AC1).

    - ``SELECT 1``로 연결을 확인한다. 실패 시 호스트·점검 항목을 담은 한국어 오류로
      래핑해 fail-fast 한다(비밀번호 노출 금지).
    - pgvector 확장(``vector``) 존재를 확인한다. 미존재 시 베이스라인 마이그레이션을
      먼저 적용하라는 actionable 오류를 던진다(확장 활성화는 Alembic이 소유 — AC1 결정).
    """
    engine = get_engine()
    host = engine.url.host or "(unknown)"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            has_vector = conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            ).first()
    except SQLAlchemyError as exc:
        raise DatabaseConnectionError(
            f"데이터베이스에 연결할 수 없습니다 (host={host}). "
            "DATABASE_URL과 DB 가동 상태를 확인하세요 "
            "(Supabase는 5432 포트=직접 연결/Session pooler 사용, 6543 금지)."
        ) from exc

    if has_vector is None:
        raise DatabaseConnectionError(
            f"pgvector 확장이 활성화되어 있지 않습니다 (host={host}). "
            "`uv run alembic upgrade head`를 먼저 실행해 베이스라인 마이그레이션을 "
            "적용하세요(확장 활성화는 베이스라인 마이그레이션이 소유합니다)."
        )
