---
baseline_commit: NO_VCS
---
# Story 1.8: 로그인·로그아웃·세션 유지 & RBAC

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- create-story(2026-06-15): Ultimate context engine 분석 완료 — architecture.md(인증/보안 L155-166·네이밍 L228-241·경계 L347-360·에러/시간 규약·금지 안티패턴) + epics.md(Story 1.8 AC, FR-2, NFR-6) + EXPERIENCE.md(L32 토큰 이원화·L53 로그인=전역 헤더·L122 로그아웃 챗봇 초기화=E7) + 1.7 학습(core/security 해싱·User/UserRole·EMAIL_TAKEN/검증 핸들러·register 패턴·test_main 불변식·네이밍 자동 uq/pk·운영DB 미변조 수기 마이그레이션) + 1.7 deferred(verify_password fail-closed·IntegrityError 과대캐치·email 정규화 불변식) + 현재 코드(core/security·config·errors·time·db·main·auth/{models,schemas,service,router}·env.py·tests·pyproject·migration) 정독 + 실측(PyJWT 2.13.0 HS256 동작·exp/sig 예외·<32B 키 경고·sha256 64자). **UPDATE 중심 스토리**(신규 모듈 0, RefreshToken 1 테이블만 신규). **범위 결정**: 백엔드 로그인/로그아웃/리프레시/RBAC 의존성만(프론트 로그인 UI·자동재발급 인터셉터는 SDK 1.9 이후, 챗봇 세션 종료는 E7 — 본문 §범위 경계 참조). **핵심 함정**: ① JWT_SECRET_KEY <32B → PyJWT InsecureKeyLengthWarning(min 32 강제) ② verify_password가 손상 해시에 예외(fail-open 위험) → fail-closed 래핑 필수 ③ FastAPI 쿠키는 주입 Response param에 set, logout은 반환 Response에 직접 set ④ test_config의 key_lists==model_fields 어서션 → JWT_SECRET_KEY를 REQUIRED_ENV에도 동기화 ⑤ JWT 함수가 get_settings() 소비 → JWT 테스트는 5개 필수 env 주입(conftest auth_env). -->

## Story

As a 가입한 사용자,
I want 이메일·비밀번호로 로그인하고 로그아웃 전까지 인증을 유지하며 내 역할에 맞는 기능만 접근하길,
so that 인증이 필요한 기능을 안전하게(세션 유지·역할 강제·로그아웃 즉시 무효화) 이용한다 (FR-2, NFR-6, UJ-1·2·3).

## Acceptance Criteria

1. **(AC1 — 로그인 & 토큰 발급/보관 이원화)** 가입한 사용자가 올바른 자격 증명으로 로그인하면, **단일 백엔드 발급 JWT(access 단기 + refresh 장기)** 가 발급된다. **refresh 토큰의 해시**가 `refresh_tokens` 테이블에 저장되고(원문 미저장), 토큰은 **웹=httpOnly+Secure+SameSite 쿠키 / RN=응답 본문(SecureStore+Bearer 헤더 보관)** 양쪽으로 제공된다. 백엔드 인증 의존성은 **Authorization Bearer 헤더와 쿠키 양쪽에서 access 토큰을 추출**한다.
2. **(AC2 — 잘못된 자격 증명)** 잘못된 자격 증명(미존재 이메일·틀린 비밀번호·비활성 계정)으로 로그인하면 **401 `UNAUTHENTICATED`** 로 거부되고 표준 에러 스키마로 안내된다. 세 실패 모드는 **동일한 401**로 응답한다(계정 존재 여부 노출 방지 = enumeration 차단).
3. **(AC3 — access 만료 & refresh 재발급)** access 토큰이 만료되어 인증 요청이 **401**을 받으면, 클라이언트는 **refresh 엔드포인트(`POST /api/v1/auth/refresh`)로 1회 재발급**할 수 있다. 백엔드는 유효한 refresh로 **새 토큰 쌍을 회전(rotation) 발급**하고(기존 refresh 즉시 무효화), refresh가 만료/위조/무효(로그아웃·회전 후)면 **401**로 거부한다(클라이언트는 로그인으로 유도). *클라이언트의 401→refresh 자동 1회 재시도 인터셉터는 SDK(1.9) 이후 프론트 작업 — 본 스토리는 백엔드 refresh 엔드포인트만.*
4. **(AC4 — 로그아웃 & 즉시 무효화)** 사용자가 로그아웃하면 제시한 refresh 토큰의 해시 행이 `refresh_tokens`에서 **즉시 삭제(무효화)** 되고 인증 쿠키가 제거되어 세션이 종료된다. 로그아웃은 **멱등**하다(토큰이 이미 없거나 잘못돼도 204로 정상 종료). *(챗봇 대화 종료 연동은 E7.)*
5. **(AC5 — RBAC 역할 강제)** 권한이 없는 역할이 보호된 엔드포인트에 접근하면 **백엔드 의존성이 403 `FORBIDDEN_ROLE`로 최종 강제**한다. access 토큰 없이 보호 엔드포인트에 접근하면 **401 `UNAUTHENTICATED`**. 역할(`booker`/`provider`/`admin`)은 **JWT role 클레임 + FastAPI 의존성**으로 강제하며, **가입 시 확정되어 전환할 수 없다**(역할 변경 엔드포인트 없음). 프론트 라우트 보호는 보조일 뿐 최종 강제 아님.

> **이 스토리의 범위 결정(명시 — 매우 중요, 1.7과 동일 원칙):**
> - **1.8은 백엔드 인증/인가만 구현한다:** 로그인/로그아웃/리프레시 엔드포인트 + `refresh_tokens` 테이블 + JWT 발급/검증 + RBAC 의존성(`core/security`). AC1~5는 전부 백엔드 동작이다.
> - **프론트 로그인/계정 UI(web/admin/mobile) + 401→refresh 자동 재시도 인터셉터는 본 스토리 범위가 아니다.** 아키텍처는 "프론트는 `packages/api-client` 생성 SDK로만 백엔드 호출, 직접 fetch 금지"(L290)를 강제하는데 그 **SDK는 Story 1.9에서 생성**된다. UX(EXPERIENCE.md L53)는 로그인을 "전역 헤더/메뉴"로만 다루고 상세 화면 사양이 없다. → 프론트 인증 UI는 **SDK(1.9) 이후**로 둔다(말미 "질문/확인" 참조).
> - **챗봇 대화 세션 종료(로그아웃 연동)는 E7**(EXPERIENCE.md L122 "로그아웃 시 대화 초기화" = LangGraph thread 초기화). 1.8 로그아웃은 refresh 토큰 무효화 + 쿠키 제거까지만.
> - **계정 비활성화 동작·역할 전환·시드 관리자 생성은 E8**(FR-31~33). 1.8은 로그인 시 `is_active` 거부 + `require_role` 의존성(향후 도메인 라우터가 소비)만 제공한다.

## Tasks / Subtasks

> **권장 순서:** Task 1(config JWT_SECRET_KEY) → Task 2(core/security JWT·fail-closed·RBAC) → Task 3(RefreshToken 모델) → Task 4(스키마) → Task 5(서비스) → Task 6(라우터+쿠키) → Task 7(Alembic refresh_tokens) → Task 8(테스트) → Task 9(문서/무회귀).

- [x] **Task 1 — `app/core/config.py`(UPDATE): `JWT_SECRET_KEY` 필수 비밀 키 추가 (AC: 1, 3, 5)**
  - [x] **신규 필수 비밀 키** `JWT_SECRET_KEY: str`(기본값 없음 → 누락/빈 값 시 fail-fast — 1.1 패턴). access/refresh JWT의 HS256 서명 키(단일 백엔드 발급·검증).
  - [x] **빈 값 거부 validator에 등록:** `_reject_blank_required`의 `@field_validator(...)` 키 목록에 `"JWT_SECRET_KEY"` 추가(공백/빈 문자열 거부).
  - [x] **최소 길이 강제(중요 함정):** 별도 `@field_validator("JWT_SECRET_KEY", mode="after")`로 **`len(v) >= 32` 강제**(미달 시 `ValueError`). 이유: PyJWT 2.13은 HS256 키가 32바이트 미만이면 `InsecureKeyLengthWarning`을 내며 RFC 7518 §3.2 위반(실측 확인). 약한 키를 기동 시점에 막는다.
  - [x] **진단 목록 동기화:** `REQUIRED_KEYS` 리스트에 `"JWT_SECRET_KEY"` 추가(맨 끝 권장). `_assert_key_lists_match_model()`(import 시점)이 `REQUIRED_KEYS|OPTIONAL_KEYS == model_fields`를 강제하므로 **반드시 동기화**(누락 시 import RuntimeError). 비밀이므로 `NON_SECRET_KEYS`에는 넣지 않는다(마스킹 유지).
  - [x] **`.env.example`(UPDATE):** `[필수]` 섹션에 `JWT_SECRET_KEY` 추가 — 용도(JWT 서명, 백엔드 전용 비밀)·생성법 주석(`python -c "import secrets; print(secrets.token_urlsafe(48))"`)·플레이스홀더(`JWT_SECRET_KEY=change-me-generate-a-long-random-secret`). ⚠️ `.env.example`은 추적 파일 — 실제 비밀 금지.
  - [x] **TTL은 env가 아니라 `core/security` 모듈 상수로 둔다**(MVP — config 표면 최소화): access 15분 / refresh 14일(Task 2).
  - [x] **운영 영향 주의(소유자 안내):** `JWT_SECRET_KEY`가 필수가 되므로 소유자 `.env`에 추가하기 전엔 앱 기동(lifespan)·통합테스트가 fail-fast 한다(의도된 동작). README/Completion Notes에 명시.

