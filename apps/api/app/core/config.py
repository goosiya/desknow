"""애플리케이션 설정 로딩 및 환경 점검 (Story 1.1).

pydantic-settings 기반 ``Settings``를 정의한다.
- **필수 키**는 기본값 없는 필드로 선언 → ``.env``/환경변수에 없으면 인스턴스 생성 시
  ``ValidationError``가 발생하여 **자연스러운 fail-fast**가 된다(AC 4).
- **선택 키**는 ``Optional`` + 기본값 ``None`` (미설정 시에도 기동 정상, AC 5).
- ``get_settings()``: ``@lru_cache`` 싱글톤 접근자. Story 1.2의 ``main.py``가 이를 호출하면
  앱 기동 시점에 동일한 fail-fast가 연결된다.
- ``--check`` CLI: 키 **존재 여부만** 마스킹하여 출력(비밀 값 평문 노출 금지, AC 5).

참고: 키 발급/설정 가이드는 ``docs/external-services-setup.md``.
"""
from __future__ import annotations

import argparse
import sys
from functools import lru_cache

from pydantic import ValidationError, field_validator
from pydantic_core import ErrorDetails
from pydantic_settings import BaseSettings, SettingsConfigDict

# 임베딩 모델 기본값(단일 고정). 빈 값으로 덮어써지면 이 값으로 복원한다.
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"

# LLM 프로바이더/모델 기본값(Story 7.1). 빈 값으로 덮어써지면 이 값으로 복원한다.
# 기준 프로바이더=OpenAI(≤2초 SLA, OPENAI_API_KEY 필수). LLM_MODEL은 기준 OpenAI 모델 id다.
# 모델 id는 시점에 따라 바뀌므로(지식 컷오프 주의) 설정값으로 둬 배포 시 현행 id로 교체한다.
DEFAULT_LLM_PROVIDER = "openai"
DEFAULT_LLM_MODEL = "gpt-4o-mini"

# 비밀 값이 아니라 누락 시 빈 문자열을 거부하지 않고 기본값으로 복원하는 키
# (의미상 필수지만 기본값이 있어 fail-fast 대상이 아니다 — 진단에서 별도 표기).
DEFAULTED_KEYS: set[str] = {"EMBEDDING_MODEL"}

# 진단 출력에서 다룰 키 목록 (표시 순서)
REQUIRED_KEYS: list[str] = [
    "KAKAO_REST_API_KEY",
    "KAKAO_JS_KEY",
    "OPENAI_API_KEY",
    "DATABASE_URL",
    "EMBEDDING_MODEL",
    "JWT_SECRET_KEY",
]

# JWT 서명 키 최소 길이(바이트). PyJWT 2.13은 HS256 키가 32바이트 미만이면
# InsecureKeyLengthWarning을 내며 RFC 7518 §3.2를 위반한다 → 약한 키를 기동 시점에 막는다.
JWT_SECRET_MIN_LENGTH = 32
OPTIONAL_KEYS: list[str] = [
    "ANTHROPIC_API_KEY",
    "GOOGLE_AI_API_KEY",
    "KAKAO_NATIVE_APP_KEY",
    # LLM 선택 설정(Story 7.1) — 비밀 아님·기본값 보유. 미설정 시에도 기준(OpenAI)으로 정상 기동.
    "LLM_PROVIDER",
    "LLM_MODEL",
    # 시드 관리자 부트스트랩(Story 8.1) — scripts/seed_admin.py 전용·앱 기동 무관(fail-fast 아님).
    # 비밀/식별정보라 NON_SECRET_KEYS 미포함(마스킹 유지).
    "SEED_ADMIN_EMAIL",
    "SEED_ADMIN_PASSWORD",
]

# 비밀이 아니므로 진단 시 전체 값 표시를 허용하는 키
NON_SECRET_KEYS: set[str] = {"EMBEDDING_MODEL", "LLM_PROVIDER", "LLM_MODEL"}


