"""add rooms address column

Revision ID: f1ba2a78986a
Revises: 7a6edff2b9ef
Create Date: 2026-06-19 00:26:08.053086

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # autogenerate가 sqlmodel.sql.sqltypes.* 타입을 렌더할 때 NameError 방지


# revision identifiers, used by Alembic.
revision: str = 'f1ba2a78986a'
down_revision: Union[str, Sequence[str], None] = '7a6edff2b9ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # rooms.address 표시용 주소 컬럼만 추가한다(nullable — 기존 행은 null).
    # ★autogenerate가 끼워넣은 `drop_index idx_document_chunks_embedding_hnsw`는 제거했다 —
    #   이 HNSW 벡터 인덱스는 raw SQL(document_chunks 마이그레이션)로 만들어 모델 메타데이터에
    #   없어 매 autogenerate마다 "삭제 대상"으로 오탐된다. 실제로 drop하면 RAG 유사도 검색이
    #   풀스캔으로 퇴화하므로 절대 떨어뜨리지 않는다(메모리: alembic autogenerate 함정).
    op.add_column(
        'rooms',
        sa.Column('address', sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('rooms', 'address')
