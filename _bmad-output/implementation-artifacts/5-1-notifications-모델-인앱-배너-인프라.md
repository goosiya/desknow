---
baseline_commit: NO_VCS
---

# Story 5.1: notifications 모델 & 인앱 배너 인프라

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 개발자,
I want 인앱 배너의 데이터 모델(`notifications` 테이블)과 전역 배너 컴포넌트·조회/소멸 인프라를 두길,
so that 도래 리마인드(5.2)·상태변경 통지(5.3/6.2/8.3)가 접속 시점에 표시되고 사용자별로 영속 관리된다 (UX-DR5, FR-18/18a 인프라, NFR 시간규약).

이 스토리는 **Epic 5의 첫 스토리이자 인프라 스토리**다. Epic 4의 `reservations` foundation(4.1)과 동형 — 데이터 계층 + 서비스 프리미티브 + 전역 컴포넌트를 세우고, **실제 트리거는 후속에 위임**한다:
- **도래 리마인드 도출**(24h 이내 확정 예약 → 배너) + '다시 보지 않기' = **Story 5.2**
- **상태변경 통지 생성**(거절 FR-24 / 임의취소 FR-32 시점에 행 생성) = **Story 6.2 / 8.3 배선**, 표시·'확인'은 **Story 5.3**

## Acceptance Criteria

(epics.md Story 5.1 BDD + KTH 확정 3건 기반)

**AC1 — 데이터 모델**
**Given** `notifications` 테이블(통합 모델 + `type` 판별자)
**When** 마이그레이션을 적용하면
**Then** `id·user_id(FK→users)·type('reservation_reminder'|'status_change')·reservation_id(FK→reservations)·reason(nullable)·created_at(UTC)·dismissed_at(nullable UTC)` 컬럼과 `UNIQUE(user_id, reservation_id, type)`(명시 단축명, ≤63자)이 존재한다. 라이브 Supabase에도 `alembic upgrade head`가 실제 적용된다. [[dev-workflow-policy-live-db-migration]]

**AC2 — 서비스 프리미티브 (생성/조회/소멸)**
**Given** 서비스 계층
**When** 통지를 생성·조회·소멸하면
**Then** `create_notification`(멱등 — `UNIQUE` 위반 시 기존 행 반환), `list_pending(user_id)`(= `dismissed_at IS NULL` 행만, 최신순), `dismiss_notification(user_id, notification_id)`(소유권 검증 + `dismissed_at` 설정·멱등)이 동작한다. 점유/상태 도메인 침범 없이 자기완결.

**AC3 — 조회/소멸 엔드포인트 + SDK**
**Given** REST 표면
**When** 접속 시 표시할 통지를 조회하거나 소멸하면
**Then** `GET /api/v1/notifications`(본인 미확인 목록·로그인 필요) + `POST /api/v1/notifications/{notification_id}/dismiss`(멱등·소유권)가 동작하고, `packages/api-client` SDK가 재생성되어 OpenAPI 드리프트 게이트(Layer A·B)가 그린이다.

**AC4 — 전역 배너 컴포넌트 (표시)**
**Given** `notifications` 테이블과 전역 배너 컴포넌트
**When** 접속 시 표시할 배너가 있으면(미확인 통지가 GET에서 ≥1건)
**Then** 면 위 플랫(`bg-secondary`/`bg-muted` 배경 + 아이콘 + 텍스트)으로 표시되고, 출현이 aria-live로 안내된다(푸시 아님 — 접속 시점에만). 색 단독 금지(아이콘+텍스트 병행), 닫기 버튼 ≥44px. 미로그인/통지 0건이면 슬롯은 공간을 차지하지 않는다(`empty:hidden` 보존).

**AC5 — 소멸 영속 (사용자별)**
**Given** 배너 상태
**When** '다시 보지 않기' 또는 '확인'을 하면(둘 다 단일 generic dismiss 프리미티브 소비)
**Then** 사용자별 상태가 영속되어(`dismissed_at` 설정) 해당 배너가 더는/소멸 처리되고, 같은 사용자 재접속 시 다시 뜨지 않는다.

## Tasks / Subtasks

- [x] **Task 1 — `notifications` 모델 + 마이그레이션 (AC1)**
  - [x] `apps/api/app/notifications/__init__.py` 도크스트링 갱신(빈 골격 → Story 5.1 인프라)
  - [x] `apps/api/app/notifications/models.py`: `Notification` SQLModel + `NotificationType(StrEnum)` (`RESERVATION_REMINDER="reservation_reminder"`, `STATUS_CHANGE="status_change"`). 컬럼: `id`(uuid PK), `user_id`(FK→users, RESTRICT, index), `reservation_id`(FK→reservations, **CASCADE** — 예약 행 삭제 시 통지 무의미), `type`(str + CHECK), `reason`(str nullable — 'rejected'|'cancelled'), `created_at`(now_utc, timestamptz), `dismissed_at`(timestamptz nullable). 복합 `UniqueConstraint("user_id","reservation_id","type", name="uq_notifications_user_reservation_type")`(명시 단축명) + `CHECK` 단축명(`ck_notifications_type`)
  - [x] 마이그레이션 생성: `down_revision = "f1a2b3c4d5e6"`(현재 head), 파일명 `create_notifications_table`(rev `a7c9e1b3d5f2`). favorites 마이그레이션(181925e12bb8) 스타일 미러 — `op.f()` 자동명 + 복합 UNIQUE는 하드코딩 단축명
  - [x] `tests/notifications/test_models.py`: 제약명 ≤63자 + 이중접두 부재 회귀 가드(4.1 `test_models.py` 선례 미러)
  - [x] **라이브 Supabase에 `alembic upgrade head` 실제 실행**(no-op 아님 — 신규 리비전 `f1a2b3c4d5e6→a7c9e1b3d5f2`) + 적용 확인(컬럼·UNIQUE·CHECK·CASCADE FK·인덱스 inspect 검증) [[dev-workflow-policy-live-db-migration]]