class Settings(BaseSettings):
    """백엔드 환경 설정.

    - 진짜 비밀인 필수 키(아래 3종)는 기본값을 부여하지 않는다(누락 시 fail-fast).
      또한 **빈 문자열/공백만 입력된 경우도 거부**한다 — ``.env``에 ``OPENAI_API_KEY=``
      처럼 값을 비워두면 누락과 동일하게 ``ValidationError``로 기동을 막는다.
    - ``EMBEDDING_MODEL``은 의미상 필수지만 단일 고정 기본값을 제공한다(교체 시 전체
      재임베딩 필요). 빈 값으로 덮어써지면 기본값으로 복원한다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── 필수 키 (기본값 없음 → 누락/빈 값 시 fail-fast) ──
    KAKAO_REST_API_KEY: str  # 지오코딩/주소 변환 (백엔드 전용)
    KAKAO_JS_KEY: str  # 웹 지도 JS SDK (프론트 노출 유일 키, 도메인 화이트리스트 전제)
    OPENAI_API_KEY: str  # 기준 LLM + 임베딩 (백엔드 전용)
    # DB 연결 문자열(비밀: 비밀번호 포함). Story 1.4부터 필수.
    # provider 콘솔의 postgresql://·postgres://를 psycopg3용으로 자동 정규화한다.
    DATABASE_URL: str
    # JWT(access+refresh) HS256 서명 키(백엔드 전용 비밀). Story 1.8부터 필수.
    # 누락/빈 값 시 fail-fast. 32바이트 미만은 거부한다(InsecureKeyLengthWarning 방지).
    JWT_SECRET_KEY: str

    # 임베딩 모델: 단일 고정. 의미상 필수지만 기본값 제공(교체 시 전체 재임베딩 필요).
    EMBEDDING_MODEL: str = DEFAULT_EMBEDDING_MODEL

    # ── 선택 키 (미설정 시 해당 경로만 비활성화, 기동은 정상) ──
    ANTHROPIC_API_KEY: str | None = None  # 멀티 LLM best-effort
    GOOGLE_AI_API_KEY: str | None = None  # 멀티 LLM best-effort
    KAKAO_NATIVE_APP_KEY: str | None = None  # RN 앱 카카오 공유

    # ── 시드 관리자 부트스트랩 (Story 8.1 — scripts/seed_admin.py 전용) ──
    # 앱·통합테스트는 이 키 없이도 기동해야 하므로 선택 키(Optional+None)다. 시드 스크립트가
    # 자체적으로 미설정/빈 값을 검증·안내한다(여기선 _reject_blank_required에 등록하지 않음).
    SEED_ADMIN_EMAIL: str | None = None  # 시드 관리자 이메일(앱 부팅 무관)
    SEED_ADMIN_PASSWORD: str | None = None  # 시드 관리자 비밀번호 — 비밀(마스킹 유지)

    # ── LLM 선택 설정 (Story 7.1 — 둘 다 기본값 보유 → fail-fast 대상 아님) ──
    # 설정값만 바꿔 프로바이더/모델을 전환한다(if 분기 없이 레지스트리 조회). 비밀이 아니다.
    LLM_PROVIDER: str = DEFAULT_LLM_PROVIDER  # openai|anthropic|google (chatbot/llm 레지스트리 키)
    LLM_MODEL: str = DEFAULT_LLM_MODEL  # 기준 OpenAI 모델 id(배포 시 현행 id 확인·교체 가능)

    @field_validator(
        "KAKAO_REST_API_KEY",
        "KAKAO_JS_KEY",
        "OPENAI_API_KEY",
        "DATABASE_URL",
        "JWT_SECRET_KEY",
        mode="after",
    )
    @classmethod
    def _reject_blank_required(cls, v: str) -> str:
        """필수 비밀 키는 빈 문자열/공백을 거부한다(누락과 동일 취급 — fail-fast)."""
        if v is None or not v.strip():
            raise ValueError("필수 키는 비어 있을 수 없습니다 (값을 입력하세요).")
        return v

    @field_validator("JWT_SECRET_KEY", mode="after")
    @classmethod
    def _enforce_jwt_secret_length(cls, v: str) -> str:
        """JWT 서명 키는 최소 32바이트를 강제한다(PyJWT InsecureKeyLengthWarning 차단).

        HS256 키가 32바이트(=256비트) 미만이면 PyJWT 2.13이 경고를 내며 RFC 7518 §3.2를
        위반한다. 약한 키를 기동 시점에 fail-fast로 막는다(빈 값은 위 blank validator가 선처리).
        """
        if len(v) < JWT_SECRET_MIN_LENGTH:
            raise ValueError(
                f"JWT_SECRET_KEY는 최소 {JWT_SECRET_MIN_LENGTH}자 이상이어야 합니다 "
                "(생성: python -c \"import secrets; print(secrets.token_urlsafe(48))\")."
            )
        return v

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        """DB URL 스킴을 psycopg3 드라이버용 ``postgresql+psycopg://``로 정규화한다.

        Supabase/Railway 콘솔이 주는 ``postgresql://``·``postgres://``(또는 다른
        드라이버 접미사)를 받아 psycopg3 스킴으로 통일한다. PostgreSQL 계열이 아니거나
        스킴이 없으면 ``ValueError``로 거부한다(소유자가 provider 문자열을 그대로
        붙여도 동작하되, 잘못된 DB는 명확히 막는다).
        """
        scheme, sep, rest = v.partition("://")
        if not sep:
            raise ValueError(
                "DATABASE_URL은 'scheme://...' 형식이어야 합니다 "
                "(예: postgresql+psycopg://user:password@host:5432/desknow)."
            )
        # 드라이버 접미사(`+psycopg` 등)를 떼고 베이스 스킴만 검사한다.
        base_scheme = scheme.split("+", 1)[0].lower()
        if base_scheme not in ("postgresql", "postgres"):
            raise ValueError(
                f"지원하지 않는 DATABASE_URL 스킴입니다: '{scheme}'. "
                "PostgreSQL 연결 문자열을 사용하세요 "
                "(postgresql:// 또는 postgresql+psycopg://)."
            )
        # 드라이버를 psycopg3로 강제 통일(psycopg2/asyncpg 등이 섞여도 정합 보장).
        return f"postgresql+psycopg://{rest}"

    @field_validator("EMBEDDING_MODEL", mode="after")
    @classmethod
    def _default_embedding_if_blank(cls, v: str) -> str:
        """빈 값으로 덮어써지면 단일 고정 기본 모델로 복원한다."""
        return v if v and v.strip() else DEFAULT_EMBEDDING_MODEL

    @field_validator("LLM_PROVIDER", mode="after")
    @classmethod
    def _default_llm_provider_if_blank(cls, v: str) -> str:
        """빈 값(``.env``의 ``LLM_PROVIDER=``)이면 기준 프로바이더로 복원한다."""
        return v if v and v.strip() else DEFAULT_LLM_PROVIDER

    @field_validator("LLM_MODEL", mode="after")
    @classmethod
    def _default_llm_model_if_blank(cls, v: str) -> str:
        """빈 값이면 기준 OpenAI 모델 기본값으로 복원한다."""
        return v if v and v.strip() else DEFAULT_LLM_MODEL


def _assert_key_lists_match_model() -> None:
    """진단 키 목록(REQUIRED/OPTIONAL)이 ``Settings`` 필드와 정확히 일치하는지 보장한다.

    ``env_status``의 ``getattr(..., None)``는 목록 문자열이 실제 필드명과 어긋나면
    조용히 ``"(미설정)"``로 위장한다. 그 silent drift를 import 시점에 즉시 잡는다.
    """
    declared = set(REQUIRED_KEYS) | set(OPTIONAL_KEYS)
    fields = set(Settings.model_fields)
    missing_in_lists = fields - declared
    unknown_in_lists = declared - fields
    if missing_in_lists or unknown_in_lists:
        raise RuntimeError(
            "진단 키 목록이 Settings 필드와 불일치합니다 — "
            f"목록에 없음: {sorted(missing_in_lists)}, "
            f"모델에 없음: {sorted(unknown_in_lists)}"
        )


_assert_key_lists_match_model()


def _ensure_utf8_streams() -> None:
    """stdout/stderr를 UTF-8(대체 문자 허용)로 재설정한다.

    Windows 한글 콘솔(cp949)이나 파이프/CI 리다이렉트 환경에서 이모지·한글·``…``
    출력 시 ``UnicodeEncodeError``로 진단이 죽는 것을 막는다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # 이미 분리됐거나 재설정 불가한 스트림
                pass