- [x] **Task 2 — `app/core/security.py`(UPDATE): JWT 발급/검증 · fail-closed · RBAC 의존성 (AC: 1, 2, 3, 5)**
  - [x] **기존 `hash_password`/`verify_password` 보존.** 단 **`verify_password`를 fail-closed로 래핑**(1.7 deferred 회수): pwdlib `verify`는 손상/빈/파싱불가 해시에 **예외**를 던진다(False 아님) → 1.8 로그인이 부분 마이그레이션·손상 `password_hash` 행을 만나면 500. `try/except Exception: return False`로 감싸 **검증 불가 = 인증 실패(False)** 로 만든다(fail-open 차단). 정상 경로 동작·시그니처(`verify(password, hash)` 순서)는 불변.
  - [x] **JWT 상수:** `JWT_ALGORITHM = "HS256"`, `ACCESS_TOKEN_TTL = timedelta(minutes=15)`, `REFRESH_TOKEN_TTL = timedelta(days=14)`, `TOKEN_TYPE_ACCESS = "access"`, `TOKEN_TYPE_REFRESH = "refresh"`. 쿠키명 `ACCESS_COOKIE_NAME = "desknow_access"`, `REFRESH_COOKIE_NAME = "desknow_refresh"`.
  - [x] **시크릿 지연 로드:** JWT 함수는 **함수 내부에서** `get_settings().JWT_SECRET_KEY`를 읽는다(모듈 import 시점 호출 금지 — `test_main` 모듈레벨 TestClient/도구 import가 `.env` 없이도 안전해야 함, 1.4 지연 패턴과 동일).
  - [x] **`AuthPrincipal`**: `@dataclass(frozen=True)` — `user_id: uuid.UUID`, `role: str`(토큰 클레임에서 디코드한 인증 주체. DB 객체 아님).
  - [x] **`create_access_token(user_id: uuid.UUID, role: str, *, now: datetime | None = None) -> str`**: payload `{"sub": str(user_id), "role": role, "type": TOKEN_TYPE_ACCESS, "iat": now, "exp": now + ACCESS_TOKEN_TTL}`(now 미지정 시 `now_utc()` — 1.5 단일 출처, 테스트 결정성 위해 주입 가능). `jwt.encode(..., algorithm=JWT_ALGORITHM)`.
  - [x] **`create_refresh_token(user_id: uuid.UUID, *, now: datetime | None = None) -> str`**: payload `{"sub": str(user_id), "type": TOKEN_TYPE_REFRESH, "jti": uuid.uuid4().hex, "iat": now, "exp": now + REFRESH_TOKEN_TTL}`. **`jti`(랜덤)로 매 발급 토큰이 달라 해시가 고유**해진다(동일 사용자·동초 발급 충돌 방지). role 클레임은 refresh에 넣지 않는다(회전 시 DB의 최신 role 사용).
  - [x] **`decode_token(token: str, *, expected_type: str) -> dict[str, Any]`**: `jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])`. `jwt.InvalidTokenError`(만료=`ExpiredSignatureError`·위조=`InvalidSignatureError` 모두 하위클래스 — 실측 확인)면 `DomainError(ErrorCode.UNAUTHENTICATED, "유효하지 않은 토큰입니다.")`(401). 디코드 후 `claims.get("type") != expected_type`면 동일 401(access↔refresh 교차 사용 차단).
  - [x] **`hash_token(raw: str) -> str`**: `hashlib.sha256(raw.encode()).hexdigest()`(64자 hex). refresh 원문 대신 해시를 DB에 저장/조회한다(DB 유출 시에도 토큰 사용 불가).
  - [x] **`get_current_principal(request: Request) -> AuthPrincipal`**(FastAPI 의존성): access 토큰을 **헤더 우선, 쿠키 폴백**으로 추출 — `Authorization: Bearer <t>`(대소문자 무관, 접두사 strip) 우선, 없으면 `request.cookies.get(ACCESS_COOKIE_NAME)`. 토큰 부재 → `DomainError(UNAUTHENTICATED, ...)`(401). `decode_token(t, expected_type=TOKEN_TYPE_ACCESS)` → `AuthPrincipal(user_id=uuid.UUID(claims["sub"]), role=claims["role"])`. **DB 미접근**(access는 단명 토큰이라 클레임 신뢰; is_active 즉시취소는 E8).
  - [x] **`require_role(*allowed_roles: str) -> Callable[..., AuthPrincipal]`**(의존성 팩토리): 내부 `checker(principal: AuthPrincipal = Depends(get_current_principal))`가 `principal.role not in allowed_roles`면 `DomainError(ErrorCode.FORBIDDEN_ROLE, "이 작업을 수행할 권한이 없습니다.")`(403), 통과 시 principal 반환. **향후 도메인 라우터**(E2 rooms=provider·E8 admin)가 `Depends(require_role("provider"))`로 소비한다. 본 스토리는 의존성 제공 + 테스트로 실증(실 도메인 라우터는 아직 없음).
  - [x] **import:** `import hashlib`, `import uuid`, `from dataclasses import dataclass`, `from datetime import datetime, timedelta`, `from typing import Any, Callable`, `import jwt`, `from fastapi import Depends, Request`, `from app.core.config import get_settings`, `from app.core.errors import DomainError, ErrorCode`, `from app.core.time import now_utc`. (`ErrorCode.UNAUTHENTICATED`(401)·`FORBIDDEN_ROLE`(403)는 1.5에 **이미 정의·등록**됨 — 추가 정의 불필요.)
  - [x] **금지:** access/refresh 외 토큰 타입을 신뢰; `jwt.decode`에 `algorithms` 누락(alg=none 공격); refresh 원문 DB 저장; 시크릿 모듈레벨 로드; `datetime.now()` 직접 호출(→ `now_utc()`).

- [x] **Task 3 — `app/auth/models.py`(UPDATE): `RefreshToken` 모델 (AC: 1, 4)**
  - [x] **신규 테이블 `refresh_tokens`**(아키텍처 §Naming L230에 명시된 테이블명). `users`에 이은 **두 번째 도메인 테이블** + **첫 FK**. User 모델·UserRole은 그대로 둔다.
    ```python
    class RefreshToken(SQLModel, table=True):
        __tablename__ = "refresh_tokens"
        id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
        user_id: uuid.UUID = Field(
            sa_column=Column(
                Uuid(),
                ForeignKey("users.id", ondelete="CASCADE"),  # fk_refresh_tokens_user_id_users(규약 자동)
                nullable=False,
                index=True,  # idx_refresh_tokens_user_id — 사용자별 조회/CASCADE 보조
            ),
        )
        token_hash: str = Field(unique=True, max_length=64)  # sha256 hex(64) → uq_refresh_tokens_token_hash
        expires_at: datetime = Field(
            sa_column=Column(DateTime(timezone=True), nullable=False),  # *_at = UTC timestamptz
        )
        created_at: datetime = Field(
            default_factory=now_utc,
            sa_column=Column(DateTime(timezone=True), nullable=False),
        )
    ```
  - [x] **import 추가:** 기존 `from sqlalchemy import Column, DateTime`에 `ForeignKey, Uuid` 추가(`from sqlalchemy import Column, DateTime, ForeignKey, Uuid`).
  - [x] **제약명은 손으로 짓지 않는다** — 1.4 `NAMING_CONVENTION`이 자동 부여: PK `pk_refresh_tokens`, FK `fk_refresh_tokens_user_id_users`(템플릿 `fk_%(table)s_%(col)s_%(referred)s`), UNIQUE `uq_refresh_tokens_token_hash`, INDEX `idx_refresh_tokens_user_id`. **명시적 `index=True`로 user_id 인덱스를 켜되 이름은 규약이 부여**.
  - [x] **`token_hash`는 원문이 아니라 sha256 해시**(64 hex). UNIQUE로 조회 키이자 회전/로그아웃 삭제 대상.
  - [x] **`ondelete="CASCADE"`**: 사용자 hard-delete 시 토큰 정리(MVP는 is_active=False라 미발생하나 위생). SQLModel `foreign_key=` 단축형은 ondelete 미지원 → 위 명시적 `Column(ForeignKey(...))` 사용.
  - [x] **금지:** refresh 원문/평문 비밀 컬럼; `role` 같은 비-토큰 컬럼; `SQLModel.metadata.create_all`(Alembic 단독 — 1.4).

- [x] **Task 4 — `app/auth/schemas.py`(UPDATE): 로그인/토큰 스키마 (AC: 1, 2, 3, 4)**
  - [x] **기존 `RegisterRequest`/`UserPublic` 보존.** 아래 추가:
    ```python
    class LoginRequest(BaseModel):
        email: str       # ⚠️ EmailStr 아님 — 형식 위반도 401(enumeration·형식 누출 방지). 서비스가 .strip().lower() 정규화
        password: str    # 정책 validator 없음 — 로그인은 검증이 아니라 대조

    class TokenResponse(BaseModel):
        access_token: str
        refresh_token: str
        token_type: str = "bearer"   # 와이어 snake_case 유지

    class RefreshRequest(BaseModel):
        refresh_token: str | None = None   # RN=본문 / 웹=쿠키(미전송 시 라우터가 쿠키 폴백)

    class LogoutRequest(BaseModel):
        refresh_token: str | None = None   # 동상. 멱등 로그아웃
    ```
  - [x] **`LoginRequest.email`은 `str`(EmailStr 아님):** 로그인에서 잘못된 이메일 형식까지 **422가 아니라 401로 단일화**(AC2 "잘못된 자격증명 → 401", enumeration·형식 누출 차단). 정규화(`.strip().lower()`)는 서비스가 수행한다. *(가입은 형식 검증이 본질이라 EmailStr; 로그인은 대조가 본질이라 str — 의도된 비대칭.)*
  - [x] **`TokenResponse` 필드는 snake_case**(와이어 규약 L286·L240). `token_type="bearer"`(소문자, RFC 6750).
  - [x] **금지:** 응답에 refresh **해시** 노출(원문만 반환, 해시는 DB 내부); access/refresh를 camelCase로.

