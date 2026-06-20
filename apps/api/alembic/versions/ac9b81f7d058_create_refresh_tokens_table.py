"""create refresh_tokens table

Revision ID: ac9b81f7d058
Revises: 191d9c7dab2d
Create Date: 2026-06-15 11:11:16.713137

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # autogenerate가 sqlmodel.sql.sqltypes.* 타입을 렌더할 때 NameError 방지


# revision identifiers, used by Alembic.
revision: str = 'ac9b81f7d058'
down_revision: Union[str, Sequence[str], None] = '191d9c7dab2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """refresh_tokens 테이블 생성(두 번째 도메인 테이블·첫 FK — Story 1.8).

    제약명은 SQLModel.metadata 네이밍 규약(1.4)이 부여한다: PK=pk_refresh_tokens,
    FK=fk_refresh_tokens_user_id_users(→users.id, CASCADE), UNIQUE=uq_refresh_tokens_token_hash,
    INDEX=idx_refresh_tokens_user_id. token_hash는 원문이 아니라 sha256 해시(64자)다.
    *_at은 timestamptz(UTC 규약).
    """
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_refresh_tokens_user_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("idx_refresh_tokens_user_id", "refresh_tokens", ["user_id"])


def downgrade() -> None:
    """refresh_tokens 테이블 제거(왕복 가능)."""
    op.drop_index("idx_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
