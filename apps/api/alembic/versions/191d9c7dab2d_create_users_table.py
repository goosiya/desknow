"""create users table

Revision ID: 191d9c7dab2d
Revises: 124a50c37b8c
Create Date: 2026-06-15 10:07:03.153477

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # autogenerate가 sqlmodel.sql.sqltypes.* 타입을 렌더할 때 NameError 방지


# revision identifiers, used by Alembic.
revision: str = '191d9c7dab2d'
down_revision: Union[str, Sequence[str], None] = '124a50c37b8c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """users 테이블 생성(첫 도메인 테이블 — Story 1.7).

    제약명은 SQLModel.metadata 네이밍 규약(1.4)이 부여한다: PK=pk_users,
    UNIQUE=uq_users_email(이메일 중복 차단의 진실의 원천). created_at은
    timestamptz(*_at = UTC 규약).
    """
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(length=320), nullable=False),
        sa.Column("password_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("role", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )


def downgrade() -> None:
    """users 테이블 제거(왕복 가능)."""
    op.drop_table("users")
