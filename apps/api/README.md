# desknow-api

desknow 백엔드 API (FastAPI + PostgreSQL/pgvector + SQLModel + Alembic).

## 환경 점검 (키 로드 검증)

```bash
uv sync
cp .env.example .env   # 이후 실제 키 값 입력 (docs/external-services-setup.md 참고)
uv run python -m app.core.config --check
```

- 필수 키 누락 시: 어떤 키가 빠졌는지 출력하며 **fail-fast**(종료 코드 1).
- 모든 필수 키 존재 시: 마스킹된 값과 함께 정상 출력(종료 코드 0).

## 데이터베이스 (Story 1.4)

`DATABASE_URL`은 **Story 1.4부터 필수**입니다(미설정 시 기동 fail-fast).

- **스킴**: provider 콘솔이 주는 `postgresql://`·`postgres://`를 그대로 붙여도 됩니다 —
  psycopg3 드라이버용 `postgresql+psycopg://`로 **자동 정규화**됩니다. PostgreSQL이
  아니면 기동 시 거부합니다.
- **개발 DB = Supabase 권장**: Supabase 콘솔 → Project Settings → Database →
  Connection string. ⚠️ **직접 연결 또는 Session pooler의 5432 포트**를 사용하세요.
  Transaction pooler(6543)는 prepared statement/세션 상태를 끊어 Alembic 마이그레이션·
  일부 psycopg3 기능이 깨집니다.
- **기동 검증**: 앱 startup(lifespan)에서 `SELECT 1` 연결 + pgvector 확장 존재를
  검증하고, 실패 시 한국어 actionable 오류로 fail-fast 합니다.

### 마이그레이션 (Alembic)

스키마는 **Alembic이 단독 소유**합니다(`SQLModel.metadata.create_all` 사용 금지).
도메인 테이블은 각 스토리가 점진적으로 추가하며, 베이스라인은 **빈 스키마 + pgvector
확장만** 활성화합니다.

```bash
uv run alembic upgrade head                          # 마이그레이션 적용 (확장 활성화)
uv run alembic revision --autogenerate -m "메시지"   # (후속) 모델 변경으로부터 마이그레이션 생성
uv run alembic downgrade -1                           # 직전 마이그레이션 되돌리기
```

> 후속 스토리는 `app/{domain}/models.py`에 모델을 정의하고 `alembic/env.py`의 **모델
> import 허브**에서 import 해야 autogenerate가 인식합니다. 컬럼/제약 네이밍은
> `app/core/db.py`의 `NAMING_CONVENTION`(메타데이터 등록)을 자동으로 따릅니다.

## 횡단 유틸 (Story 1.5)

### 시간 규약 — UTC 저장 / KST 판정 (`app/core/time.py`)

**저장·전송은 UTC(tz-aware)**, **"오늘/현재/N시간" 판정은 룸 타임존(MVP=`Asia/Seoul`)**
이 단일 출처입니다. 날짜 경계는 절대 프로세스/클라이언트 로컬 타임존에 의존하지 않습니다.
naive datetime은 `ValueError`로 거부합니다. (런타임 의존성 `tzdata`로 Windows·슬림
컨테이너의 tz DB 부재를 차단합니다.)

```python
from app.core.time import now_utc, today_in_tz, is_within_hours, isoformat_utc

today_in_tz()                       # 룸(KST) 기준 "오늘" date — FR-5 핀색 전제
is_within_hours(reservation.start, 6)   # 시작 6h 이내? — FR-16 취소 차단 / FR-18 리마인드(24)
isoformat_utc(now_utc())            # '2026-06-14T05:00:00Z' (와이어 규약 ...Z)
```

도메인 코드는 `datetime.now()`를 직접 부르지 말고 `now_utc()`만 씁니다(결정성). 판정
함수는 테스트 결정성을 위해 `now`를 주입받습니다.

### 표준 에러 스키마 (`app/core/errors.py`)

도메인 오류는 `DomainError`로 던지면 전역 핸들러가 표준 스키마
`{"detail": {"code": "...", "message": "..."}}`로 응답합니다. 에러코드는 상수
(`ErrorCode` StrEnum)로만 사용하며 문자열 하드코딩은 금지입니다. 상태 매핑(`DEFAULT_STATUS`):
동시성/상태충돌=409, 권한=403, 미인증=401, 검증=422.