@lru_cache
def get_settings() -> Settings:
    """캐시된 싱글톤 Settings 접근자.

    필수 키 누락 시 ``ValidationError``를 던진다(fail-fast). ``lru_cache``는 예외를
    캐시하지 않으므로, 환경을 고친 뒤 재호출하면 정상 로드가 가능하다.
    """
    return Settings()


def mask_secret(value: str | None, *, reveal: bool = False) -> str:
    """비밀 값을 마스킹한다.

    - 미설정(``None``/빈 문자열/공백만) → ``"(미설정)"``
    - ``reveal=True`` → 전체 값(비밀이 아닌 키 전용)
    - 그 외 → ``앞2자…뒤2자`` 형태. 12자 이하 짧은 값은 전부 ``"****"``.

    짧은 토큰에서 평문 상당 부분이 새는 것을 막기 위해 임계값을 12자로 올리고
    노출 글자 수를 최소화한다(존재 여부 확인이 목적, 식별 가능성 최소화).
    """
    if value is None or value.strip() == "":
        return "(미설정)"
    if reveal:
        return value
    if len(value) <= 12:
        return "****"
    return f"{value[:2]}…{value[-2:]}"


def env_status(settings: Settings) -> dict[str, str]:
    """각 키의 (마스킹된) 상태 문자열을 반환한다. 비밀 값은 평문 노출하지 않는다."""
    status: dict[str, str] = {}
    for key in REQUIRED_KEYS + OPTIONAL_KEYS:
        raw = getattr(settings, key, None)
        status[key] = mask_secret(raw, reveal=key in NON_SECRET_KEYS)
    return status


