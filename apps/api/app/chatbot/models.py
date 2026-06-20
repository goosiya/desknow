"""chatbot 도메인 ORM 모델: ``DocumentChunk`` (Story 7.2).

문서 RAG(7.5)의 **데이터 계층 인프라**다. ``docs_corpus/`` 문서를 청크로 쪼개 OpenAI
``text-embedding-3-small``로 임베딩한 결과를 pgvector 컬럼에 멱등 적재하기 위한 단일 테이블.

**설계 결정(Dev Notes §멱등 전략):**

- **멱등 단위 = 문서(파일)**. 문서 전체 내용의 sha256(``content_hash``)을 각 청크 행에
  denormalize 저장한다. 재인제스트 시 ``source_path`` 기준 기존 해시와 대조해, 같으면 임베딩·
  적재를 모두 스킵(OpenAI 호출 0), 다르면 기존 청크를 전부 삭제 후 재적재(stale 벡터 0).
- ``(source_path, chunk_index)`` 복합 UNIQUE가 중복/동시 INSERT를 스키마에서도 막는다
  (멱등 이중 방어). 명시 단축명 ``uq_document_chunks_source_path_chunk_index``(회고 P1,
  42자 ≤63 ✓ — notifications 선례).
- **단일 테이블 + denormalized ``content_hash``**로 충분하다(부분실패 식별·멱등 모두 만족).
  ``documents`` 부모 테이블 분리(2테이블 정규화)는 과설계 — 후속 필요 시(Dev Notes §대안).

**규약:**

- 테이블 복수 snake_case(``document_chunks``). 단일 제약(PK)·``source_path`` 조회 인덱스는
  1.4 ``NAMING_CONVENTION``(``app/core/db.py``)이 자동 부여한다(PK ``pk_document_chunks``,
  INDEX ``idx_document_chunks_source_path``). 복합 UNIQUE만 명시 단축명.
- 벡터 컬럼은 ``pgvector.sqlalchemy.Vector`` 타입(런타임 의존성 ``pgvector>=0.4.2`` 보유).
  raw SQL DDL을 손코딩하지 않는다 — 모델은 ``Vector(1536)``, DDL은 Alembic이 소유.
- ``created_at`` = ``*_at`` 규약상 UTC ``timestamptz``(``core/time.now_utc`` 단일 출처).

스키마는 Alembic이 단독 소유한다(``SQLModel.metadata.create_all`` 금지 — 1.4 규약).
HNSW 인덱스(``vector_cosine_ops``)는 autogenerate가 못 만들므로 마이그레이션에서 수기 추가한다.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.time import now_utc

# 임베딩 차원(text-embedding-3-small 고정). 코드 상수가 맞다 — 모델을 1536이 아닌 차원의 모델로
# 교체하면 적재가 깨지므로, 교체는 **전체 재임베딩 + 차원 변경 마이그레이션**을 동반한다
# (architecture L132 "교체 시 전체 재임베딩"). 따라서 설정값이 아니라 불변 상수로 둔다.
EMBEDDING_DIM = 1536


class DocumentChunk(SQLModel, table=True):
    """문서 한 청크 + 그 임베딩 벡터(문서×청크 1행).

    제약명: PK ``pk_document_chunks``는 1.4 규약 자동, ``source_path`` 조회 인덱스
    ``idx_document_chunks_source_path``는 ``index=True``로 자동. 복합 UNIQUE만 명시
    단축명 ``uq_document_chunks_source_path_chunk_index``(이중접두 함정 없는 단순 UNIQUE).
    """

    __tablename__ = "document_chunks"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # docs_corpus/ 기준 상대 경로(POSIX). 문서 식별자이자 멱등/삭제 단위. 조회 인덱스 자동.
    source_path: str = Field(
        nullable=False,
        index=True,  # idx_document_chunks_source_path — 해시 대조·멱등 DELETE 조회
    )
    # 문서 파일 전체 내용의 sha256(hexdigest). 문서 단위 멱등 기준(같은 source_path의 모든
    # 청크 행에 동일 값으로 denormalize 저장 — 재인제스트 시 1행만 읽어 대조한다).
    content_hash: str = Field(nullable=False)
    # 문서 내 청크 순서(0부터). (source_path, chunk_index) 복합 UNIQUE의 한 축.
    chunk_index: int = Field(nullable=False)
    content: str = Field(nullable=False)  # 청크 원문(7.5 RAG 근거 텍스트로 노출)
    # pgvector 벡터 컬럼. sa_column으로 Vector 타입을 명시한다(list[float] 어노테이션은
    # pydantic 검증용, 실제 DB 타입은 Vector(1536)). DDL/인덱스는 Alembic이 소유.
    embedding: list[float] = Field(
        sa_column=Column(Vector(EMBEDDING_DIM), nullable=False),
    )
    created_at: datetime = Field(
        default_factory=now_utc,  # core/time 단일 출처(datetime.now() 직접 호출 금지)
        sa_column=Column(DateTime(timezone=True), nullable=False),  # *_at = UTC timestamptz
    )

    __table_args__ = (
        # 복합 UNIQUE — 명시 단축명(회고 P1, 42자 ≤63). 한 문서의 같은 순번 청크는 1행:
        # 멱등 DELETE→INSERT가 중복 INSERT/동시 적재로 깨지지 않게 스키마에서도 강제한다.
        UniqueConstraint(
            "source_path",
            "chunk_index",
            name="uq_document_chunks_source_path_chunk_index",
        ),
    )