- [x] **Task 2 — 서비스 프리미티브 (AC2)**
  - [x] `apps/api/app/notifications/service.py`:
    - `create_notification(session, user_id, reservation_id, type, reason=None) -> Notification` — INSERT + commit. `uq_notifications_user_reservation_type` 위반 시 rollback → 기존 행 재조회 반환(멱등). 무관 제약 re-raise(`violated_constraint()` 선별, favorites 선례)
    - `list_pending(session, user_id) -> list[Notification]` — `WHERE user_id=? AND dismissed_at IS NULL ORDER BY created_at DESC`(+ tie-breaker `id`)
    - `dismiss_notification(session, user_id, notification_id) -> None` — 행 조회(없거나 타 사용자 = `NOTIFICATION_NOT_FOUND` 404·소유권 누설 금지). 이미 `dismissed_at` 있으면 멱등 no-op. 아니면 `dismissed_at = now_utc()` + commit
  - [x] `tests/notifications/test_service.py`: FakeSession 패턴(favorites `test_service.py` 미러). 멱등 생성·소유권 404·dismiss 멱등 단언

- [x] **Task 3 — 엔드포인트 + 스키마 + SDK (AC3)**
  - [x] `apps/api/app/notifications/schemas.py`: `NotificationItem`(`id·type·reservation_id·reason·room_name·created_at`) — `created_at`은 `isoformat_utc` 직렬화(`...Z`). `room_name`은 라우터에서 합성(아래)
  - [x] `apps/api/app/notifications/router.py`: `APIRouter(prefix="/notifications", tags=["notifications"])`
    - `GET ""` → `list[NotificationItem]`, `Depends(get_current_principal)`(로그인만, 역할무관 — booker/provider/admin 모두 예약자가 될 수 있음). `service.list_pending` 결과를 `NotificationItem`으로 변환하며 `room_name`은 **라우터에서 `session.get(Room)` 합성**(4.8 선례 — service는 rooms import 금지, 순환 회피). 손상/누락 룸은 폴백(`room_name=None`)
    - `POST "/{notification_id}/dismiss"` → 204, `Depends(get_current_principal)`. `service.dismiss_notification(session, principal.user_id, notification_id)`
  - [x] `apps/api/app/core/errors.py`: `ErrorCode.NOTIFICATION_NOT_FOUND = "NOTIFICATION_NOT_FOUND"`(404) + `DEFAULT_STATUS` 매핑 추가
  - [x] `apps/api/app/main.py`: `api_router.include_router(notifications_router)` 등록(favorites/reservations 선례 위치)
  - [x] `tests/notifications/test_router.py`: 401(미로그인)·200 목록·204 dismiss·404 소유권·`created_at` `...Z`·room_name 합성/None 폴백 단언(favorites `test_router.py` 미러)
  - [x] **OpenAPI → SDK 재생성**: `pnpm` 파이프라인으로 `packages/api-client` 재생성(`notificationsListNotifications`·`notificationsDismissNotification`·`NotificationItem`). 드리프트 게이트 Layer A·B 그린. 비고: `type`은 자유 문자열 컬럼이라 SDK에 `NotificationType` 전용 enum은 생성되지 않는다(reservations `status` 선례와 동일 — 와이어는 `str`, FE가 문자열 리터럴로 분기). AC3 운영ID·`NotificationItem`은 모두 생성 확인.

- [x] **Task 4 — 웹 useNotifications 훅 + 소멸 뮤테이션 (AC3·AC5)**
  - [x] `apps/web/src/features/notifications/useNotifications.ts`:
    - `NOTIFICATIONS_KEY = ["notifications"] as const`(**최상위 독립 키 — 절대 `["rooms"]`/`["reservations"]` 프리픽스 금지**, favorites/reservations 선례)
    - `useNotifications()` — `useQuery({ queryKey: NOTIFICATIONS_KEY, enabled: !!user(useSession), queryFn: notificationsListNotifications({throwOnError:true}) → data ?? [] })`
    - `useDismissNotification()` — `useMutation`: `notificationsDismissNotification({ path:{ notification_id }, throwOnError:true })`. 옵티미스틱(useToggleFavorite 선례): `onMutate`에서 해당 id 제거 + previous 스냅샷, `onError` 롤백, `onSettled` **`NOTIFICATIONS_KEY` 정확 키만** invalidate
  - [x] `apps/web/src/features/notifications/useNotifications.test.tsx`: SDK 모킹·옵티미스틱 제거·정확 키 invalidate(광역 금지) 단언(favorites 훅 테스트 미러)

