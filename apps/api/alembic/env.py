"""Alembic 마이그레이션 환경 (Story 1.4).

- DB URL은 ``alembic.ini``에 하드코딩하지 않고 ``app.core.config``의 settings에서
  주입한다(비밀이 ini에 박히지 않게 한다).
- ``import app.core.db``로 네이밍 규약 등록을 보장하고 ``target_metadata``를
  ``SQLModel.metadata``로 설정한다 → autogenerate가 후속 스토리 모델을 인식한다.
- **모델 import 허브**: 후속 스토리는 아래 표시된 위치에서 ``app/{domain}/models.py``를
  import 한다(Story 1.7부터 ``app.auth`` 모델을 등록 — 아래 import 허브 참조).
"""
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

import app.core.db  # noqa: F401 — import만으로 SQLModel.metadata 네이밍 규약을 등록한다
from alembic import context
from app.core.config import get_settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# autogenerate 대상 메타데이터. SQLModel.metadata가 스키마의 원천이다.
target_metadata = SQLModel.metadata


def _database_url() -> str:
    """settings에서 DB URL을 직접 읽는다(configparser 우회 — 비밀 보호 + ``%`` 함정 회피).

    ini 하드코딩 대신 settings에서 주입한다(비밀이 ini에 박히지 않게 한다). 단,
    ``set_main_option``/``get_main_option`` 경유는 금물 — Alembic의 ``Config``는
    configparser(BasicInterpolation) 백엔드라, 비밀번호에 포함된 **raw ``%``**
    (URL 인코딩된 비밀번호, 예 ``%40``=``@``)가 ``InterpolationSyntaxError``를 일으켜
    모든 alembic 명령이 깨진다(Alembic은 ``%``를 이스케이프하지 않는다 — config.py
    docstring 명시). 따라서 URL을 configparser에 넣지 않고 엔진/컨텍스트에 직접 전달한다.

    *지연 호출*(import 시점 아님)이라, ``env.py`` import 자체는 ``DATABASE_URL`` 없이도
    안전하다(실제 마이그레이션 실행 시점에만 settings를 로드한다).
    """
    return get_settings().DATABASE_URL

# ── 모델 import 허브 (후속 스토리) ──────────────────────────────────────────
# 후속 스토리는 도메인 모델을 여기서 import 해 autogenerate가 인식하게 한다.
# (주의: 실제 도메인 모듈은 app.auth 등 — 위 예시 주석의 app.users는 placeholder였다.)
from app.auth import models as _auth_models  # noqa: F401 — User를 SQLModel.metadata에 등록(1.7)
from app.chatbot import models as _chatbot_models  # noqa: F401 — DocumentChunk 등록(7.2)
from app.favorites import models as _favorites_models  # noqa: F401 — Favorite 등록(3.7)
from app.notifications import models as _notifications_models  # noqa: F401 — Notification 등록(5.1)
from app.reservations import models as _reservations_models  # noqa: F401 — Reservation 2종 등록(4.1)
from app.reviews import models as _reviews_models  # noqa: F401 — Review·ReviewReply 등록(5.5/5.6)
from app.rooms import models as _rooms_models  # noqa: F401 — Room 외 2종 등록(2.1)
# ────────────────────────────────────────────────────────────────────────────


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # ini 섹션을 가져오되, 비밀 URL은 configparser를 거치지 않고 dict에 직접 주입한다
    # (raw `%` 비밀번호가 BasicInterpolation에서 깨지는 것을 방지 — _database_url 참고).
    configuration = dict(config.get_section(config.config_ini_section, {}))
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=False,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