- [x] **Task 5 — `app/auth/service.py`(UPDATE): 인증/발급/회전/무효화 (AC: 1, 2, 3, 4, 5)**
  - [x] **기존 `register_user` 보존.** 아래 함수 추가(라우터에서 도메인 로직 분리 — §Boundaries L349):
  - [x] **`authenticate_user(session, email: str, password: str) -> User`** (AC2): `email.strip().lower()` 정규화 → `select(User).where(User.email == email)` 조회. **미존재 OR `not verify_password(password, user.password_hash)` OR `not user.is_active`** → **모두 동일** `DomainError(ErrorCode.UNAUTHENTICATED, "이메일 또는 비밀번호가 올바르지 않습니다.")`(401, enumeration 차단). 통과 시 User 반환. *(verify_password는 Task 2 fail-closed라 손상 해시도 안전히 False→401.)*
  - [x] **`issue_token_pair(session, user: User) -> TokenResponse`** (AC1): `access = create_access_token(user.id, user.role)`; `raw_refresh = create_refresh_token(user.id)`; `session.add(RefreshToken(user_id=user.id, token_hash=hash_token(raw_refresh), expires_at=now_utc() + REFRESH_TOKEN_TTL))`; `session.commit()`; `TokenResponse(access_token=access, refresh_token=raw_refresh)` 반환. **refresh 해시만 저장**(원문 미저장).
  - [x] **`rotate_token_pair(session, raw_refresh: str) -> TokenResponse`** (AC3): `decode_token(raw_refresh, expected_type=TOKEN_TYPE_REFRESH)`(만료/위조/타입오류 → 401) → `row = session.exec(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_refresh))).first()`; **`row is None`(로그아웃·이미 회전·위조) → 401**; `session.delete(row)`(회전 — 기존 무효화); `user = get_user_by_id(session, uuid.UUID(claims["sub"]))`(미존재/비활성 → 401); **새 쌍 발급**(`issue_token_pair` 재사용 또는 인라인 — 같은 트랜잭션에서 add+commit) 후 반환. **로테이션**으로 refresh 재사용 공격을 1회용으로 제한.
  - [x] **`revoke_refresh_token(session, raw_refresh: str | None) -> None`** (AC4): `raw_refresh`가 None이면 즉시 반환(멱등). **decode 하지 않고** `hash_token`으로 행 조회 → 있으면 `session.delete(row)` + `commit`, 없으면 no-op(멱등 — 만료/위조 토큰도 에러 없이 로그아웃 성공). 손상 토큰에도 절대 예외/401 금지.
  - [x] **`get_user_by_id(session, user_id: uuid.UUID) -> User`** (AC5/`/me`): `session.get(User, user_id)`; None → `DomainError(UNAUTHENTICATED, ...)`(401). `/me`와 refresh가 공유.
  - [x] **IntegrityError 과대캐치 금지(1.7 deferred 교훈):** refresh insert는 `jti` 랜덤으로 `token_hash` 충돌이 천문학적 → **broad `except IntegrityError` 래핑하지 않는다**(register_user의 EMAIL_TAKEN 변환을 복사 금지). 만약의 충돌은 그대로 전파(500). register_user의 기존 캐치는 건드리지 않는다.
  - [x] **import:** `from app.auth.models import RefreshToken, User`, `from app.auth.schemas import TokenResponse`, `from app.core.security import (create_access_token, create_refresh_token, decode_token, hash_token, verify_password, TOKEN_TYPE_REFRESH, REFRESH_TOKEN_TTL)`, `from app.core.time import now_utc`, `from app.core.errors import DomainError, ErrorCode`.
  - [x] **금지:** raw `HTTPException`/문자열 코드(→ `DomainError`); refresh 만료 후에도 발급(decode가 exp 강제); 비활성 사용자에 토큰 발급.

- [x] **Task 6 — `app/auth/router.py`(UPDATE): login/refresh/logout/me + 쿠키 (AC: 1, 2, 3, 4, 5)**
  - [x] **기존 `register` 라우트 보존.** `router`(prefix `/auth`)에 아래 추가 → 최종 경로 `/api/v1/auth/{login,refresh,logout,me}`. **`main.py` 변경 불필요**(auth_router는 이미 `api_router`에 포함됨 — 새 라우트는 자동 노출).
  - [x] **쿠키 헬퍼**(라우터 모듈 내 private):
    ```python
    def _set_auth_cookies(response: Response, tokens: TokenResponse) -> None:
        response.set_cookie(ACCESS_COOKIE_NAME, tokens.access_token, httponly=True, secure=True,
                            samesite="lax", path="/", max_age=int(ACCESS_TOKEN_TTL.total_seconds()))
        response.set_cookie(REFRESH_COOKIE_NAME, tokens.refresh_token, httponly=True, secure=True,
                            samesite="lax", path="/api/v1/auth", max_age=int(REFRESH_TOKEN_TTL.total_seconds()))
    def _clear_auth_cookies(response: Response) -> None:
        response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
        response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/v1/auth")
    ```
    **refresh 쿠키 path를 `/api/v1/auth`로 한정**(노출 최소화 — refresh/logout만 전송). access는 `path="/"`. httpOnly+Secure+SameSite(AC1).
  - [x] **`POST /auth/login` → 200 + TokenResponse, 쿠키 set:**
    ```python
    @router.post("/login", response_model=TokenResponse, responses={401: {"model": ErrorResponse}})
    def login(data: LoginRequest, response: Response, session: Session = Depends(get_session)) -> TokenResponse:
        user = service.authenticate_user(session, data.email, data.password)
        tokens = service.issue_token_pair(session, user)
        _set_auth_cookies(response, tokens)   # 주입 Response에 set → FastAPI가 최종 응답에 병합
        return tokens
    ```
    상태 200(register=201과 달리 리소스 생성 아님). **쿠키는 주입된 `response: Response`에 set**(모델 반환과 병행 — FastAPI가 병합).
  - [x] **`POST /auth/refresh` → 200 + TokenResponse, 쿠키 set:** body `RefreshRequest` 또는 쿠키에서 refresh 추출 — `raw = data.refresh_token or request.cookies.get(REFRESH_COOKIE_NAME)`; 없으면 `DomainError(UNAUTHENTICATED)`(401); `tokens = service.rotate_token_pair(session, raw)`; `_set_auth_cookies(response, tokens)`; return tokens. (`request: Request, response: Response` 주입.)
  - [x] **`POST /auth/logout` → 204, 쿠키 제거, 멱등:**
    ```python
    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout(data: LogoutRequest, request: Request, session: Session = Depends(get_session)) -> Response:
        raw = data.refresh_token or request.cookies.get(REFRESH_COOKIE_NAME)
        service.revoke_refresh_token(session, raw)
        resp = Response(status_code=status.HTTP_204_NO_CONTENT)
        _clear_auth_cookies(resp)   # ⚠️ 반환할 Response에 직접 set(주입 response param에 set하면 병합 안 됨)
        return resp
    ```
    **함정:** 별도 `Response`를 반환하므로 쿠키 삭제는 **반환 객체**에 한다(주입 response가 아님). 멱등(토큰 없어도 204).
  - [x] **`GET /auth/me` → 200 + UserPublic(인증 필요):**
    ```python
    @router.get("/me", response_model=UserPublic, responses={401: {"model": ErrorResponse}})
    def me(principal: AuthPrincipal = Depends(get_current_principal),
           session: Session = Depends(get_session)) -> User:
        return service.get_user_by_id(session, principal.user_id)
    ```
    프론트가 세션 복원에 사용 + `get_current_principal`(헤더/쿠키 추출) 실증.
  - [x] **import 추가:** `from fastapi import APIRouter, Depends, Request, Response, status`(기존에 status 있음), `from app.auth.schemas import (LoginRequest, LogoutRequest, RefreshRequest, RegisterRequest, TokenResponse, UserPublic)`, `from app.core.security import (ACCESS_COOKIE_NAME, ACCESS_TOKEN_TTL, AuthPrincipal, REFRESH_COOKIE_NAME, REFRESH_TOKEN_TTL, get_current_principal)`, `from app.core.errors import DomainError, ErrorCode, ErrorResponse`.
  - [x] **`responses={401: {"model": ErrorResponse}}`** 로 OpenAPI에 에러 계약 노출(1.9 SDK가 `detail.code` 타입 생성). login/refresh/me에 적용.
  - [x] **보존(회귀 불변식):** `register` 라우트·`main.py` 배선·CORS(`allow_credentials=True`, 쿠키 대비)·`/api/v1` 프리픽스·전역 핸들러 전부 그대로.

- [x] **Task 7 — Alembic: `refresh_tokens` 테이블 마이그레이션 (AC: 1, 4)**
  - [x] **`alembic/env.py` 변경 불필요:** 모델 허브가 이미 `from app.auth import models`(모듈 전체)를 import → `RefreshToken`이 `SQLModel.metadata`에 자동 등록(L51). 확인만.
  - [x] **마이그레이션 생성:** `uv run alembic revision -m "create refresh_tokens table"`(빈 revision — `script.py.mako`가 `import sqlmodel` 포함). `down_revision`은 **`191d9c7dab2d`**(users 마이그레이션) — FK가 users.id를 참조하므로 users 이후 순서 보장. 라이브 DB가 닿고 베이스라인+users가 적용됐으면 `--autogenerate`로 생성 가능(1.4 파이프라인 2차 실증).
  - [x] **본문(autogenerate 미사용 시 수기 — 1.7과 동일 폴백):**
    ```python
    def upgrade() -> None:
        op.create_table(
            "refresh_tokens",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("token_hash", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                    name="fk_refresh_tokens_user_id_users", ondelete="CASCADE"),
            sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        )
        op.create_index("idx_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    def downgrade() -> None:
        op.drop_index("idx_refresh_tokens_user_id", table_name="refresh_tokens")
        op.drop_table("refresh_tokens")
    ```
  - [x] **검증:** 제약명이 규약대로(`pk_refresh_tokens`·`fk_refresh_tokens_user_id_users`·`uq_refresh_tokens_token_hash`·`idx_refresh_tokens_user_id`)인지, `*_at`이 `timestamptz`인지, **도메인 테이블이 `refresh_tokens` 하나만** 추가됐는지. `uv run alembic upgrade head --sql`(오프라인)로 DDL 확인(라이브 DB 불필요). **운영 DB 미변조** 위해 1.7처럼 autogenerate 대신 수기+오프라인 검증 채택 가능.
  - [x] **금지:** `create_all`; 베이스라인/users 외 다른 테이블 동시 생성; FK 없이 user_id만(참조 무결성 상실).