- [x] **Task 5 — 전역 NotificationBanner 컴포넌트 + 슬롯 배선 (AC4·AC5)**
  - [x] `apps/web/src/features/notifications/NotificationBanner.tsx`: 단건 배너. `role="status"`·아이콘(lucide `Bell`, `aria-hidden`)+텍스트(generic 카피 `bannerMessage` render-time 파생, 5.2/5.3이 정밀화) + 닫기 버튼(≥44px `tap-target`, `aria-label="알림 닫기"`, `useDismissNotification`). 토큰 스타일 `bg-secondary text-secondary-foreground border border-border rounded-md px-4 py-2 text-sm leading-[1.6]`(NetworkNotice 미러). 색 단독 금지(아이콘+텍스트)
  - [x] `apps/web/src/components/shell/InAppBannerSlot.tsx`를 **`"use client"` 컴포넌트로 승격** — `useNotifications()`로 미확인 통지 조회 → 각 통지를 `NotificationBanner`로 render-time map 렌더. 통지 0건/미로그인이면 빈 렌더(기존 `empty:hidden` 컨테이너 유지). 기존 `id="in-app-banner-slot"`·`aria-live="polite"`·레이아웃 className 보존(AppShell Z-순서 불변·AppShell.tsx 무수정)
  - [x] `apps/web/src/features/notifications/NotificationBanner.test.tsx` + InAppBannerSlot 통합 테스트: generic 카피 파생·통지 렌더·닫기 클릭→소멸·미로그인 빈 렌더(조회 안 함)·통지 0건 빈 렌더·aria 단언

- [x] **Task 6 — 게이트 + 라우팅 메모**
  - [x] 백엔드 `pytest`(신규 notifications 23건 포함 — 434 passed/11 skip)·`ruff`·`mypy` 그린
  - [x] SDK 드리프트 Layer A·B·`check-types` 그린
  - [x] 웹 `vitest`(신규 13건 포함 — 246 passed)·`lint`(직접 fetch 0·set-state-in-effect 0)·`check-types`·`build` 그린 / `turbo` 전체 그린(13/13)
  - [x] **모바일 배너 = E7 명시 라우팅**(FR-18 "웹·앱 동일"이나 apps/mobile 본격 작업은 E7·apps/admin 미수정 — 본 스토리 apps/mobile·apps/admin 변경 0) [[web-mobile-parity-on-changes]]

## Dev Notes

### 🎯 스토리 본질 (반드시 먼저 읽을 것)

이건 **인프라 스토리**다(4.1 reservations foundation과 동형). 목표는 "동작하는 알림 기능"이 아니라 **5.2/5.3/6.2/8.3이 소비할 영속 통지 기계 + 전역 배너 표면**을 세우는 것이다.

- **이 스토리가 만드는 것:** 통합 `notifications` 테이블 · 서비스 프리미티브(create/list_pending/dismiss) · GET/POST dismiss 엔드포인트 · SDK · 전역 `NotificationBanner` + 슬롯 배선 · `useNotifications` 훅.
- **이 스토리가 만들지 않는 것 (명시 위임):**
  - **도래 리마인드 도출**(24h 이내 확정 예약 → `reservation_reminder` 행/배너) + '다시 보지 않기' 정밀 카피 = **5.2**
  - **상태변경 통지 생성**(거절/취소 시점에 `create_notification(type=status_change, reason=...)` 호출) = **6.2(거절)·8.3(임의취소)** 배선, 표시·'확인' 정밀 카피 = **5.3**
- **"죽은 컴포넌트" 아님:** KTH 확정(영속 통지 수직 슬라이스 풀) — 배너는 GET 실데이터를 렌더하고 dismiss로 소멸하는 **완전한 수직 슬라이스**다. 프로덕션 트리거(생성)는 5.3/6.2/8.3이 배선하지만, 데모/테스트는 행 seed로 end-to-end 검증된다(4.1·4.8 인프라 선례). 배너 카피는 generic(type/reason 기반)이고 5.2/5.3이 정밀화한다.

### KTH 확정 3건 (2026-06-17)

1. **모델 형태 = 통합 테이블 + `type` 판별자.** 단일 `notifications`로 두 종류를 다룬다. `status_change`=거절/취소 시점 행 생성·`dismissed_at`으로 소멸. `reservation_reminder`=평소 행 없음(도출)·'다시 보지 않기' 시 억제행 생성(5.2). 단일 dismiss 메커니즘.
2. **5.1 스코프 = 영속 통지 수직 슬라이스 풀.** 테이블+프리미티브+GET+POST dismiss+SDK+전역 배너+훅 모두. 도래 도출=5.2, 거절/취소 생성=5.3/6.2/8.3.
3. **dismiss = 단일 generic 프리미티브.** `POST /notifications/{id}/dismiss` 하나가 `dismissed_at` 설정(멱등). '다시 보지 않기'(5.2)·'확인'(5.3) 모두 동일 엔드포인트 소비 — 차이는 **행 생성 방식**(리마인드=억제행 생성, 통지=기존행)이지 소멸 동작이 아님. 5.2/5.3이 카피·생성만 분기.

### 🏗️ 아키텍처 가드레일 (Architecture.md — 반드시 준수)