```python
from app.core.errors import DomainError, ErrorCode

raise DomainError(ErrorCode.SLOT_CONFLICT, "이미 예약된 슬롯입니다.")   # → 409 표준 스키마
# OpenAPI 노출: @router.post(..., responses={409: {"model": ErrorResponse}})
```

핸들러는 `app/main.py`가 `register_exception_handlers(app)` 한 줄로 배선합니다
(`DomainError` + `RequestValidationError`만 표준화 — 라우팅 404/405는 프레임워크 기본 유지).

## 인증 — 회원가입 (Story 1.7)

`POST /api/v1/auth/register` — 이메일·비밀번호·역할(`booker`/`provider`)로 계정을 만듭니다.
비밀번호는 **pwdlib + Argon2**(`app/core/security.py`)로 해싱해 `password_hash`에만 저장하며
**평문은 절대 저장하지 않습니다**(NFR-6). `users`는 첫 도메인 테이블입니다.

```jsonc
// 요청 (snake_case, 와이어 규약)
{ "email": "user@example.com", "password": "Test1234!", "role": "booker" }

// 201 Created — 사용자 리소스(password_hash 비노출, created_at은 ...Z)
{ "id": "…uuid…", "email": "user@example.com", "role": "booker",
  "is_active": true, "created_at": "2026-06-15T05:00:00Z" }
```

- **검증(백엔드가 신뢰 경계)**: 이메일 형식 위반·비밀번호 정책(최소 8자 + 대문자·숫자·
  특수문자 각 1개 — FR-3) 위반·`role` 위반은 모두 **422 `VALIDATION_ERROR`**(표준 에러 스키마).
- **중복 차단**: 이미 가입된 이메일(대소문자 무관)은 **409 `EMAIL_TAKEN`**. 이메일은 소문자
  정규화 저장하며, `users.email`의 **UNIQUE 제약(`uq_users_email`)이 진실의 원천**입니다
  (서비스 선검사 + 경합 시 `IntegrityError`→`EMAIL_TAKEN` 이중 방어).
- `admin` 역할은 가입으로 만들 수 없습니다(시드 전용). JWT 발급·로그인·RBAC는 Story 1.8입니다.

> `users` 테이블은 마이그레이션으로 생성됩니다 — `uv run alembic upgrade head`를 먼저 실행하세요.

## 인증 — 로그인 / 세션 / RBAC (Story 1.8)

단일 백엔드 발급 **JWT(HS256)** 로 세션을 유지합니다 — **access 단기(15분) + refresh 장기
(14일)**. refresh는 **원문이 아니라 sha256 해시**만 `refresh_tokens` 테이블에 저장하며
(DB 유출 내성), 로그아웃·회전 시 행을 삭제해 **즉시 무효화**합니다.

> **`JWT_SECRET_KEY` 필수(Story 1.8부터)** — access/refresh 서명 키(백엔드 전용 비밀, **≥32자**).
> 누락/빈 값/32자 미만이면 기동 fail-fast 합니다. 생성:
> `python -c "import secrets; print(secrets.token_urlsafe(48))"` → `.env`에 추가.
> `refresh_tokens` 테이블은 마이그레이션으로 생성됩니다 — `uv run alembic upgrade head` 실행.

| 엔드포인트 | 동작 | 성공 |
|------------|------|------|
| `POST /api/v1/auth/login` | 이메일·비밀번호 로그인 → 토큰 쌍 발급 | **200** + `TokenResponse` |
| `POST /api/v1/auth/refresh` | 유효 refresh로 새 쌍 **회전** 발급(기존 무효화) | **200** + `TokenResponse` |
| `POST /api/v1/auth/logout` | refresh 해시 행 삭제 + 쿠키 제거(**멱등**) | **204** |
| `GET /api/v1/auth/me` | 현재 인증 사용자 조회(인증 필요) | **200** + `UserPublic` |

```jsonc
// POST /auth/login 요청
{ "email": "user@example.com", "password": "Test1234!" }
// 200 — 토큰 쌍(snake_case). 웹은 쿠키로도 동시 수신.
{ "access_token": "eyJ…", "refresh_token": "eyJ…", "token_type": "bearer" }
```

- **토큰 보관 이원화**: **웹 = httpOnly+Secure+SameSite 쿠키**(`desknow_access` path=`/`,
  `desknow_refresh` path=`/api/v1/auth`) / **RN = 응답 본문 → SecureStore → `Authorization: Bearer`**.
  백엔드 인증 의존성은 **헤더 우선·쿠키 폴백**으로 access 토큰을 추출합니다.