- [x] **Task 8 — 테스트 (AC: 1, 2, 3, 4, 5)**
  - [x] **`tests/conftest.py`(신규 — 공유 JWT 환경 픽스처):** JWT 함수가 `get_settings()`(5개 필수 키 전부)를 소비하므로, JWT를 건드리는 테스트는 필수 env를 주입해야 한다. **non-autouse** 픽스처(요청한 테스트만 적용 → test_config·test_main 무간섭):
    ```python
    import pytest
    from app.core.config import get_settings
    from app.core.db import get_engine
    _AUTH_ENV = {
        "KAKAO_REST_API_KEY": "test-kakao-rest", "KAKAO_JS_KEY": "test-kakao-js",
        "OPENAI_API_KEY": "test-openai", "DATABASE_URL": "postgresql://u:p@localhost:5432/desknow",
        "JWT_SECRET_KEY": "test-jwt-secret-key-at-least-32-bytes-long-xx",  # ≥32B(InsecureKeyLengthWarning 회피)
    }
    @pytest.fixture
    def auth_env(monkeypatch):
        for k, v in _AUTH_ENV.items(): monkeypatch.setenv(k, v)
        get_settings.cache_clear(); get_engine.cache_clear()
        yield
        get_settings.cache_clear(); get_engine.cache_clear()
    ```
  - [x] **`tests/core/test_security.py`(UPDATE):** ⓐ `verify_password` **fail-closed** — `verify_password("x", "not-a-hash")`/`verify_password("x", "")`가 **예외 없이 False**(1.7 deferred 회수 실증). ⓑ(auth_env) access 발급→`decode_token(..., expected_type=access)`가 sub/role 복원, refresh도 동상. ⓒ **만료** — `create_access_token(uid, role, now=<과거>)`로 exp 과거 토큰 → `decode_token`이 `DomainError(UNAUTHENTICATED, 401)`. ⓓ **타입 교차** — access를 `expected_type=refresh`로 decode → 401. ⓔ **위조** — 서명 변조/임의 문자열 → 401. ⓕ `hash_token` 결정성 + 64 hex. ⓖ **`get_current_principal`/`require_role`은 미니앱으로 실증**(test_errors 미니앱 패턴): 라우트 `Depends(require_role("provider"))` — provider 토큰(헤더) →200, booker 토큰 →**403 FORBIDDEN_ROLE**, 토큰 無 →**401 UNAUTHENTICATED**. 추가로 `get_current_principal`의 **쿠키 추출**(access를 `desknow_access` 쿠키로) →200으로 헤더/쿠키 양쪽 실증(AC1·AC5).
  - [x] **`tests/auth/test_service.py`(UPDATE):** FakeSession을 확장(`get`/`delete` + 토큰 조회 지원 — 아래)하여: ⓐ `authenticate_user` 성공(실제 `hash_password`로 만든 해시 보유 User), ⓑ 틀린 비번/미존재/`is_active=False` **각각 401 UNAUTHENTICATED**(동일 코드), ⓒ 손상 해시 User → fail-closed로 401, ⓓ(auth_env) `issue_token_pair`가 RefreshToken을 add(해시 저장·원문 아님)+commit하고 TokenResponse 반환, ⓔ `rotate_token_pair`가 기존 행 delete+새 행 add(회전)·미존재 해시 → 401, ⓕ `revoke_refresh_token(None)` no-op·존재 시 delete·미존재 시 no-op(멱등), ⓖ `get_user_by_id` 미존재 → 401. **FakeSession 확장**(register 테스트 그린 유지): 기존 필드 보존 + `get(model, pk)`·`delete(obj)`·토큰/유저를 구분 반환할 수 있게 `exec`가 받은 statement로 분기하거나 결과를 주입식으로(예: `users`/`tokens` dict). register용 기존 시그니처/동작은 깨지 않게 추가만.
  - [x] **`tests/auth/test_router.py`(UPDATE):** `dependency_overrides[get_session]` + `auth_env`로(라우터 JWT 발급이 settings 소비): ⓐ **로그인 성공** → 200 + `{access_token, refresh_token, token_type:"bearer"}` + **`Set-Cookie`에 `desknow_access`·`desknow_refresh`(HttpOnly·Secure·SameSite=Lax)**(헤더 파싱으로 단언). ⓑ 틀린 자격 → **401 UNAUTHENTICATED**. ⓒ **refresh** 성공 → 200 + 새 토큰(회전), 무효 refresh → 401, 토큰 부재(본문·쿠키 모두 없음) → 401. ⓓ **logout** → **204** + `Set-Cookie` 만료(삭제) 헤더, 토큰 없이 호출해도 204(멱등). ⓔ **`/me`** — 유효 access(헤더 Bearer) → 200 + UserPublic(해시 비노출·`...Z`), 토큰 없음 → 401. **반드시 `finally: app.dependency_overrides.clear()`**. *(쿠키 round-trip은 TestClient가 Secure를 강제하지 않아 Set-Cookie 속성 단언으로 검증 — 실 브라우저 https/cross-origin은 1.9+/배포 영역.)*
  - [x] **`tests/integration/test_auth_session.py`(신규, `TEST_DATABASE_URL` 가드 skipif — 1.4/1.7 패턴):** `alembic upgrade head` 후 ⓐ `refresh_tokens` 테이블+`uq_refresh_tokens_token_hash`+FK 존재, ⓑ 가입→로그인(refresh 행 1개 생성·해시 저장)→`/me`(또는 토큰 디코드)→refresh(옛 해시 행 삭제·새 행 생성=회전)→logout(행 삭제) 왕복, ⓒ 동일 refresh 재사용(회전 후) → 401. CI에 라이브 DB 없으면 자동 skip.
  - [x] **`tests/core/test_config.py`(UPDATE):** `REQUIRED_ENV`에 `"JWT_SECRET_KEY": "test-jwt-secret-key-at-least-32-bytes-long-xx"`(≥32) 추가. `test_missing_required_keys_*`의 누락 집합 단언은 `<=`(subset)라 그대로 통과하나 명확성 위해 JWT_SECRET_KEY 포함 고려. **신규 테스트:** `JWT_SECRET_KEY`가 32자 미만이면 `ValidationError`(min-length validator). `test_key_lists_match_model_fields`는 Task 1의 REQUIRED_KEYS 동기화로 자동 그린.
  - [x] **`tests/test_main.py` 무회귀(불변식):** 모듈 레벨 `TestClient(app)` 유지(새 라우트는 import 시 DB 비트리거 — 시크릿도 함수 내부 지연 로드라 안전). **바꾸지 말 것.** 전부 그린 확인.
  - [x] **게이트:** `uv run ruff check . && uv run mypy && uv run pytest`. 기준선 **86 passed·2 skipped**(1.7 후) → 신규 후 전부 그린.

- [x] **Task 9 — 문서 & 무회귀 확인 (AC: 1~5)**
  - [x] **`apps/api/README.md`(UPDATE):** "인증 — 회원가입(1.7)" 다음에 "인증 — 로그인/세션/RBAC(1.8)" 섹션 — `POST /auth/login`(200+TokenResponse, 쿠키+본문 이원화)·`/refresh`(회전)·`/logout`(204 멱등)·`GET /auth/me`, 토큰 보관(웹=쿠키/RN=헤더), `require_role` 의존성 소비 예, **`JWT_SECRET_KEY` 필수 추가**(생성법) + `alembic upgrade head`로 `refresh_tokens` 적용 안내. 에러코드(UNAUTHENTICATED 401·FORBIDDEN_ROLE 403).
  - [x] **1.1~1.7 산출물 무회귀:** **백엔드 전용 변경**(프론트 web/admin/mobile·packages 무영향). `mypy strict`(pydantic.mypy)·`ruff(E,F,I,B,UP)` 통과. `alembic`은 ruff `extend-exclude`라 마이그레이션 린트 churn 없음. `register`·`users`·config 기존 동작·test_main 불변식 보존.

### Review Findings

코드 리뷰(2026-06-15, 3-레이어 적대적 병렬: Blind Hunter · Edge Case Hunter · Acceptance Auditor, 전부 claude-opus-4-8[1m]). **Acceptance Auditor: AC1~5 전부 PASS · 스코프 크리프 0 · 안티패턴(refresh 해시저장·algorithms 명시·type 검사·jti·verify fail-closed·로그인 401 단일화·LoginRequest.email=str·로그아웃 멱등·반환 Response 쿠키·IntegrityError 미과대캐치·시크릿 지연로드·REQUIRED_KEYS 동기화) 전부 준수.** 게이트 실측 일치(ruff/mypy/pytest 131 passed·3 skipped). **patch 2 · defer 12 · dismiss 8.** 세 레이어 수렴 핵심 = 서명 유효·클레임 손상 토큰의 미처리 500(모듈이 문서화한 "모든 토큰 문제 → 401" 계약 위반).

**Patch (적용 완료 2026-06-15 — 게이트 재그린 ruff·mypy 19 files·pytest 138 passed·3 skipped, 기준선 131→+7 회귀):**

- [x] [Review][Patch] 서명 유효·클레임 손상 토큰이 처리 안 된 500 유발(계약 "모든 토큰 문제 → 401" 위반) — `decode_token`이 서명·exp·type만 검증하고 `sub` UUID/`role` 존재 형태를 검증하지 않아, `get_current_principal`의 `uuid.UUID(claims["sub"])`·`claims["role"]`와 `rotate_token_pair`의 `uuid.UUID(claims["sub"])`가 비-UUID `sub`·누락 `role`/`exp`에 `ValueError`/`KeyError`(미처리 500)를 던짐. 정상 운영(백엔드 단일 발급)에선 미발현이나 시크릿 유출·향후 발급경로·테스트토큰에 노출 + 문서화 계약 위반. **수정:** `jwt.decode(..., options={"require": ["exp", "type", "sub"]})`(refresh도 3클레임 보유 — role은 access 전용이라 전역 require에 넣지 않음) + `get_current_principal`/`rotate_token_pair`의 `uuid.UUID(sub)`·`role` 추출을 try/except·존재검사로 감싸 `DomainError(UNAUTHENTICATED)`(401) 반환. [apps/api/app/core/security.py:134-150,174-184; apps/api/app/auth/service.py:117] (blind+edge+auditor 3레이어 수렴)
- [x] [Review][Patch] `_extract_access_token` 분기 테스트 부재 — 1.8 신규 추출 로직의 소문자 `bearer` 스킴·빈/공백 `Bearer `(쿠키 폴백)·헤더+쿠키 동시 우선순위(헤더 우선) 경로가 상시 스위트에서 미검증. 해피 헤더/쿠키 외 분기에 단위 테스트 추가(미니앱 패턴 재사용). [apps/api/tests/core/test_security.py] (edge)

**Defer (deferred-work.md 기록 — 후속/인프라/배포):**