**도메인 구조** [Source: architecture.md#Structure Patterns / L255-256]
- 백엔드: `apps/api/app/notifications/{router,models,schemas,service}.py` (도메인 모듈 패키지). `notifications`는 이미 빈 골격(`__init__.py`)이 1.2에서 생성됨.
- 프론트: 기능 단위 폴더 `apps/web/src/features/notifications/`.

**네이밍** [Source: architecture.md#Naming Patterns / L231-251]
- 테이블 복수 snake_case `notifications`. 컬럼 snake_case. FK `{단수}_id`. 제약 `uq_{table}_{cols}`·`ck_{table}_{...}`. 시각 컬럼 `*_at`(UTC timestamptz).
- API JSON 필드 = **snake_case 그대로**(와이어 전 구간, camelCase 변환 레이어 금지).
- 상태코드: 404(NOT_FOUND), 401(미인증), 204(dismiss 성공 본문 없음).

**시간 규약** [Source: architecture.md#Format Patterns / L268-269, core/time.py]
- 모든 시각 UTC 저장(`now_utc()`)·ISO-8601 `...Z` 전송(`isoformat_utc()`). naive datetime 금지(경계에서 ValueError).
- 5.1은 24h 경계 판정을 **하지 않는다**(그건 5.2 도래 도출). 5.1은 `created_at`/`dismissed_at` 기록·직렬화만.

**에러** [Source: architecture.md#Format Patterns / L265-267, core/errors.py]
- 표준 스키마 `{"detail":{"code","message"}}`. `DomainError(ErrorCode.X, "...")` 만 사용(raw `HTTPException(detail="string")` 금지).
- **신규 `ErrorCode.NOTIFICATION_NOT_FOUND`(404)** 1건 추가 — `core/errors.py` `ErrorCode` StrEnum + `DEFAULT_STATUS` 둘 다.

**경계** [Source: architecture.md#Architectural Boundaries / L354-361]
- 도메인 간 직접 import 금지, service 통해서만. **service는 rooms import 금지**(순환 회피) — `room_name` 합성은 **라우터에서 `session.get(Room)`**(4.8 `list_booker_reservations` 선례와 동일 패턴).
- 프론트는 `packages/api-client` SDK로만 호출(직접 fetch 금지).
- 서버 상태=TanStack Query, 화면 로컬 상태만.

**금지 안티패턴** [Source: architecture.md#Anti-Patterns / L297-301]
- 색만으로 상태 표현 금지(배너=색+아이콘+텍스트). 로컬 타임존 날짜 경계 판정 금지(5.1은 경계판정 안 함).

### 📂 수정/생성 파일 (현 상태 → 변경)

**UPDATE (기존 — 깨지 말 것):**
- `apps/api/app/notifications/__init__.py` — 현재 `"""notifications 도메인 모듈 (Story 1.2 — 빈 골각). 알림 인프라는 Epic 5."""`. 도크스트링만 갱신.
- `apps/api/app/core/errors.py` — `ErrorCode` StrEnum에 `NOTIFICATION_NOT_FOUND` 추가, `DEFAULT_STATUS` dict에 `ErrorCode.NOTIFICATION_NOT_FOUND: 404` 추가. **기존 코드/매핑 보존**(SLOT_CONFLICT 등 10건).
- `apps/api/app/main.py` — `from app.notifications.router import router as notifications_router` + `api_router.include_router(notifications_router)` 추가. **기존 라우터 등록 순서·`custom_generate_unique_id`·CORS·lifespan 보존.**
- `apps/web/src/components/shell/InAppBannerSlot.tsx` — 현재 빈 placeholder div(`id="in-app-banner-slot"`·`aria-live="polite"`·`empty:hidden`). **`"use client"`로 승격 + `useNotifications` 소비 + `NotificationBanner` 렌더.** ⚠️ **AppShell Z-순서·레이아웃·기존 id/aria 보존**(AppShell.tsx L51이 이 컴포넌트를 헤더 하단에 렌더 — 배너<콘텐츠<FAB Z-순서). AppShell.tsx 자체는 수정 불요(InAppBannerSlot만 교체).

**NEW (백엔드):**
- `apps/api/app/notifications/models.py·schemas.py·service.py·router.py`
- `apps/api/alembic/versions/<rev>_create_notifications_table.py`
- `apps/api/tests/notifications/__init__.py·test_models.py·test_service.py·test_router.py`

**NEW (웹):**
- `apps/web/src/features/notifications/useNotifications.ts·NotificationBanner.tsx`
- `apps/web/src/features/notifications/useNotifications.test.tsx·NotificationBanner.test.tsx`

### 🔁 재사용 — 바퀴 재발명 금지

| 필요 | 재사용 대상 | 출처 |
|---|---|---|
| 도메인 패키지 구조(models/schemas/service/router) | `favorites/` 전체(가장 가까운 user-scoped 단순 도메인) | apps/api/app/favorites |
| 멱등 생성(UNIQUE 위반→기존행) + 선별 제약 변환 | `favorites.service.add_favorite` + `violated_constraint()` | favorites/service.py, core/db.py |
| 소유권 404·읽기전용 cross-domain(room_name 합성) | `reservations` me_router `list_booker_reservations`(라우터에서 `session.get(Room)`) | reservations (4.8) |
| 시각 직렬화(`...Z`) | `isoformat_utc`·`now_utc` | core/time.py |
| 에러코드/표준스키마 | `ErrorCode`·`DomainError`·`ErrorResponse`·`DEFAULT_STATUS` | core/errors.py |
| 인증 의존성(로그인만, 역할무관) | `get_current_principal`(`require_role` 아님) | core/security.py |
| 세션 의존성 | `get_session` | core/db.py |
| FakeSession 단위테스트 | `FakeFavoriteSession`(exec 라우팅·commit IntegrityError 주입) | tests/favorites/test_service.py |
| 라우터 dependency override 통합테스트 + `auth_env` 픽스처 | favorites `test_router.py` | tests/favorites, tests/conftest.py |
| TanStack 독립 키 + 옵티미스틱 뮤테이션 | `useFavorites`/`useToggleFavorite`(키 `["favorites"]`·정확 키 invalidate) | features/favorites/useFavorites.ts |
| 단순 쿼리 훅 + auth 게이팅 | `useReservations`(키 `["reservations"]`·`enabled:!!user`) | features/reservation/useReservations.ts |
| 전역 aria-live 인라인 배너(role=status·토큰 스타일) | `NetworkNotice`(`bg-secondary`·`text-secondary-foreground`·`border`·`rounded-md`·`leading-[1.6]`) | components/NetworkNotice.tsx |
| 상태 배지 3중신호(색+아이콘+텍스트)·render-time 파생 | `ReservationRow`/`reservations.ts`(set-state-in-effect 회피) | features/reservation |
| SDK 호출 형상(`{data}=await fn({throwOnError:true})`·credentials) | `api-client.ts`(`configureApiClient({credentials:"include"})`) | lib/api-client.ts |
| vitest QueryClient 래퍼·SDK 모킹 | favorites 훅/컴포넌트 테스트 | features/favorites/*.test.tsx |

### 🧱 데이터 모델 상세 (KTH 확정 #1)

```
notifications
  id              uuid PK   (default_factory uuid4)
  user_id         uuid  FK→users.id   RESTRICT  index   (수신자)
  reservation_id  uuid  FK→reservations.id  CASCADE  index  (대상 예약)
  type            str   CHECK in ('reservation_reminder','status_change')   index 선택
  reason          str?  ('rejected'|'cancelled' — status_change 전용, reminder=NULL)
  created_at      timestamptz  (now_utc)
  dismissed_at    timestamptz?  (NULL=미확인/표시, 설정=소멸 — '다시보지않기'·'확인' 공통)
  UNIQUE(user_id, reservation_id, type)  name="uq_notifications_user_reservation_type"
```

- **`reservation_id` ondelete=CASCADE** (favorites는 RESTRICT였으나 통지는 예약 종속 — 예약 행 하드삭제 시 통지 무의미. 단 현 앱은 예약 하드삭제 경로 없음[취소=status flip]이라 실발현은 E8). `user_id`=RESTRICT(favorites 선례 — 사용자는 하드삭제 안 함).
- **`type` CHECK**: 4.1 `ck_reservations_status` 선례 — 명시 단축명 `ck_notifications_type`. Pydantic Literal + DB CHECK 이중 방어.
- **복합 UNIQUE 단축명**: `uq_notifications_user_reservation_type`(38자 ≤63). 자동 규약(`uq_notifications_user_id_reservation_id_type`=44자)도 ≤63이나, **4.1 선례대로 명시 단축명 + ≤63 회귀 테스트**를 둔다. [Source: deferred-work.md L97 — 63자 한계 회수 패턴]
- 멱등 근거: `(user_id, reservation_id, type)` 1행 — 같은 예약·같은 종류 통지는 1건. status_change 재생성(거절 후 재거절 등 비정상)·reminder 억제 중복 시 멱등.

### 🌐 엔드포인트 계약 (AC3)

```
GET  /api/v1/notifications                      → 200 list[NotificationItem]   (get_current_principal)
POST /api/v1/notifications/{notification_id}/dismiss → 204                       (get_current_principal)
```

`NotificationItem` (snake_case 와이어):
```
{ id, type, reservation_id, reason, room_name, created_at }   # created_at = isoformat_utc → ...Z
```
- `room_name`: 라우터에서 `session.get(Room, reservation.room_id)` 합성(service rooms import 금지·4.8 패턴). 룸 누락/비활성도 폴백(`room_name=None` 또는 ""·막다른 화면 금지). ⚠️ `notification → reservation → room` 2-홉 — 라우터에서 `session.get(Reservation, n.reservation_id)` 후 `session.get(Room, r.room_id)`. N+1 우려(통지 N건)는 인프라 수용(목록 작음·favorites N+1 deferred 선례) — 필요 시 후속.
- `GET`는 `list_pending`(`dismissed_at IS NULL`)만 반환 — 소멸한 건 안 보임.
- `operationId` = `{tag}_{name}` = `notifications_list_notifications`·`notifications_dismiss_notification`(main.py `custom_generate_unique_id`).

### 🎨 배너 컴포넌트 (UX-DR5 / AC4)

[Source: ux DESIGN.md#UX-DR5 / EXPERIENCE.md L121,166,167 / epics.md L144]
- **시각:** 면 위 플랫(그림자 없음). 배경 `bg-secondary`(`#FFF0D6`) 또는 `bg-muted`(`#F4EDDF`) — `NetworkNotice`와 동일 토큰 클래스 채택. `text-secondary-foreground`·`border border-border`·`rounded-md`·`px-4 py-2`·`text-sm leading-[1.6]`.
- **3중 신호:** 색 + 아이콘(lucide `Bell`/`BellRing`·`aria-hidden="true"`) + 텍스트. 색 단독 금지.
- **접근성:** 슬롯이 이미 `aria-live="polite"`(InAppBannerSlot 컨테이너) — 배너 출현이 자동 안내. 배너 자체 `role="status"`(NetworkNotice 선례). 닫기 버튼 `≥44px`(tap-target)·`aria-label`(예 "알림 닫기").
- **카피(generic — 5.2/5.3이 정밀화):** type/reason 기반 최소 카피. 친근한 해요체(EXPERIENCE.md 톤). 예: `status_change`+`rejected` → "○○ 예약이 거절됐어요.", `status_change`+`cancelled` → "○○ 예약이 취소됐어요.", `reservation_reminder` → "○○ 예약이 곧 다가와요." (정밀 카피·24h 도출은 5.2/5.3 — 여기선 동작하는 generic이면 충분). 닫기 라벨은 generic("확인"/"닫기")으로 두고 5.2가 reminder에 '다시 보지 않기' 라벨 분기.
- **푸시 아님:** 접속 시점 GET 조회로만 표시(NFR — 푸시 인프라 없음).

### ⚠️ 반복 함정 프리플라이트 (dev-workflow-policy 누적 교훈 — 위반 시 리뷰 차단)

[[dev-workflow-policy-deferred-and-repeat-mistakes]]
1. **TanStack 키 풋건:** `NOTIFICATIONS_KEY = ["notifications"]` **최상위 독립** — 절대 `["rooms"]`/`["reservations"]` 프리픽스 금지. dismiss invalidate는 **정확 키만**(광역 금지). (3.7 L153 풋건·4.x 반복)
2. **set-state-in-effect 금지:** 배너 표시/숨김은 GET 결과에서 **render-time 파생**(effect→setState 금지). InAppBannerSlot은 `useNotifications().data`를 직접 map 렌더. (3.5/3.6/4.x 선례)
3. **직접 fetch 금지:** SDK(`@desknow/api-client`)로만. (전 스토리)
4. **색 단독 금지:** 배너=색+아이콘+텍스트.
5. **클라 트리거 4xx→500화 금지:** dismiss 404/401은 `DomainError`/`get_current_principal`가 표준 처리(2.2/2.3 patch 반복 교훈). 라우터에서 raw 500 누출 금지.
6. **소유권 누설 금지:** 타 사용자 통지 dismiss = 404(403 아님 — 존재 누설 회피, 4.7 cancel 선례).
7. **dead 버튼/막다른 화면 금지:** 닫기 버튼은 실제 dismiss 호출. 룸 누락도 폴백 렌더.

### 🔗 후속 의존 (forward notes — 5.1이 만들지 않음)

- **5.2 (도래 리마인드):** `list_pending`에 **도출 리마인드 머지**(24h 이내 확정 예약 → 가상/실 `reservation_reminder` + '다시 보지 않기' 억제행 체크). ⚠️ **`hours_until` 부동소수 6h/24h 경계 정밀도**(deferred-work.md L103·core/time.py:69-89) 트리거가 5.2 — 그때 epsilon/초절삭 정책 + 경계 테스트 의무 회수. [Source: deferred-work.md L103]
- **5.3 (상태변경 통지 표시):** reason별 정밀 카피 + '확인' 라벨 분기. 생성은 6.2/8.3.
- **6.2 (거절)·8.3 (임의취소):** 거절/취소 service에서 `create_notification(type=status_change, reason='rejected'|'cancelled')` 호출 배선(동일 트랜잭션 권장). cancel-vs-reject 교차 race(deferred-work.md L11)는 6.2 소유.
- **모바일 배너:** E7(apps/mobile). FR-18 "웹·앱 동일"이나 본격 모바일은 E7. [[web-mobile-parity-on-changes]]
- **N+1(GET 통지별 reservation+room 2-홉):** favorites N+1 deferred 계열 — 통지 다수 시 배치 조회 후속.

### 🧪 테스트 표준

[Source: architecture.md#Structure Patterns L258, tests/conftest.py, tests/favorites/*]
- 백엔드: `tests/notifications/` 미러 구조. `test_service.py`=FakeSession 단위(favorites 선례·exec 엔티티 라우팅·commit IntegrityError 주입), `test_router.py`=`TestClient` 통합 + `auth_env` 픽스처 + `_override_session`/`app.dependency_overrides[get_session]`. 토큰 팩토리 `create_access_token(uuid4(), "booker")`.
- 핵심 단언: 멱등 생성(UNIQUE 위반→기존행)·`list_pending` dismissed 제외·dismiss 소유권 404·dismiss 멱등·`created_at` `...Z`·제약명 ≤63.
- 프론트: vitest co-located `*.test.tsx`. QueryClient 래퍼 + SDK 모킹(favorites 선례). 단언: 옵티미스틱 제거·정확 키 invalidate(광역 금지)·미로그인 빈 렌더·배너 닫기→소멸·aria(`role=status`·닫기 `aria-label`).

### Project Structure Notes

- 정합: `notifications` 도메인은 architecture.md L256·L337에 이미 정의된 모듈(빈 골격 존재). 신규 디렉터리 생성 아님 — 파일 채움.
- 변이 없음: 와이어 snake_case·UTC/`...Z`·도메인 경계·SDK-only 호출 모두 기존 패턴과 일치.
- 신규 의존성: 백엔드 0(SQLModel/FastAPI 기존)·프론트 0(lucide `Bell`·TanStack·shadcn 토큰 기존).

### References

- [Source: epics.md#Epic 5 / Story 5.1 (L888-906)] — 스토리 BDD, 도래/상태변경 2종, '다시 보지 않기'/'확인'
- [Source: epics.md L144 (UX-DR5)] — 인앱 배너 컴포넌트 2종·면 위 플랫·secondary/muted·아이콘+텍스트·aria-live
- [Source: epics.md L150,166,167 (UX-DR11/접근성)] — aria-live·색 비의존·터치 ≥44px
- [Source: architecture.md#API & Communication Patterns L175-176] — notifications 도메인 모듈
- [Source: architecture.md#Requirements to Structure Mapping L376] — 알림 FR-18,18a → notifications · 전역 배너 컴포넌트
- [Source: architecture.md#Project Structure L337] — `notifications/ # FR-18,18a — pending/dismiss`
- [Source: architecture.md#Naming/Format/Anti-Patterns L231-301] — snake_case·UTC `...Z`·에러스키마·색비의존
- [Source: PRD FR-18 (예약 도래 인앱 배너), FR-18a (상태변경 통지 배너)] — 24h 정확·'다시 보지 않기' 영속 / 거절·취소 1회 통지·'확인' 소멸·독립 트리거
- [Source: apps/api/app/favorites/*] — user-scoped 도메인 패턴(멱등·소유권·FakeSession 테스트)
- [Source: apps/api/app/reservations/router.py (4.8 list_booker_reservations)] — 라우터 room_name 합성(service rooms import 금지·순환 회피)
- [Source: apps/api/app/core/{errors,time,security,db}.py] — ErrorCode/DomainError·isoformat_utc/now_utc·get_current_principal·get_session/violated_constraint
- [Source: apps/web/src/components/{shell/InAppBannerSlot,NetworkNotice}.tsx] — 전역 슬롯(aria-live·empty:hidden)·인라인 배너(role=status·토큰)
- [Source: apps/web/src/features/favorites/useFavorites.ts] — 독립 키·옵티미스틱·정확 키 invalidate
- [Source: deferred-work.md L97 (≤63 제약명), L103 (hours_until 경계=5.2 트리거)]
- [[dev-workflow-policy-live-db-migration]] · [[dev-workflow-policy-deferred-and-repeat-mistakes]] · [[web-mobile-parity-on-changes]] · [[terminology-network-disconnect-not-offline]]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Opus 4.8, 1M context)

### Debug Log References

- 라이브 Supabase 마이그레이션: `uv run alembic upgrade head` → `f1a2b3c4d5e6 → a7c9e1b3d5f2 (create notifications table)` 적용. `inspect()`로 컬럼 7종·UNIQUE(`uq_notifications_user_reservation_type`)·CHECK(`ck_notifications_type`)·FK(reservation_id=CASCADE, user_id=RESTRICT)·인덱스 2종 검증.
- 게이트: api `pytest` 434 passed/11 skip(신규 notifications 23) · `ruff`(E501 2건 수정 후 clean) · `mypy` 38 files clean / SDK 드리프트 Layer A·B clean · `check-types` clean / web `vitest` 246 passed(신규 13) · `lint` clean · `check-types` clean · `build` clean / `turbo run lint check-types test build` 13/13 successful.

### Completion Notes List

- **인프라 수직 슬라이스 완성(AC1~AC5):** 통합 `notifications` 테이블(type 판별자) + 서비스 프리미티브(create 멱등·list_pending·dismiss 소유권/멱등) + `GET /notifications`·`POST /notifications/{id}/dismiss` + SDK 재생성 + 전역 `NotificationBanner`·`InAppBannerSlot` 배선 + `useNotifications`/`useDismissNotification` 훅. 행 seed로 end-to-end 검증되는 완전한 수직 슬라이스(트리거 생성은 5.2/6.2/8.3 위임).
- **KTH 확정 3건 반영:** ①통합 테이블+type 판별자+`UNIQUE(user_id,reservation_id,type)` 멱등. ②영속 통지 수직 슬라이스 풀(테이블→GET→배너→dismiss). ③단일 generic dismiss(`POST .../dismiss` 멱등 — '다시 보지 않기'/'확인' 공유).
- **도메인 경계 준수:** `room_name` 합성은 라우터의 `notification→reservation→room` 2-홉 `session.get`(service는 `notifications` 테이블만 — rooms/reservations import 0, 4.8 순환 회피 패턴). 룸/예약 누락은 `room_name=None` 폴백.
- **반복 함정 프리플라이트 7종 모두 준수:** ①`NOTIFICATIONS_KEY=["notifications"]` 최상위 독립·정확 키만 invalidate(광역·["rooms"]/["reservations"] 금지·테스트로 단언). ②배너 표시=GET 결과 render-time map(effect→setState 0). ③SDK-only(직접 fetch 0). ④색+아이콘+텍스트 3중. ⑤dismiss 404/401=DomainError/get_current_principal 표준(raw 500 0). ⑥타인 통지=404(누설 금지). ⑦닫기=실제 dismiss·룸 누락 폴백 렌더(dead 버튼/막다른 화면 0).
- **신규 ErrorCode 1:** `NOTIFICATION_NOT_FOUND`(404) — `ErrorCode` StrEnum + `DEFAULT_STATUS` 둘 다. 신규 의존성 0(백엔드·프론트).
- **SDK `NotificationType` 비고:** `type`을 자유 문자열 컬럼으로 저장(reservations `status`/users `role` 선례 — DB CHECK + 스키마 이중 방어)했으므로 SDK에 전용 `NotificationType` enum은 생성되지 않는다(와이어=`str`). FE는 문자열 리터럴(`"status_change"`/`"reservation_reminder"`)로 분기. AC3가 요구하는 operationId(`notificationsListNotifications`·`notificationsDismissNotification`)·`NotificationItem`은 모두 생성 확인.
- **모바일/admin:** apps/mobile·apps/admin 변경 0(모바일 배너=E7 명시 라우팅 — FR-18 "웹·앱 동일"이나 본격 모바일은 E7). [[web-mobile-parity-on-changes]]
- **후속 위임(forward):** 도래 리마인드 도출+'다시 보지 않기' 카피=5.2(+`hours_until` 6h/24h 경계 정밀도 deferred L103 의무 회수 트리거), 상태변경 표시 정밀 카피=5.3, 거절/취소 생성 배선=6.2/8.3, N+1 배치 조회=favorites 계열 deferred.

### File List

**NEW (백엔드):**
- `apps/api/app/notifications/models.py`
- `apps/api/app/notifications/schemas.py`
- `apps/api/app/notifications/service.py`
- `apps/api/app/notifications/router.py`
- `apps/api/alembic/versions/a7c9e1b3d5f2_create_notifications_table.py`
- `apps/api/tests/notifications/__init__.py`
- `apps/api/tests/notifications/test_models.py`
- `apps/api/tests/notifications/test_service.py`
- `apps/api/tests/notifications/test_router.py`

**UPDATE (백엔드):**
- `apps/api/app/notifications/__init__.py` (도크스트링 갱신)
- `apps/api/app/core/errors.py` (`NOTIFICATION_NOT_FOUND` 추가 — ErrorCode + DEFAULT_STATUS)
- `apps/api/app/main.py` (notifications_router 등록)

**NEW (웹):**
- `apps/web/src/features/notifications/useNotifications.ts`
- `apps/web/src/features/notifications/NotificationBanner.tsx`
- `apps/web/src/features/notifications/useNotifications.test.tsx`
- `apps/web/src/features/notifications/NotificationBanner.test.tsx`

**UPDATE (웹):**
- `apps/web/src/components/shell/InAppBannerSlot.tsx` (`"use client"` 승격 + useNotifications 소비 + NotificationBanner 렌더)

**UPDATE (SDK — 재생성 산출물):**
- `packages/api-client/openapi.json`
- `packages/api-client/src/generated/**` (sdk.gen.ts·types.gen.ts 등 — `notificationsListNotifications`·`notificationsDismissNotification`·`NotificationItem` 추가)

## Change Log

| 날짜 | 변경 | 비고 |
|---|---|---|
| 2026-06-17 | Story 5.1 구현 완료 (notifications 모델·서비스·엔드포인트·SDK·전역 배너·훅) | 인프라 수직 슬라이스. 신규 ErrorCode 1(NOTIFICATION_NOT_FOUND)·신규 의존성 0. 라이브 Supabase 마이그레이션 적용(`a7c9e1b3d5f2`). 게이트 전건 그린(api 434/11skip·web 246·turbo 13/13). 트리거(생성)는 5.2/6.2/8.3 위임. |

## Review Findings

3계층 적대적 리뷰(Blind Hunter / Edge Case Hunter / Acceptance Auditor) — 2026-06-17. Auditor=AC1~AC5 전건 PASS·차단 위반 0. decision-needed 0 · patch 2 · defer 6 · dismiss 10(오탐·설계대로·기처리).

### Patch (코드 수정 — 비차단)

- [ ] [Review][Patch] 중첩 aria-live 라이브 리전 이중 낭독 — 컨테이너 `aria-live="polite"`(InAppBannerSlot) 안에 배너 `role="status"`(암묵 live region)가 중첩되어 다건 통지 시 스크린리더 이중/충돌 낭독 가능. 컨테이너 aria-live는 AC4 슬롯 계약이므로 보존하고 배너의 `role="status"`를 제거(또는 컨테이너 aria-live 제거 중 택1, 권장=배너 role 제거). [apps/web/src/features/notifications/NotificationBanner.tsx:47] (edge)
- [ ] [Review][Patch] test_router.py 401 테스트 docstring AC 라벨 오기 — 무토큰 401 게이팅 테스트가 "AC5 인증 게이팅"으로 주석돼 있으나 인증 표면은 AC3(AC5=소멸 영속). 동작·단언은 정확, 주석만 수정. [apps/api/tests/notifications/test_router.py:209,256] (auditor)

### Defer (실재하나 현 스토리 비차단 — deferred-work.md 등재)

- [x] [Review][Defer] 다중 배너 동시 dismiss 옵티미스틱 previous 스냅샷 클로버 [apps/web/src/features/notifications/useNotifications.ts:57-70] — deferred, pre-existing (blind+edge)
- [x] [Review][Defer] create_notification 진짜 동시삽입 경합 시 재조회 None → raw IntegrityError 500 [apps/api/app/notifications/service.py:59-71] — deferred, pre-existing (blind+edge)
- [x] [Review][Defer] GET /notifications 실패 시 배너 무음 소실(에러 미surface) [apps/web/src/features/notifications/useNotifications.ts + InAppBannerSlot.tsx] — deferred, pre-existing (edge)
- [x] [Review][Defer] FakeSession이 where/order_by 미모사 → list_pending의 dismissed_at 필터·정렬이 단위테스트에서 실검증 안 됨 [apps/api/tests/notifications/test_service.py] — deferred, pre-existing (blind)
- [x] [Review][Defer] reason 자유 문자열 미검증(BE CHECK/길이 0 + FE 매직스트링) — type와 방어 비대칭 [apps/api/app/notifications/models.py:98·service.py·NotificationBanner.tsx:26-29] — deferred, pre-existing (blind+edge)
- [x] [Review][Defer] GET 통지별 reservation+room 2-홉 N+1(스토리 인프라 수용 명시) [apps/api/app/notifications/router.py:66-69] — deferred, pre-existing (blind+auditor)