- **잘못된 자격(미존재·틀린 비번·비활성)** 은 세 모드 모두 **동일한 401 `UNAUTHENTICATED`**
  (계정 존재 여부 노출=enumeration 차단). 로그인은 이메일 형식 위반도 401로 단일화합니다.
- **회전(rotation)**: refresh 사용 시 옛 행 삭제 + 새 쌍 발급 → refresh 1회용화. 만료·위조·
  회전/로그아웃된 refresh는 **401**. *(클라이언트의 401→refresh 자동 1회 재시도 인터셉터는
  SDK(Story 1.9) 이후 프론트 작업 — 본 스토리는 백엔드 refresh 엔드포인트만.)*
- **RBAC**: `app/core/security.py`의 `require_role(*roles)` 의존성이 **백엔드 최종 강제**합니다
  — 권한 없는 역할은 **403 `FORBIDDEN_ROLE`**, 토큰 없으면 **401 `UNAUTHENTICATED`**. 역할은
  JWT `role` 클레임 + FastAPI 의존성으로 강제하며 **가입 시 확정·전환 불가**입니다.

```python
# 향후 도메인 라우터의 RBAC 소비 예(E2 rooms=provider, E8 admin)
from app.core.security import require_role

require_provider = require_role("provider")   # 의존성을 한 번 만들어 재사용

@router.post("/rooms")
def create_room(principal = Depends(require_provider), ...): ...   # booker → 403
```

> **프론트 로그인/계정 UI + 401→refresh 자동 재시도 인터셉터는 본 스토리 범위가 아닙니다**
> (생성 SDK 경유 — Story 1.9 이후). 챗봇 대화 세션 종료(로그아웃 연동)는 Epic 7,
> 계정 비활성화 동작·시드 관리자는 Epic 8입니다. 1.8은 로그인 시 `is_active` 거부 +
> `require_role` 의존성만 제공합니다.

## 운영 (관리자) — Epic 8

관리자(시드 운영자) 전용 표면입니다. 관리자는 **가입으로 생성할 수 없습니다**(`POST /auth/register`가
`role="admin"`을 422 거부) — 아래 시드 스크립트가 유일한 정당 생성 경로입니다.

- **`GET /api/v1/admin/accounts`** (Story 8.1): `require_role("admin")` 가드. 예약자·제공자 계정
  목록(이메일·역할·활성여부·가입일)을 **페이지네이션**(`page`≥1, `page_size` 1~100, 기본 20)으로
  반환합니다. 정렬은 `created_at` 내림차순 + `id`(동률 안정화). 비-admin은 **403 `FORBIDDEN_ROLE`**,
  토큰 없으면 **401 `UNAUTHENTICATED`**. *(인제스트=8.4.)*

- **`GET /api/v1/admin/reservations`** (Story 8.3): `require_role("admin")` 가드. **확정
  (`confirmed`) 예약만** 목록(룸 이름·예약자 실 이메일·점유 슬롯 시각 스냅샷·생성일)을
  **페이지네이션**(`page`≥1, `page_size` 1~100, 기본 20)으로 반환합니다. 정렬은 `created_at` 내림차순
  + `id`(동률 안정화), 룸/예약자는 배치 조회로 합성(N+1 회피). 운영자라 예약자 **실 이메일**을
  노출합니다(provider 표면의 익명 라벨이 아님 — accounts 정합). 비-admin **403 `FORBIDDEN_ROLE`**,
  무토큰 **401 `UNAUTHENTICATED`**.

- **`POST /api/v1/admin/reservations/{reservation_id}/cancel`** (Story 8.3): `require_role("admin")`
  가드. 확정 예약을 **임의 취소**합니다 — 동일 트랜잭션에서 ① `status`를 `cancelled`로 전이 ②
  점유 `reservation_slots` 행을 **DELETE해 슬롯 재활성**(가용성 집계에서 즉시 재예약 가능) ③
  예약자에게 `status_change`/`reason="cancelled"` 통지 1건 생성. **시간 게이트 없음**(admin 권한 —
  booker 6h·provider 시작전 윈도우를 우회해 시작된/지난 예약도 취소). **멱등**(이미 종료 상태 재호출
  = 추가 효과 0, 200). 미존재 예약은 **404 `RESERVATION_NOT_FOUND`**(누설 방지), 비-admin **403
  `FORBIDDEN_ROLE`**, 무토큰 **401 `UNAUTHENTICATED`**.

  > **통지 원자화(retry-safe — 6.2 거절도 적용):** 거절(6.2)·임의취소(8.3) 통지는 이제 상태 전이·
  > 슬롯 재활성과 **단일 트랜잭션**에 묶입니다(통지 INSERT가 전이 commit과 한 번에). 통지 실패 시
  > 전이도 롤백되고 재시도가 전부 재수행되므로, 예전의 "전이는 영속인데 통지는 별도 트랜잭션 실패로
  > 영구 손실" 문제가 제거됩니다(`reservations.service`의 `_transition_to_terminal` `notify_reason`).