- [x] [Review][Defer] refresh 회전 동시성 더블스펜드(행 잠금 없음) — 동일 refresh 동시 `/refresh` 2건이 둘 다 행 조회→삭제→발급해 한 토큰에서 두 패밀리 생성 가능(회전의 재사용 차단 무력화) [apps/api/app/auth/service.py:104-121] — deferred (blind+edge)
- [x] [Review][Defer] `expires_at` 컬럼이 조회 WHERE에서 미사용(JWT exp 단독 강제) — stateful 검증이 무효화(삭제)만 보고 만료는 안 봄. 만료행 cleanup 부재는 dev-story 1.8 defer와 중복(기존 기록) [apps/api/app/auth/service.py:112-116; apps/api/app/auth/models.py:84] — deferred (blind+edge+auditor)
- [x] [Review][Defer] access 토큰 role/is_active 즉시취소 지연(≤15분) — `get_current_principal`이 클레임 신뢰·DB 미조회라 강등/비활성이 access TTL만큼 지연. **스펙 명시 설계(E8 즉시취소 영역)** [apps/api/app/core/security.py:174-184] — deferred (blind)
- [x] [Review][Defer] refresh 재사용 탐지·토큰 패밀리 무효화 부재 — 회전 후 옛 토큰 재제시(도난 신호)에 단순 401, 자손 패밀리 미무효화 [apps/api/app/auth/service.py:115] — deferred (blind)
- [x] [Review][Defer] 세션 수 제한·"전체 로그아웃" 부재 — 매 로그인이 무제한 refresh 행 생성, 단일 토큰만 로그아웃 [apps/api/app/auth/service.py:84-101] — deferred (blind)
- [x] [Review][Defer] CSRF — 쿠키 인증에 CSRF 토큰 부재(SameSite=lax가 cross-site POST는 차단하나 GET 변경 엔드포인트 등장 시 노출) [apps/api/app/auth/router.py:45-68] — deferred, 1.9 프론트 (blind)
- [x] [Review][Defer] SameSite=lax가 cross-site 웹 refresh 쿠키 전송 차단(프론트·API 다른 사이트 배포 시 쿠키 폴백 무력) [apps/api/app/auth/router.py:56,65] — deferred, 배포/1.9 (edge)
- [x] [Review][Defer] 쿠키 `Secure=True` 무조건 하드코딩 → 로컬 HTTP 개발 시 브라우저가 쿠키 폐기(env 게이트 없음). 기존 1.8 cross-origin 검증 defer와 인접 [apps/api/app/auth/router.py:51-68] — deferred, 1.9 웹 (blind+edge)
- [x] [Review][Defer] 유니코드 이메일 정규화(`.strip().lower()`만) → NFC/NFKC·casefold 차이로 시각적 동일 이메일 중복가입 가능. **기존 1.7 defer(정규화 불변식)와 동일 계열** [apps/api/app/auth/service.py:50,73] — deferred, pre-existing 1.7 (blind)
- [x] [Review][Defer] `delete_cookie`가 set과 동일한 `secure`/`samesite` 속성 미전달 — 일부 브라우저에서 만료 Set-Cookie가 원본을 못 지움(서버측 행 삭제가 최종 권위라 무해) [apps/api/app/auth/router.py:71-74] — deferred (edge)
- [x] [Review][Defer] `authenticate_user` 타이밍 enumeration — `user is None`이면 Argon2 verify를 건너뛰어 미존재(빠름) vs 존재·틀린비번(느림) 시간차로 계정 존재 추정 가능. 응답 코드/메시지는 단일화(AC2 PASS)됐으나 타이밍은 누출. **수정안:** user None일 때 더미 Argon2 verify로 시간 균등화 [apps/api/app/auth/service.py:75-80] — deferred, AC2 의도 하드닝(권장 우선 검토) (blind+edge)
- [x] [Review][Defer] 테스트 충실도: `FakeSession.exec`가 User select의 whereclause를 무시(`existing` 무조건 반환) → `authenticate_user`의 이메일 정규화·조회 술어가 상시 스위트에서 공허 통과(통합테스트는 커버하나 라이브DB 없으면 skip). 기존 1.7 동일 계열 [apps/api/tests/auth/test_service.py:69-74] — deferred (edge)

**Dismiss (8, 기록 안 함):** ① 주입 `now`가 naive면 잘못된 exp(키워드전용·내부 테스트 시드·전 호출처 aware → 무해) ② access/refresh 시크릿 공유(type 검사 존재·현 호출처 안전) ③ 미인증 로그아웃이 피해자 토큰 무효화(피해자의 비밀 refresh 원문 보유 전제 — 비현실) ④ `token_hash` max_length=64(정확히 sha256 64자 — Blind 자체 기각) ⑤ 시크릿 길이 char vs byte(UTF-8은 char당 ≥1byte라 32자 ≥ 32byte 항상 성립 + 12자 거부·32자 수용 테스트로 경계 커버 — 오탐) ⑥ `hash_token` 공백 토큰 로그아웃 미무효화(opaque bearer는 verbatim 전송·멱등 설계 — 무해) ⑦ `token_hash` 충돌 500(의도적·천문학적 비확률·문서화) ⑧ `expires_at` default_factory 부재(TTL 의존이라 명시 필수가 올바른 설계).

## Dev Notes

### 이 스토리의 범위 경계 (스코프 크리프 방지 — 매우 중요)

| 항목 | 이 스토리(1.8) | 비고 |
|------|----------------|------|
| `POST /auth/login`(JWT access+refresh 발급, 쿠키+본문 이원화) | ✅ | 200 + TokenResponse |
| `refresh_tokens` 테이블 + 마이그레이션(해시 저장) | ✅ 두 번째 도메인 테이블·첫 FK | `uq_refresh_tokens_token_hash` |
| `POST /auth/refresh`(회전 발급·무효 401) | ✅ | rotation |
| `POST /auth/logout`(refresh 해시 삭제·쿠키 제거·멱등) | ✅ 204 | 챗봇 세션 종료는 ❌ E7 |
| `GET /auth/me`(인증 필요, UserPublic) | ✅ | `get_current_principal` 실증 |
| `core/security` JWT(create/decode)·`hash_token`·`AuthPrincipal`·`get_current_principal`·`require_role` | ✅ | 인증/인가 단일 출처(§Boundaries L351) |
| `verify_password` fail-closed 래핑 | ✅ | 1.7 deferred 회수 |
| `JWT_SECRET_KEY` 필수 config(min 32B) | ✅ | 1.1 fail-fast 패턴 |
| 로그인 시 `is_active=False` 거부(401) | ✅ | E8 비활성화가 사용 |
| **프론트 로그인/계정 UI(web/admin/mobile)** | ❌ | SDK(1.9) 이후 — 직접 fetch 금지(L290) |
| **401→refresh 자동 1회 재시도 인터셉터(클라이언트)** | ❌ | SDK(1.9) 이후 프론트(백엔드는 refresh 엔드포인트만) |
| **챗봇 대화 세션 종료(로그아웃 연동)** | ❌ | **E7**(LangGraph thread 초기화) |
| **계정 비활성화 동작·역할 전환·시드 관리자 생성(FR-31~33)** | ❌ | **E8**(1.8은 require_role 의존성 + is_active 로그인 거부만) |
| **OpenAPI→TS SDK 생성·drift 검사** | ❌ | **1.9** |
| **비밀번호 재설정·이메일 인증·레이트리밋** | ❌ | MVP 범위 밖 / 인프라 |

### 정확한 인증/보안 규약 (AC1·AC3·AC5 — 그대로 적용)

- **단일 백엔드 발급 JWT(HS256), PyJWT 2.13.0**(설치 확인). access 단기(15분) + refresh 장기(14일). HS256은 HMAC이라 `cryptography` extra 불필요(실측). **`jwt.decode`에 `algorithms=[...]` 필수**(생략 시 alg=none 공격 노출).
- **토큰 클레임:** access `{sub, role, type:"access", iat, exp}`, refresh `{sub, type:"refresh", jti, iat, exp}`. **`type`으로 access↔refresh 교차 사용 차단**, **`jti`(랜덤)로 refresh 해시 고유성** 보장. refresh에 role 미포함(회전 시 DB 최신 role 사용).
- **refresh = 해시 저장(원문 미저장):** `hash_token`=sha256 hex(64자). DB는 `token_hash`만 보유 → 유출돼도 토큰 사용 불가. **무효화 = 행 삭제**(로그아웃·회전). 검증 = JWT 디코드(stateless: sig+exp+type) + DB 해시 조회(stateful: 무효화 여부) 이중.
- **회전(rotation):** refresh 사용 시 옛 행 삭제 + 새 쌍 발급 → refresh 1회용화(재사용 탐지 기반).
- **토큰 보관 이원화(AC1·EXPERIENCE.md L32):** 웹=httpOnly+Secure+SameSite 쿠키 / RN=응답 본문→SecureStore→Bearer 헤더. **백엔드 추출은 헤더 우선·쿠키 폴백**(`get_current_principal`). 로그인은 쿠키 set **및** 본문 반환(클라이언트가 선택).
- **RBAC(AC5·§Auth L162·§Boundaries L351):** JWT role 클레임 + `require_role(*roles)` 의존성이 백엔드 최종 강제(403 FORBIDDEN_ROLE). 역할은 가입 시 확정·전환 불가(역할 변경 엔드포인트 없음). 프론트 라우트 보호는 보조.
- **fail-closed(1.7 deferred):** `verify_password`는 손상/빈 해시에 예외→**False**(인증 실패)로 래핑. 검증 불가가 인증 통과(fail-open)가 되면 안 된다.
- **`JWT_SECRET_KEY` ≥ 32바이트:** PyJWT 2.13이 미달 시 `InsecureKeyLengthWarning`(RFC 7518 §3.2). config validator로 강제 + 테스트 비밀도 ≥32.

### 정확한 데이터/네이밍 규약 (AC1/AC4 — 1.4 상속)

- **테이블 `refresh_tokens`**(복수 snake_case, §Naming L230). PK `pk_refresh_tokens`(uuid). **FK `fk_refresh_tokens_user_id_users`**(→ users.id, ondelete CASCADE), **UNIQUE `uq_refresh_tokens_token_hash`**, INDEX `idx_refresh_tokens_user_id`. **제약명은 1.4 `NAMING_CONVENTION`이 자동 부여** — 손으로 짓지 않는다.
- **`*_at`(`expires_at`·`created_at`) = UTC `timestamptz`**(`Column(DateTime(timezone=True))`). `created_at`은 `default_factory=now_utc`, `expires_at`은 서비스가 `now_utc()+REFRESH_TOKEN_TTL`로 채움.
- **`token_hash` max_length=64**(sha256 hex 정확히 64자). `user_id`는 `Uuid()` + 명시 `Column(ForeignKey(..., ondelete="CASCADE"), index=True)`(SQLModel `foreign_key=` 단축형은 ondelete 미지원).
- **와이어 snake_case 전 구간 유지**: `access_token`·`refresh_token`·`token_type`·`is_active`·`created_at`(camelCase 변환 레이어 금지, L286).

### 정확한 에러/검증 규약 (AC2/AC5 — 1.5 상속, 이미 시드됨)

