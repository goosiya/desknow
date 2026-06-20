"""baseline: enable pgvector extension

Revision ID: 124a50c37b8c
Revises: 
Create Date: 2026-06-15 02:11:21.205085

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # autogenerate가 sqlmodel.sql.sqltypes.* 타입을 렌더할 때 NameError 방지


# revision identifiers, used by Alembic.
revision: str = '124a50c37b8c'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """베이스라인: pgvector 확장만 활성화한다(도메인 테이블 생성 없음 — AC2).

    확장 활성화는 이 마이그레이션이 단일 출처로 소유한다(최소권한: 런타임 롤이
    CREATE EXTENSION 권한을 가질 필요가 없다). 후속 스토리가 테이블을 점진 추가한다.
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """확장을 제거한다(왕복 가능). 벡터 컬럼이 존재하면 PostgreSQL이 거부하므로,
    역순(후속 마이그레이션 먼저 downgrade)이 보장된 상태에서만 안전하다."""
    op.execute("DROP EXTENSION IF EXISTS vector")
