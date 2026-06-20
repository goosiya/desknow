"""add reservations.slot_starts snapshot column

Revision ID: f1a2b3c4d5e6
Revises: d8afe1726e81
Create Date: 2026-06-17 10:00:00.000000

Story 4.8 — 예약현황/히스토리(예약자)를 위한 **슬롯 시작시각 스냅샷** 컬럼을 추가한다(범위 결정 #1).

- **문제:** ``reservation_slots`` 점유 행은 취소/거절 시 DELETE된다(FULL UNIQUE 불변식의 근거 —
  활성 점유만 잔존). 그 결과 종료 상태(cancelled/rejected) 예약은 점유 행이 0건이 되어 **원래
  예약 시간 정보가 사라진다**. 예약현황 히스토리는 "지난(이용 완료/취소/거절)" 예약의 날짜·시간을
  모두 표시해야 하므로 시간 정보가 필요하다.
- **해법:** ``reservations``에 **표시 전용 immutable 스냅샷** 컬럼 ``slot_starts``(JSON, UTC ISO
  ``...Z`` 문자열 오름차순)를 추가한다. ``create_reservation``이 생성 시 1회 기록하고 취소/거절
  전이는 건드리지 않는다(히스토리 보존). **점유의 진실의 원천(``reservation_slots``)·4.9 차감
  불변식은 그대로 유지**한다(스냅샷은 ``derive_slots``/가용성 집계에 절대 미사용 — 표시 전용).

**백필(NOT NULL 신규 컬럼 — 기존 행 처리):**

- ⓐ nullable + ``server_default '[]'`` 로 추가(기존 행에 즉시 ``[]`` 채움).
- ⓑ **confirmed 예약** = ``reservation_slots``에 점유 행이 잔존하므로 그 ``slot_start``를 모아
  ISO ``...Z`` 오름차순으로 백필한다(``isoformat_utc`` 단일 출처 재사용 — 와이어와 동일 포맷).
- ⓒ **이미 취소/거절된 레거시 행** = 점유 행 0건 → ``[]`` 유지(시간 정보 이미 소실 — AC1
  "스냅샷 도입 이전 레거시는 시간 미표시 허용"). 라이브 Supabase엔 4.5/4.7 dev 예약이 있을 수
  있어 백필을 실측한다.
- ⓓ 백필 후 ``NOT NULL`` 강제(``server_default '[]'`` 유지 = 향후 누락 INSERT 방어).

**라이브 DB 적용:** down_revision = 현재 head ``d8afe1726e81``. dev 완료 시 라이브 Supabase에
``uv run alembic upgrade head``를 실제 실행한다(메모 dev-workflow-policy-live-db-migration —
백필 왕복 무결성 확인). 이 마이그레이션은 PostgreSQL에서만 실행된다(테스트 skipif + 라이브).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'd8afe1726e81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """slot_starts 스냅샷 컬럼 추가 + confirmed 예약 백필 + NOT NULL 강제."""
    # ⓐ nullable + server_default '[]' 로 추가(기존 행 즉시 [] — NOT NULL 충돌 회피).
    op.add_column(
        "reservations",
        sa.Column(
            "slot_starts",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'[]'"),  # postgres가 unknown 리터럴을 json으로 캐스트
        ),
    )

    # ⓑ confirmed 예약 백필 — reservation_slots의 잔존 점유 행에서 slot_start를 모아 ISO ...Z
    #    오름차순 스냅샷으로 채운다. 날짜 포맷을 SQL 방언에 의존하지 않고 isoformat_utc(앱 단일
    #    출처)로 Python에서 만들어 와이어와 바이트 동일성을 보장한다(timestamptz → psycopg aware
    #    datetime → isoformat_utc). 취소/거절 레거시 행은 점유 0건이라 여기 안 잡혀 [] 유지(ⓒ).
    from app.core.time import isoformat_utc

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT reservation_id, slot_start FROM reservation_slots "
            "ORDER BY reservation_id, slot_start"
        )
    ).all()
    grouped: dict = {}
    for reservation_id, slot_start in rows:
        grouped.setdefault(reservation_id, []).append(slot_start)
    for reservation_id, starts in grouped.items():
        snapshot = sorted(isoformat_utc(s) for s in starts)
        bind.execute(
            sa.text(
                "UPDATE reservations SET slot_starts = :snapshot WHERE id = :id"
            ).bindparams(
                sa.bindparam("snapshot", snapshot, type_=sa.JSON()),
                sa.bindparam("id", reservation_id),
            )
        )

    # ⓓ 백필 후 NOT NULL 강제(server_default '[]'는 유지 — 향후 누락 INSERT 방어).
    op.alter_column("reservations", "slot_starts", nullable=False)


def downgrade() -> None:
    """slot_starts 컬럼 제거(스냅샷 데이터 소실 — 표시 전용이라 무해)."""
    op.drop_column("reservations", "slot_starts")