- **401 미인증:** `DomainError(ErrorCode.UNAUTHENTICATED, ...)` → 1.5 핸들러가 `{detail:{code:"UNAUTHENTICATED", message}}`(401은 `DEFAULT_STATUS` 기본). **`UNAUTHENTICATED`는 이미 정의·등록**(errors.py L40·L50) — 추가 불필요.
- **403 권한:** `DomainError(ErrorCode.FORBIDDEN_ROLE, ...)` → 403. **`FORBIDDEN_ROLE`도 이미 시드**(L39·L49).
- **로그인은 422를 쓰지 않는다:** `LoginRequest.email`을 `str`(EmailStr 아님)로 둬 형식 위반도 401로 단일화(enumeration·형식 누출 차단). 가입(EmailStr→422)과의 의도된 비대칭.
- **상태코드:** 로그인 성공=**200**(리소스 생성 아님 — register 201과 다름), refresh=200, 로그아웃=**204**, /me=200.

### 현재 코드 상태 — 신규 vs UPDATE (반드시 정독 후 작성/수정)

- **`app/core/security.py`**(45줄, 정독함) — **UPDATE**: `hash_password` 유지, `verify_password` fail-closed 래핑, JWT(create_access/refresh·decode_token·hash_token)·`AuthPrincipal`·`get_current_principal`·`require_role`·상수·쿠키명 추가. **시크릿은 함수 내부 지연 로드**.
- **`app/auth/models.py`**(56줄, 정독함) — **UPDATE**: `RefreshToken` 추가(User/UserRole 보존). import에 `ForeignKey, Uuid` 추가.
- **`app/auth/schemas.py`**(73줄, 정독함) — **UPDATE**: `LoginRequest`·`TokenResponse`·`RefreshRequest`·`LogoutRequest` 추가(RegisterRequest/UserPublic 보존).
- **`app/auth/service.py`**(46줄, 정독함) — **UPDATE**: `authenticate_user`·`issue_token_pair`·`rotate_token_pair`·`revoke_refresh_token`·`get_user_by_id` 추가(register_user·기존 IntegrityError 캐치 보존 — **복사 금지**).
- **`app/auth/router.py`**(38줄, 정독함) — **UPDATE**: login/refresh/logout/me + 쿠키 헬퍼 추가(register 보존). **`main.py` 변경 없음**(auth_router 이미 포함).
- **`app/core/config.py`**(280줄, 정독함) — **UPDATE**: `JWT_SECRET_KEY` 필수 키 + blank validator + min-32 validator + `REQUIRED_KEYS` 동기화(+`_assert_key_lists_match_model` 자동 검사). `.env.example`도 UPDATE.
- **`app/core/errors.py`**(122줄, 정독함) — **참고(변경 없음)**: `ErrorCode.UNAUTHENTICATED`(401·L40)·`FORBIDDEN_ROLE`(403·L39)·`DomainError`·`ErrorResponse`·핸들러 전부 준비됨. 1.8은 **소비만**.
- **`app/core/time.py`**(108줄, 정독함) — **참고(변경 없음)**: `now_utc()`(iat/exp·expires_at·created_at)·`isoformat_utc()`(UserPublic) 사용.
- **`app/core/db.py`**(94줄, 정독함) — **참고(변경 없음)**: `get_session()`(라우터 Depends)·`NAMING_CONVENTION`(제약명 자동)·지연 엔진. `create_all` 금지.
- **`app/main.py`**(88줄, 정독함) — **변경 없음**: auth_router 이미 `api_router`에 포함 → 새 라우트 자동 노출. CORS `allow_credentials=True`(L68, 쿠키 대비) 이미 준비. **보존**.
- **`alembic/env.py`**(98줄, 정독함) — **변경 없음**: `from app.auth import models`(모듈 전체·L51)가 `RefreshToken`을 자동 등록.
- **`tests/test_main.py`**(78줄, 정독함) — **회귀 불변식**: 모듈 레벨 `TestClient(app)` 유지. **바꾸지 말 것**.
- **`pyproject.toml`**(74줄, 정독함) — **변경 없음**: `pyjwt>=2.13.0` 이미 설치(L20). ruff `extend-immutable-calls=[Depends,Security]`(L63, RBAC 의존성 대비) 이미 준비. 새 의존성 없음.

### 모든 신규/수정 모듈 스타일(1.4/1.5/1.7 일관성)

- 헤더 `from __future__ import annotations`, 한국어 모듈 docstring(규약·소비처 명시), 상수 대문자, 타입 주석 명시(mypy strict). `app/{domain}/{models,schemas,service,router}.py` 분리. 새 함수는 ruff(E,F,I,B,UP)·mypy strict(pydantic.mypy) 게이트 통과.

### 흔한 실수 방지 (anti-patterns)

- ❌ refresh 원문/평문 DB 저장 → `hash_token`(sha256) 해시만 저장.
- ❌ `jwt.decode`에 `algorithms` 생략(alg=none 공격) → `algorithms=[JWT_ALGORITHM]` 명시.
- ❌ access를 refresh로(또는 그 반대) 사용 → `type` 클레임 검사(`expected_type`).
- ❌ refresh 토큰에 `jti` 없음(동초 발급 시 해시 충돌) → `jti=uuid.uuid4().hex`.
- ❌ `verify_password`가 손상 해시에 예외(fail-open) → try/except→False(fail-closed).
- ❌ 로그인 실패를 모드별 다른 코드(이메일 미존재 404 등 → enumeration) → **모두 401 UNAUTHENTICATED**.
- ❌ `LoginRequest.email`을 EmailStr로(형식 위반 422 누출) → `str` + 서비스 정규화.
- ❌ 로그아웃이 잘못된/만료 토큰에 401/500 → 멱등 204(decode 없이 해시 삭제만).
- ❌ logout에서 **주입 `response` param**에 쿠키 삭제 후 별도 Response 반환(쿠키 유실) → **반환 Response에 직접** `delete_cookie`.
- ❌ refresh insert에 `except IntegrityError`→EMAIL_TAKEN 복사(register 패턴 오용) → 래핑 금지(jti 충돌 천문학적, 전파).
- ❌ 시크릿을 모듈 레벨 `get_settings()`로 로드(test_main import 깨짐) → 함수 내부 지연 로드.
- ❌ `JWT_SECRET_KEY`를 REQUIRED_KEYS에만(또는 model에만) 추가 → `_assert_key_lists_match_model` RuntimeError. **양쪽 동기화**.
- ❌ test_config의 `REQUIRED_ENV`에 JWT_SECRET_KEY 누락 → 기존 config 테스트가 ValidationError로 깨짐. **함께 추가**(≥32자).
- ❌ JWT_SECRET_KEY <32바이트(InsecureKeyLengthWarning) → validator로 min 32 강제 + 테스트 비밀 ≥32.
- ❌ `main.py`에 새 라우트 배선 추가(이미 auth_router 포함) → 라우터 객체에만 추가.
- ❌ `RefreshToken.user_id`에 `foreign_key=` 단축형 + ondelete 기대(미지원) → 명시 `Column(ForeignKey(..., ondelete="CASCADE"))`.
- ❌ `datetime.now()`로 iat/exp/expires_at → `now_utc()`(1.5 단일 출처).
- ❌ `SQLModel.metadata.create_all()` → Alembic refresh_tokens 단일 마이그레이션(1.4).
- ❌ `register_user`/기존 테스트 변경 → 추가만(회귀 0).

### Testing standards

- 백엔드 pytest, `tests/` 미러 구조(§L253): `tests/core/test_security.py`(UPDATE), `tests/auth/test_{service,router}.py`(UPDATE), `tests/integration/test_auth_session.py`(신규), `tests/core/test_config.py`(UPDATE), `tests/conftest.py`(신규 `auth_env`).
- **단위/라우터 테스트는 라이브 DB 불필요**: JWT/해시는 순수 함수(auth_env로 시크릿만), 서비스는 확장 Fake 세션, 라우터는 `dependency_overrides[get_session]` + `auth_env`. 라이브 DB 왕복은 `TEST_DATABASE_URL` skipif(1.4 패턴).
- **결정성:** 시각 의존은 `now` 주입(만료 토큰=과거 now)으로 결정적 단언. 토큰 문자열 값 비교 금지(디코드 결과·형식만). 쿠키는 `Set-Cookie` 속성(HttpOnly/Secure/SameSite/Max-Age) 단언(실 브라우저 round-trip 아님).
- **conftest 주의:** `auth_env`는 **non-autouse** — test_config(자체 env 조작)·test_main(import 안전)과 무간섭. JWT 만지는 테스트만 명시 요청.
- 게이트: `ruff check`(E,F,I,B,UP) + `mypy --strict`(pydantic.mypy) + `pytest`. 기준선 **86 passed·2 skipped**(1.7 후) → 신규 후 전부 그린.

### Project Structure Notes

- `core/security`·`auth/{models,schemas,service,router}`는 architecture.md 트리(L326-327)에 정확히 정렬. `refresh_tokens`는 §Auth L158("refresh 해시 저장 → 즉시 무효화")·§Naming L230의 산출물.
- **변이/충돌 없음:** 백엔드 전용. 프론트(web/admin/mobile)·`packages/{ui,api-client,config}` 무영향. `main.py`·`env.py`·`pyproject.toml` 변경 없음(라우터 객체·모델 허브·pyjwt 이미 준비).
- import 방향: `router → service → {models, security, schemas, errors}`, `router → security(get_current_principal/require_role)`, `security → {config, errors, time}`. 도메인 모듈 간 직접 import 없음(자기 도메인 내부만 — §L349).

### References