def _report_failure(exc: ValidationError) -> None:
    """필수 키 누락/빈 값 등 검증 실패를 사람이 읽기 좋게 stderr로 출력한다.

    pydantic 오류의 ``loc``는 보통 ``(필드명,)`` 이지만, 모델/루트 레벨 오류는
    ``loc == ()`` 일 수 있다. ``loc[0]`` 직접 인덱싱은 그 경우 ``IndexError``로
    진단 자체를 죽이므로, 빈 ``loc``를 안전하게 가드한다.
    """

    def _field_of(e: ErrorDetails) -> str | None:
        loc = e.get("loc") or ()
        return str(loc[0]) if loc else None

    missing = [f for e in exc.errors() if e.get("type") == "missing" and (f := _field_of(e))]
    blank = [f for e in exc.errors() if e.get("type") == "value_error" and (f := _field_of(e))]
    other = [
        e
        for e in exc.errors()
        if e.get("type") not in ("missing", "value_error") or not _field_of(e)
    ]

    print("❌ 환경변수 로드 실패 — 기동 중단 (fail-fast)", file=sys.stderr)
    if missing:
        print("   다음 필수 키가 누락되었습니다:", file=sys.stderr)
        for key in missing:
            print(f"     - {key}", file=sys.stderr)
    if blank:
        print("   다음 필수 키가 비어 있습니다(값 입력 필요):", file=sys.stderr)
        for key in blank:
            print(f"     - {key}", file=sys.stderr)
    if other:
        print("   기타 검증 오류:", file=sys.stderr)
        for e in other:
            print(f"     - {e.get('loc')}: {e.get('msg')}", file=sys.stderr)
    print(
        "   → apps/api/.env 를 확인하세요 (가이드: docs/external-services-setup.md).",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    """환경 점검 CLI. 필수 키 누락 시 종료 코드 1(fail-fast), 정상 시 0.

    예: ``python -m app.core.config --check``
    """
    parser = argparse.ArgumentParser(
        prog="python -m app.core.config",
        description="환경변수(.env) 로드 및 필수 키 존재 여부 점검(값은 마스킹).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="키 로드/존재 여부를 점검한다(기본 동작).",
    )
    parser.parse_args(argv)
    _ensure_utf8_streams()  # cp949/리다이렉트 환경 인코딩 에러 방지

    try:
        settings = Settings()  # .env 로드 — 필수 키 누락/빈 값 시 ValidationError
    except ValidationError as exc:
        _report_failure(exc)
        return 1

    status = env_status(settings)
    print("✅ 환경변수 로드 성공 — 키 존재 확인 (값은 마스킹)")
    print("  [필수]")
    for key in REQUIRED_KEYS:
        # EMBEDDING_MODEL은 의미상 필수지만 기본값 보유 → 라벨로 구분 표기
        note = " (기본값 있음)" if key in DEFAULTED_KEYS else ""
        print(f"    {key:<22} = {status[key]}{note}")
    print("  [선택]")
    for key in OPTIONAL_KEYS:
        print(f"    {key:<22} = {status[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
