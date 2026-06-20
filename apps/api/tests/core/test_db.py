"""core.db 단위 테스트 (Story 1.4 — 라이브 DB 불필요).

검증 항목:
  (a) 네이밍 규약이 SQLModel.metadata에 규약대로 등록됨(AC3)
  (b) verify_db_connection이 연결 실패를 명확한 한국어 오류로 래핑(AC1)
  (c) pgvector 확장 미존재 시 actionable 오류(AC1)
  (d) 정상 연결 + 확장 존재 시 예외 없음

참고: URL 스킴 정규화는 config의 검증기가 소유하므로 test_config.py에서 검증한다.
라이브 DB는 쓰지 않고 엔진을 가짜로 주입(monkeypatch)해 오류 경로만 검증한다.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError
from sqlmodel import SQLModel

from app.core import db


# (a) 네이밍 규약 등록 ----------------------------------------------------------
def test_naming_convention_registered():
    nc = SQLModel.metadata.naming_convention
    for key in ("ix", "uq", "ck", "fk", "pk"):
        assert key in nc, f"네이밍 규약에 '{key}' 키가 없습니다"
    # 아키텍처 규약: 인덱스는 idx_, UNIQUE는 uq_ (SQLAlchemy 기본 ix_ 오버라이드)
    assert nc["ix"].startswith("idx_")
    assert nc["uq"].startswith("uq_")
    assert nc["fk"].startswith("fk_")
    assert nc["pk"].startswith("pk_")
    assert nc["ck"].startswith("ck_")


# 가짜 엔진/커넥션 — 라이브 DB 없이 verify_db_connection 경로를 구동한다 ----------
class _FakeURL:
    host = "db.example.com"


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FailingEngine:
    """connect() 자체가 OperationalError를 던지는 엔진(연결 실패 시뮬레이션)."""

    url = _FakeURL()

    def connect(self):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))


class _Conn:
    def __init__(self, has_vector: bool):
        self._has_vector = has_vector

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, clause):
        if "pg_extension" in str(clause):
            return _FakeResult((1,) if self._has_vector else None)
        return _FakeResult((1,))


class _Engine:
    """정상 연결 엔진. has_vector로 확장 존재 여부를 제어한다."""

    url = _FakeURL()

    def __init__(self, has_vector: bool):
        self._has_vector = has_vector

    def connect(self):
        return _Conn(self._has_vector)


# (b) 연결 실패 래핑 ------------------------------------------------------------
def test_verify_db_connection_wraps_connection_error(monkeypatch):
    monkeypatch.setattr(db, "get_engine", lambda: _FailingEngine())
    with pytest.raises(db.DatabaseConnectionError) as exc_info:
        db.verify_db_connection()
    msg = str(exc_info.value)
    # 어떤 호스트인지·무엇을 확인할지 안내(단 비밀번호는 노출하지 않는다)
    assert "db.example.com" in msg
    assert "DATABASE_URL" in msg
    assert "connection refused" not in msg  # 원인은 __cause__로만, 메시지엔 노출 안 함
    # 원본 예외는 체인으로 보존되어야 한다
    assert isinstance(exc_info.value.__cause__, OperationalError)


# (c) pgvector 확장 미존재 ------------------------------------------------------
def test_verify_db_connection_missing_pgvector(monkeypatch):
    monkeypatch.setattr(db, "get_engine", lambda: _Engine(has_vector=False))
    with pytest.raises(db.DatabaseConnectionError) as exc_info:
        db.verify_db_connection()
    assert "alembic upgrade head" in str(exc_info.value)


# (d) 정상 경로 — 예외 없음 -----------------------------------------------------
def test_verify_db_connection_ok(monkeypatch):
    monkeypatch.setattr(db, "get_engine", lambda: _Engine(has_vector=True))
    # 예외가 발생하지 않아야 한다
    db.verify_db_connection()
