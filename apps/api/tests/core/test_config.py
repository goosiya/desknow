"""core.config 단위 테스트.

검증 항목:
  (a) 필수 키 누락 시 ValidationError (fail-fast)
  (b) 모든 필수 키 존재 시 정상 인스턴스화 + 기본값(EMBEDDING_MODEL) 적용
  (c) 진단 출력이 비밀 값을 평문 노출하지 않음(마스킹)
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import (
    OPTIONAL_KEYS,
    REQUIRED_KEYS,
    Settings,
    env_status,
    get_settings,
    mask_secret,
)

# 필수 키 최소 집합(.env 파일 무시하고 환경변수로만 주입)
REQUIRED_ENV = {
    "KAKAO_REST_API_KEY": "kakao-rest-1234567890",
    "KAKAO_JS_KEY": "kakao-js-0987654321",
    "OPENAI_API_KEY": "sk-secretopenaikey1234",
    "DATABASE_URL": "postgresql://dbuser:dbpass@localhost:5432/desknow",
    # JWT_SECRET_KEY는 Story 1.8부터 필수 + 최소 32자(InsecureKeyLengthWarning 방지).
    "JWT_SECRET_KEY": "test-jwt-secret-key-at-least-32-bytes-long-xx",
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """모든 관련 환경변수를 제거해 테스트 격리를 보장한다."""
    for key in REQUIRED_KEYS + OPTIONAL_KEYS:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _settings(**extra) -> Settings:
    # _env_file=None: 실제 .env 파일을 읽지 않고 환경변수만 사용
    return Settings(_env_file=None, **extra)


# (a) 필수 키 누락 시 fail-fast -------------------------------------------------
def test_missing_required_keys_raises_validation_error(monkeypatch):
    # 환경변수가 비어 있는 상태(autouse fixture가 제거)
    with pytest.raises(ValidationError) as exc_info:
        _settings()
    missing = {e["loc"][0] for e in exc_info.value.errors() if e["type"] == "missing"}
    # 기본값 없는 필수 키 3종이 누락으로 보고되어야 함
    assert {"KAKAO_REST_API_KEY", "KAKAO_JS_KEY", "OPENAI_API_KEY"} <= missing


def test_partial_required_keys_still_fails(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_API_KEY", REQUIRED_ENV["KAKAO_REST_API_KEY"])
    with pytest.raises(ValidationError) as exc_info:
        _settings()
    # 남은 누락 키가 정확히 보고되어야 한다(부분 설정 회귀 방지)
    missing = {e["loc"][0] for e in exc_info.value.errors() if e["type"] == "missing"}
    assert "KAKAO_JS_KEY" in missing
    assert "OPENAI_API_KEY" in missing
    assert "KAKAO_REST_API_KEY" not in missing


def test_blank_required_key_rejected(monkeypatch):
    # 모든 필수 키를 채우되 하나를 공백으로 → 누락과 동일하게 fail-fast
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    with pytest.raises(ValidationError):
        _settings()


def test_empty_string_required_key_rejected(monkeypatch):
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("KAKAO_JS_KEY", "")
    with pytest.raises(ValidationError):
        _settings()


# (b) 필수 키 존재 시 정상 인스턴스화 ------------------------------------------
def test_all_required_keys_present_instantiates(monkeypatch):
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    settings = _settings()
    assert settings.KAKAO_REST_API_KEY == REQUIRED_ENV["KAKAO_REST_API_KEY"]
    assert settings.OPENAI_API_KEY == REQUIRED_ENV["OPENAI_API_KEY"]
    # 임베딩 모델 기본값 고정
    assert settings.EMBEDDING_MODEL == "text-embedding-3-small"
    # 선택 키 기본값은 None
    assert settings.ANTHROPIC_API_KEY is None
    # DATABASE_URL은 필수(1.4) — provider의 postgresql:// 스킴이 psycopg3로 정규화된다
    assert settings.DATABASE_URL == (
        "postgresql+psycopg://dbuser:dbpass@localhost:5432/desknow"
    )


# (b-2) DATABASE_URL 필수화 & 스킴 정규화 ------------------------------------
def test_database_url_is_required(monkeypatch):
    # DATABASE_URL을 제외한 필수 키만 설정 → DATABASE_URL 누락이 보고되어야 함
    for k, v in REQUIRED_ENV.items():
        if k != "DATABASE_URL":
            monkeypatch.setenv(k, v)
    with pytest.raises(ValidationError) as exc_info:
        _settings()
    missing = {e["loc"][0] for e in exc_info.value.errors() if e["type"] == "missing"}
    assert "DATABASE_URL" in missing


def test_database_url_blank_rejected(monkeypatch):
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("DATABASE_URL", "   ")
    with pytest.raises(ValidationError):
        _settings()


@pytest.mark.parametrize(
    "raw, expected",
    [
        # postgresql:// → +psycopg 정규화
        (
            "postgresql://u:p@host:5432/desknow",
            "postgresql+psycopg://u:p@host:5432/desknow",
        ),
        # postgres:// (단축형) → +psycopg 정규화
        (
            "postgres://u:p@host:5432/desknow",
            "postgresql+psycopg://u:p@host:5432/desknow",
        ),
        # 이미 +psycopg → 변경 없음(스킴 캐논화만)
        (
            "postgresql+psycopg://u:p@host:5432/desknow",
            "postgresql+psycopg://u:p@host:5432/desknow",
        ),
    ],
)
def test_database_url_scheme_normalized(monkeypatch, raw, expected):
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("DATABASE_URL", raw)
    assert _settings().DATABASE_URL == expected


@pytest.mark.parametrize(
    "raw",
    [
        "mysql://u:p@host:3306/desknow",  # 비-postgres → 거부
        "sqlite:///local.db",  # 비-postgres → 거부
        "host:5432/desknow",  # 스킴 없음 → 거부
    ],
)
def test_database_url_non_postgres_rejected(monkeypatch, raw):
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("DATABASE_URL", raw)
    with pytest.raises(ValidationError):
        _settings()


# (b-3) JWT_SECRET_KEY 필수화 & 최소 길이(Story 1.8) ------------------------
def test_jwt_secret_key_is_required(monkeypatch):
    # JWT_SECRET_KEY를 제외한 필수 키만 설정 → JWT_SECRET_KEY 누락이 보고되어야 함
    for k, v in REQUIRED_ENV.items():
        if k != "JWT_SECRET_KEY":
            monkeypatch.setenv(k, v)
    with pytest.raises(ValidationError) as exc_info:
        _settings()
    missing = {e["loc"][0] for e in exc_info.value.errors() if e["type"] == "missing"}
    assert "JWT_SECRET_KEY" in missing


def test_jwt_secret_key_blank_rejected(monkeypatch):
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("JWT_SECRET_KEY", "   ")
    with pytest.raises(ValidationError):
        _settings()


def test_jwt_secret_key_too_short_rejected(monkeypatch):
    # 32자 미만 → min-length validator가 ValidationError로 거부(InsecureKeyLengthWarning 방지)
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("JWT_SECRET_KEY", "short-secret")  # 12자 < 32
    with pytest.raises(ValidationError):
        _settings()


def test_jwt_secret_key_min_length_accepted(monkeypatch):
    # 정확히 32자는 통과(경계값)
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)
    assert _settings().JWT_SECRET_KEY == "a" * 32


def test_jwt_secret_key_is_masked_in_diagnostics(monkeypatch):
    # JWT_SECRET_KEY는 비밀이므로 진단 출력에 평문 노출되면 안 된다(NON_SECRET_KEYS 제외 확인)
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    settings = _settings()
    status = env_status(settings)
    assert REQUIRED_ENV["JWT_SECRET_KEY"] not in "\n".join(status.values())


def test_embedding_model_overridable(monkeypatch):
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-large")
    assert _settings().EMBEDDING_MODEL == "text-embedding-3-large"


def test_embedding_model_blank_falls_back_to_default(monkeypatch):
    # 빈 값으로 덮어써도 단일 고정 기본값으로 복원
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("EMBEDDING_MODEL", "")
    assert _settings().EMBEDDING_MODEL == "text-embedding-3-small"


# (c) 진단 출력 마스킹 ---------------------------------------------------------
def test_mask_secret_masks_long_value():
    masked = mask_secret("sk-secretopenaikey1234")  # 22자
    assert "secretopenaikey" not in masked
    assert masked.startswith("sk")
    assert masked.endswith("34")


def test_mask_secret_short_value_fully_masked():
    # 12자 이하는 부분 노출 없이 전부 마스킹
    assert mask_secret("short") == "****"
    assert mask_secret("a" * 12) == "****"


def test_mask_secret_boundary_at_13(monkeypatch):
    # 13자(임계값 초과)부터 앞2…뒤2만 노출
    masked = mask_secret("a" * 9 + "bcdz")  # 13자, 끝 'dz'
    assert masked == "aa…dz"


def test_mask_secret_handles_empty_and_whitespace():
    assert mask_secret(None) == "(미설정)"
    assert mask_secret("") == "(미설정)"
    assert mask_secret("   ") == "(미설정)"


def test_env_status_does_not_leak_secret(monkeypatch):
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    settings = _settings()
    status = env_status(settings)
    blob = "\n".join(f"{k}={v}" for k, v in status.items())
    # 비밀 값 전체가 진단 출력에 평문으로 나타나면 안 됨
    assert REQUIRED_ENV["OPENAI_API_KEY"] not in blob
    assert REQUIRED_ENV["KAKAO_REST_API_KEY"] not in blob
    # EMBEDDING_MODEL은 비밀이 아니므로 전체 표시 허용
    assert status["EMBEDDING_MODEL"] == "text-embedding-3-small"


def test_get_settings_is_cached(monkeypatch):
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    assert get_settings() is get_settings()


def test_get_settings_recovers_after_fix(monkeypatch, tmp_path):
    # .env 없는 디렉터리에서 시작 → 필수 키 없음 → ValidationError(예외는 캐시 안 됨)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()
    # 환경을 보정하면 동일 호출이 정상 로드되어야 한다(예외 캐시되지 않음)
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    assert get_settings().OPENAI_API_KEY == REQUIRED_ENV["OPENAI_API_KEY"]
    get_settings.cache_clear()


def test_key_lists_match_model_fields():
    # 진단 목록과 모델 필드가 정확히 일치해야 silent drift가 없다
    assert set(REQUIRED_KEYS) | set(OPTIONAL_KEYS) == set(Settings.model_fields)