- **`POST /api/v1/admin/accounts/{account_id}/deactivate`** (Story 8.2): `require_role("admin")`
  가드. 대상 계정의 `User.is_active`를 `false`로 전이하고(**조건부 원자 UPDATE**), provider면 같은
  트랜잭션에서 그의 룸(`is_active=false`)까지 **캐스케이드**합니다 → 지도/목록/반경/지역 **노출
  중단** + **신규 예약 차단**(기존 노출 쿼리·`_get_active_room_or_404`가 자동 처리), **기존 확정
  예약은 유지**(reservations/슬롯 미터치 — 예약 임의취소는 8.3). **멱등**(이미 비활성 계정 재호출 =
  추가 쓰기 없이 200). **비활성 단방향**(재활성 엔드포인트 없음). 대상이 admin(자기 자신 포함)이거나
  미존재면 **404 `ACCOUNT_NOT_FOUND`**(존재 누설 방지), 비-admin **403 `FORBIDDEN_ROLE`**, 무토큰
  **401 `UNAUTHENTICATED`**. *서비스 이용 차단은 **최종 강제(≤15분)** — 인증 핫패스는 stateless
  유지이고, 발급된 access 토큰(15분)은 만료까지 유효하나 refresh 갱신이 거부되어(1.8) 만료 후
  세션 연장이 불가합니다.*

- **`POST /api/v1/admin/ingest`** (Story 8.4): `require_role("admin")` 가드. 고정 디렉터리
  **`apps/api/docs_corpus/`**(UI 업로드 아님 — 디렉터리 배치 후 트리거)의 문서를 7.2 코어
  파이프라인(`ingest_corpus`)으로 임베딩해 pgvector(`document_chunks`)에 **멱등하게** 적재합니다
  (내용 sha256이 같으면 재임베딩 스킵·OpenAI 호출 0, 바뀌면 기존 청크 전량 교체). 처리는
  **동기**(잡 큐·폴링 없음 — 라우터는 `def` 핸들러라 FastAPI 스레드풀에서 실행)이고, 완료 시
  **처리 리포트**(`succeeded`/`skipped`/`failed`/`removed` + `total`)를 200으로 즉시 반환합니다.
  부분 실패는 배치를 중단시키지 않고 `failed: [{path, reason}]`로 식별되며, **corpus에서
  삭제/리네임된 문서의 stale 청크는 정리(reconcile)** 되어 `removed`로 보고됩니다(corpus 파일이
  하나도 없으면 reconcile를 스킵해 전체 wipe를 방지). 비-admin **403 `FORBIDDEN_ROLE`**, 무토큰
  **401 `UNAUTHENTICATED`**(per-doc 실패는 본문 사유라 엔드포인트 자체는 200). CLI
  `scripts/ingest_docs.py`도 같은 파이프라인(reconcile 포함)을 수동/개발 실행으로 제공합니다.

### 시드 관리자 부트스트랩

`SEED_ADMIN_EMAIL`/`SEED_ADMIN_PASSWORD`를 `.env`(또는 환경변수)에 설정한 뒤 1회 실행합니다.
**앱 기동과 무관**한 선택 키이며(운영 비밀이므로 라이브는 `.env`/Railway 변수로만 주입), 멱등합니다
(재실행 시 비밀번호만 로테이션 — 중복 행 없음). 이미 booker/provider로 존재하는 이메일은 admin으로
**승격하지 않습니다**(거부).

```bash
python scripts/seed_admin.py          # 또는 uv run python scripts/seed_admin.py
```

## 테스트

```bash
uv run ruff check . && uv run mypy && uv run pytest
```

라이브 DB가 필요한 마이그레이션 왕복 통합 테스트는 `TEST_DATABASE_URL` 환경변수가
설정된 경우에만 실행되며, 미설정 시 자동 skip 됩니다.