- [Source: epics.md#Story 1.8(L410-436)] — AC 원문(로그인 JWT access+refresh·refresh 해시·쿠키/헤더 이원화·잘못된 자격 401·access 만료 refresh 1회·로그아웃 즉시 무효화·RBAC 403 FORBIDDEN_ROLE·역할 전환 불가).
- [Source: epics.md#FR-2] — 로그인/세션 유지(FR-2), NFR-6(키 격리·평문 금지·토큰 보안).
- [Source: architecture.md#Authentication & Security(L155-166)] — PyJWT+pwdlib(Argon2)·refresh 해시 PG 테이블·토큰 보관 이원화(쿠키/SecureStore)·RBAC JWT role+의존성·백엔드 최종.
- [Source: architecture.md#Naming Patterns(L228-241)] — `refresh_tokens` 복수 snake_case·`*_at` UTC timestamptz·`uq_{table}_{cols}`·`fk_{table}_{col}_{ref}`·201/409/403/401/422.
- [Source: architecture.md#Format/Process/Enforcement(L256-296)] — 에러 `{detail:{code,message}}`·시간 `...Z`·검증 백엔드 최종·와이어 snake_case·인증흐름 "401→refresh 1회 재발급→실패 시 로그인"(L281, 클라이언트는 1.9).
- [Source: architecture.md#Boundaries(L347-360)] — 인증/인가 경계 = core/security 의존성으로 라우터 진입 role 강제(백엔드 최종·L351), service 계층 경유.
- [Source: EXPERIENCE.md L32·L53·L122] — 세션/토큰 이원화(웹 쿠키/RN SecureStore)·로그인=전역 헤더(상세 화면 사양 없음 → 프론트 SDK 1.9 이후)·로그아웃 시 챗봇 대화 초기화(E7).
- [Source: 1-7-이메일-회원가입.md] — core/security 해싱·User/UserRole·register 패턴·EMAIL_TAKEN/검증 핸들러 소비·test_main 불변식·운영DB 미변조 수기 마이그레이션·네이밍 자동 pk/uq.
- [Source: deferred-work.md#1-7] — verify_password fail-closed(1.8 회수)·IntegrityError 과대캐치(refresh FK 주의)·email 정규화 불변식(로그인 조회 .lower()).
- [Source: apps/api/app/core/{security,config,errors,time,db}.py, app/auth/{models,schemas,service,router}.py, app/main.py, alembic/env.py, tests/*, pyproject.toml, alembic/versions/191d9c7dab2d_*.py] — 신규/UPDATE/참고 대상 현 상태(정독 반영).
- [Source: PyJWT 2.13.0 실측] — HS256 cryptography 불필요·`ExpiredSignatureError`/`InvalidSignatureError` ⊂ `InvalidTokenError`·키 <32B `InsecureKeyLengthWarning`·sha256 hex 64자.

## Previous Story Intelligence

- **1.7(회원가입)**: ⓐ **`core/security`는 1.8이 확장**하도록 1.7이 명시 예고(해싱만 두고 JWT/RBAC는 1.8 같은 모듈). ⓑ `verify_password`는 1.8 로그인이 소비 — **시그니처 `verify(password, hash)` 순서**(docstring 오기 주의)·**손상 해시에 예외**(fail-closed 래핑 필요). ⓒ `User`/`UserRole`·`is_active`(로그인 거부용)·`uq_users_email`(정규화 .lower() 조회) 준비됨. ⓓ **`EMAIL_TAKEN`/검증 핸들러처럼 `UNAUTHENTICATED`/`FORBIDDEN_ROLE`도 1.5에 이미 시드** → 1.8은 `raise DomainError(...)`만. ⓔ **운영 Supabase는 베이스라인 미적용** → autogenerate 대신 **수기 마이그레이션 + 오프라인 `--sql`** 검증으로 운영 DB 미변조(1.8 refresh_tokens도 동일 가능). ⓕ 라우터 `Depends`용 ruff `extend-immutable-calls` 이미 설정(RBAC 의존성 그대로 통과). ⓖ test_main 모듈 레벨 TestClient 불변식·`dependency_overrides[get_session]`+`finally clear` 패턴.
- **1.5(횡단 유틸)**: `UNAUTHENTICATED`(401)·`FORBIDDEN_ROLE`(403)·`DomainError`·`ErrorResponse`·전역 핸들러 준비. `now_utc`(iat/exp/expires_at)·`isoformat_utc`(`...Z`). 검증 실패는 Pydantic→422 자동(로그인은 422 회피 위해 email=str).
- **1.4(DB)**: 네이밍 규약 메타등록(제약명 자동 — fk/uq/pk/idx)·Alembic 모델 허브(`app.auth` 모듈 전체 import라 RefreshToken 자동 등록)·`script.py.mako` `import sqlmodel`·지연 엔진(test_main 안전)·`create_all` 금지·autogenerate 라이브 DB 필요(없으면 수기).
- **1.1(설정)**: fail-fast·비밀 마스킹·blank 거부·`_assert_key_lists_match_model` import 검사·`get_settings` lru_cache(cache_clear 테스트). **JWT_SECRET_KEY를 이 패턴에 편입**.
- **공통 환경 학습**: **Windows(cp949)** — `uv run …`, `alembic.ini`/ASCII 주석. 소유자 `.env`는 필수 키 채워짐 + `DATABASE_URL`(Supabase 5432) — **`JWT_SECRET_KEY` 추가 필요**(미추가 시 기동 fail-fast = 의도). 단위/라우터 테스트는 `auth_env`로 시크릿만 주입(라이브 DB 무관).

## Git Intelligence Summary

- Git 저장소 아님(환경: Is a git repository: false). 커밋 이력 분석 불가 — 산출물 파일(1-1~1-7 스토리·deferred-work·architecture·EXPERIENCE)로 학습 대체(위 Previous Story Intelligence).

## Latest Tech Information (2026-06 확인)

- **PyJWT 2.13.0**(설치 확인): `jwt.encode(payload, key, algorithm="HS256") -> str`, `jwt.decode(token, key, algorithms=["HS256"]) -> dict`. **HS256(HMAC)은 `cryptography` extra 불필요**(실측). 예외 계층: `ExpiredSignatureError`·`InvalidSignatureError` ⊂ `InvalidTokenError`(단일 `except jwt.InvalidTokenError`로 만료+위조 포괄 — 실측). `exp`/`iat`는 aware datetime 전달 가능(내부 timestamp 변환), decode 시 exp 자동 검증. **HS256 키 <32바이트 → `InsecureKeyLengthWarning`(RFC 7518 §3.2)** → `JWT_SECRET_KEY` min 32 강제. [PyJWT api_jwt.py 실측]
- **refresh 토큰 해시**: `hashlib.sha256(token.encode()).hexdigest()` → **64자 hex**(컬럼 max_length=64). 원문 대신 해시 저장이 표준(DB 유출 내성). `jti`(`uuid.uuid4().hex`, 32자)로 발급 고유성. [hashlib·실측]
- **FastAPI 쿠키**: `response.set_cookie(key, value, httponly=True, secure=True, samesite="lax", path=..., max_age=...)`. **주입된 `response: Response` param에 set하면 모델 반환과 병합**되나, **별도 `Response()`를 반환하면 그 객체에 직접 set**해야 한다(logout). `delete_cookie(key, path=...)`는 만료 Set-Cookie를 내보낸다(path 일치 필요). [FastAPI/Starlette]
- **SQLModel FK/timestamptz**: `Field(sa_column=Column(Uuid(), ForeignKey("users.id", ondelete="CASCADE"), index=True))` — `foreign_key=` 단축형은 ondelete 미지원이라 명시 Column 사용. timestamptz는 `Column(DateTime(timezone=True))`. 네이밍 규약(metadata)이 fk/uq/idx 이름 부여. [SQLModel/SQLAlchemy 2.0]

**Sources:**
- [PyJWT (PyPI/GitHub) 2.x — encode/decode/InvalidTokenError·InsecureKeyLengthWarning] · 로컬 `.venv/.../jwt/api_jwt.py` 실측
- [FastAPI — Response Cookies / Depends] · [Starlette Response.set_cookie/delete_cookie]
- [SQLModel — Relationships/Foreign Keys] · [SQLAlchemy 2.0 — Uuid/ForeignKey(ondelete)/DateTime(timezone)]
- [RFC 6750 Bearer / RFC 7518 §3.2 HMAC key length]

## Project Context Reference

- 프로젝트 컨텍스트 파일(`**/project-context.md`) 없음 — architecture.md가 결정·패턴·경계의 1차 출처(§Enforcement L283-296: 와이어 snake_case·UTC 저장/ISO `...Z`·에러코드 상수·검증 백엔드 최종·프론트 SDK 경유는 1.9). 인증/보안은 §Authentication & Security(L155-166): JWT(access+refresh)·refresh 해시 무효화·토큰 이원화·RBAC 백엔드 최종·키 격리. 인증/인가 경계는 §Boundaries L351(core/security 의존성).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Claude Opus 4.8, 1M context) — BMad dev-story 워크플로

### Debug Log References

- **실측 검증(구현 전):** PyJWT 2.13.0 — `ExpiredSignatureError`·`InvalidSignatureError` ⊂ `InvalidTokenError`(단일 except 포괄 확인). pwdlib `verify`는 손상/빈 해시에 `UnknownHashError` **예외**(False 아님) → fail-closed 래핑 정당성 실증. `hashlib.sha256().hexdigest()` = 64자.
- **마이그레이션 오프라인 검증:** `alembic upgrade 191d9c7dab2d:head --sql`로 운영 DB 미접근 DDL 확인 — `pk_refresh_tokens`·`fk_refresh_tokens_user_id_users (ON DELETE CASCADE)`·`uq_refresh_tokens_token_hash`·`idx_refresh_tokens_user_id` 규약명 정확, `expires_at`/`created_at` = `TIMESTAMP WITH TIME ZONE`, refresh_tokens 단일 테이블만 추가.
- **FakeSession 확장:** SQLAlchemy `statement.column_descriptions[0]["entity"]`(엔티티 분기) + `statement.whereclause.right.value`(token_hash 값 추출)로 User/RefreshToken 조회를 구분하도록 실측 후 구현(register 테스트 하위호환 보존).
- **게이트 진행:** Task별 부분 실행(config 28 → security 20 → service 17 → router 14 passed) 후 전체 그린. ruff 3건(B008 require_role inline·I001 정렬·E501 한글 docstring) 수정.
- **최종 회귀에서 플레이키 1건 적발·수정:** `test_decode_forged_token_raises_401`이 JWT 서명 **마지막 base64url 글자(4비트 데이터 + 2비트 패딩)** 변조 시 패딩 비트만 바뀌어 서명 바이트가 동일해질 수 있어(토큰 끝이 'a'→'b'처럼 같은 상위 4비트면) 비결정적 통과 → **다른 시크릿으로 서명한 토큰**으로 `InvalidSignatureError`를 결정적으로 유발하도록 수정. 수정 후 5회 반복 + 전체 2회 연속 그린(131 passed·3 skipped)으로 결정성 확인.

### Completion Notes List

- **범위 충실 이행 — 백엔드 인증/인가만(UPDATE 중심, 신규 모듈 0).** 프론트 로그인 UI·401→refresh 자동 재시도 인터셉터(→1.9 SDK), 챗봇 세션 종료(→E7), 계정 비활성화 동작·시드 관리자(→E8)는 의도적으로 제외. `refresh_tokens` 1 테이블만 신규(두 번째 도메인 테이블·첫 FK).
- **AC1(로그인·토큰 이원화):** `POST /auth/login` 200 + `TokenResponse`(본문) + httpOnly·Secure·SameSite 쿠키(access path=`/`, refresh path=`/api/v1/auth`) 동시 발급. refresh **해시만** `refresh_tokens` 저장(원문 미저장). `get_current_principal`이 헤더 우선·쿠키 폴백으로 access 추출.
- **AC2(잘못된 자격):** 미존재·틀린 비번·비활성 **세 모드 동일 401 `UNAUTHENTICATED`**(enumeration 차단). `LoginRequest.email`을 `str`(EmailStr 아님)로 둬 형식 위반도 401로 단일화.
- **AC3(만료·회전):** `POST /auth/refresh`가 JWT 디코드(stateless) + DB 해시 조회(stateful) 이중 검증 후 옛 행 삭제 + 새 쌍 발급(회전, 같은 commit). 만료/위조/회전·로그아웃됨 → 401. 회전된 refresh 재사용 → 401(통합테스트 실증).
- **AC4(로그아웃·멱등):** `POST /auth/logout` 204, **decode 없이** 해시로만 행 삭제 + 쿠키 제거(반환 Response에 직접 `delete_cookie`). 토큰 부재·무효·손상에도 204(멱등).
- **AC5(RBAC):** `require_role(*roles)` 의존성이 백엔드 최종 강제 — 미허용 역할 403 `FORBIDDEN_ROLE`, 토큰 없음 401 `UNAUTHENTICATED`. 미니앱으로 provider 200·booker 403·무토큰 401 + 쿠키/헤더 양쪽 실증(실 도메인 라우터는 E2/E8).
- **핵심 함정 처리:** ① `JWT_SECRET_KEY` 필수 + min32 validator(blank validator 선처리·`_assert_key_lists_match_model` 동기화) ② `verify_password` fail-closed 래핑(1.7 deferred 회수) ③ logout 반환 Response 쿠키 ④ `test_config` `REQUIRED_ENV`에 JWT_SECRET_KEY(≥32) 동기화 ⑤ JWT 함수 시크릿 **함수 내부 지연 로드**(test_main 모듈레벨 TestClient 불변식 보존) ⑥ `jti`로 refresh 해시 고유성 ⑦ `jwt.decode` `algorithms` 명시(alg=none 공격 차단, 테스트로 실증) ⑧ IntegrityError 과대캐치 회피(register 패턴 미복사).
- **운영 영향(소유자 안내):** `JWT_SECRET_KEY`가 필수가 되어 소유자 `.env`에 추가(생성: `python -c "import secrets; print(secrets.token_urlsafe(48))"`) 전엔 앱 기동·통합테스트가 fail-fast(의도). `refresh_tokens`는 `uv run alembic upgrade head`로 적용. README·.env.example에 명시.
- **무회귀:** 백엔드 전용(프론트 web/admin/mobile·packages 무영향). `main.py`·`env.py`·`pyproject.toml` 변경 없음. `test_main` 모듈레벨 TestClient 불변식·register/users/config 기존 동작 보존. `test_auth_migration.py`에 JWT_SECRET_KEY 추가(Task 1 회귀 가드).
- **게이트:** `ruff check`(E,F,I,B,UP) ✅ · `mypy --strict`(pydantic.mypy, 19 files) ✅ · `pytest` **131 passed · 3 skipped**(기준선 86 passed·2 skipped → +45 passed, +1 live-DB skip). 3 skip = `test_migrations`·`test_auth_migration`·`test_auth_session`(전부 `TEST_DATABASE_URL` 가드).

### File List

**신규(3):**
- `apps/api/tests/conftest.py` — 공유 `auth_env` 픽스처(non-autouse, 5필수키 주입)
- `apps/api/tests/integration/test_auth_session.py` — refresh_tokens 마이그레이션 + 세션 왕복(skipif)
- `apps/api/alembic/versions/ac9b81f7d058_create_refresh_tokens_table.py` — refresh_tokens 마이그레이션(down_revision=191d9c7dab2d)

**수정(13):**
- `apps/api/app/core/config.py` — `JWT_SECRET_KEY` 필수 키 + blank·min32 validator + REQUIRED_KEYS 동기화
- `apps/api/app/core/security.py` — JWT create/decode·hash_token·verify_password fail-closed·AuthPrincipal·get_current_principal·require_role·상수·쿠키명
- `apps/api/app/auth/models.py` — `RefreshToken` 모델(+ ForeignKey, Uuid import)
- `apps/api/app/auth/schemas.py` — LoginRequest·TokenResponse·RefreshRequest·LogoutRequest
- `apps/api/app/auth/service.py` — authenticate_user·issue_token_pair·rotate_token_pair·revoke_refresh_token·get_user_by_id
- `apps/api/app/auth/router.py` — login(200)·refresh·logout(204)·me + 쿠키 헬퍼(register 보존)
- `apps/api/.env.example` — `JWT_SECRET_KEY` [필수] 섹션 추가(생성법·플레이스홀더)
- `apps/api/README.md` — "인증 — 로그인/세션/RBAC(Story 1.8)" 섹션
- `apps/api/tests/core/test_config.py` — REQUIRED_ENV에 JWT_SECRET_KEY + min-length/마스킹 테스트
- `apps/api/tests/core/test_security.py` — fail-closed·JWT·만료·타입교차·위조·alg=none·hash_token·RBAC 미니앱
- `apps/api/tests/auth/test_service.py` — FakeSession 확장 + authenticate/issue/rotate/revoke/get_user_by_id
- `apps/api/tests/auth/test_router.py` — login/refresh/logout/me + 쿠키 단언
- `apps/api/tests/integration/test_auth_migration.py` — JWT_SECRET_KEY env 추가(Task 1 회귀 가드)

## Change Log

- 2026-06-15: Story 1.8 code-review 완료(→done). 3-레이어 적대적 병렬 리뷰(Blind Hunter·Edge Case Hunter·Acceptance Auditor, claude-opus-4-8[1m]). **Acceptance Auditor: AC1~5 전부 PASS·스코프 크리프 0·안티패턴 전부 준수.** 게이트 실측 일치(131 passed·3 skipped). 트리아지: **patch 2·defer 12·dismiss 8**. 세 레이어 수렴 핵심 = 서명 유효·클레임 손상 토큰의 미처리 500(모듈 계약 "모든 토큰 문제→401" 위반). **patch 2건 적용**: ① `decode_token`에 `options={"require":["exp","type","sub"]}` + `get_current_principal`/`rotate_token_pair`의 `uuid.UUID(sub)`·`role` 추출 가드 → 손상 클레임 401화(`security.py`·`service.py`) ② `_extract_access_token` 분기 테스트(소문자 bearer·빈 Bearer 쿠키폴백·헤더 우선) + 손상클레임 401 회귀 테스트 7건 추가(`test_security.py`). 게이트 재그린: ruff·mypy(19 files)·pytest **131→138 passed·3 skipped**. defer 12건 deferred-work.md 기록(회전 동시성 더블스펜드·expires_at 미사용·access 즉시취소지연(E8)·재사용탐지·세션상한·CSRF·SameSite/Secure 쿠키(1.9/배포)·유니코드 이메일(1.7)·delete_cookie 속성·Argon2 타이밍 enumeration[권장]·FakeSession 충실도). 백엔드 전용 무회귀.
- 2026-06-15: Story 1.8 dev-story 완료(→review). 백엔드 로그인/로그아웃/세션/RBAC 구현 — Task 1~9 전부 완료(71/71 서브태스크). **config**: `JWT_SECRET_KEY` 필수+min32 validator+REQUIRED_KEYS 동기화. **core/security**: JWT create_access/refresh·decode_token(만료·위조·타입교차→401·alg 명시)·hash_token(sha256 64)·verify_password fail-closed 래핑(1.7 deferred 회수)·AuthPrincipal·get_current_principal(헤더우선·쿠키폴백)·require_role(403). **auth/models**: `RefreshToken`(2번째 도메인 테이블·첫 FK, 해시 저장·CASCADE). **auth/schemas**: Login/Token/Refresh/Logout(LoginRequest.email=str로 401 단일화). **auth/service**: authenticate(3모드 동일 401)·issue/rotate(회전)·revoke(멱등)·get_user_by_id. **auth/router**: login 200·refresh·logout 204 멱등·me + 쿠키 이원화(웹 httpOnly·RN 본문). **마이그레이션** `ac9b81f7d058`(down_revision=191d9c7dab2d, 오프라인 --sql 검증). AC1~5 충족. 게이트 그린: ruff·mypy(19 files)·pytest **86→131 passed·2→3 skipped**. 백엔드 전용 무회귀(main/env/pyproject 불변·test_main 불변식 보존). 운영: `JWT_SECRET_KEY` .env 추가 + `alembic upgrade head` 필요(README·.env.example 명시).
- 2026-06-15: Story 1.8 create-story 완료(ready-for-dev). Ultimate context engine 분석 — 백엔드 로그인/로그아웃/세션/RBAC 범위 확정(프론트 인증 UI·자동재발급 인터셉터는 SDK 1.9 이후, 챗봇 세션 종료는 E7로 명시 이관). **UPDATE 중심**(신규 모듈 0): `core/config`(JWT_SECRET_KEY 필수·min32)·`core/security`(JWT create/decode·hash_token·verify_password fail-closed·AuthPrincipal·get_current_principal·require_role)·`auth/models`(RefreshToken — 2번째 도메인 테이블·첫 FK)·`auth/schemas`(Login/Token/Refresh/Logout)·`auth/service`(authenticate/issue/rotate/revoke/get_user_by_id)·`auth/router`(login 200·refresh·logout 204 멱등·me + 쿠키 이원화). 신규 1: `refresh_tokens` 마이그레이션(down_revision=191d9c7dab2d). 핵심 함정 명시(JWT_SECRET_KEY<32B 경고·verify fail-closed·logout 반환 Response 쿠키·test_config key_lists 동기화·JWT 테스트 conftest auth_env·jti 해시 고유성·alg 명시·로그인 401 단일화). 1.5 인프라(UNAUTHENTICATED/FORBIDDEN_ROLE/DomainError/핸들러)·1.7 자산(verify_password/User/is_active/네이밍 규약) 소비. PyJWT 2.13.0 실측(HS256 cryptography 불필요·예외 계층·키 길이 경고·sha256 64자).
