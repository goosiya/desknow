---
baseline_commit: NO_VCS
---

# Story 2.1: rooms 데이터 모델 & 영업시간/휴무 모델

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 개발자,
I want 스터디룸·영업시간·휴무 예외 테이블과 슬롯 도출 규칙을 정의하길,
So that 등록된 공간으로부터 1시간 슬롯이 결정적으로 도출되고 탐색·예약이 이를 사용할 수 있다.

## Acceptance Criteria

**AC1 — rooms 도메인 마이그레이션**
**Given** rooms 도메인 마이그레이션
**When** `alembic upgrade head`를 실행하면
**Then** `rooms`(이름·시간당 금액·수용 인원·룸 형태·부대시설·lat/lng·행정동 코드·`is_active`), `business_hours`(room별 weekday 0~6, 같은 날 내 시작/종료), `holiday_exceptions`(room별 date) 테이블이 생성된다.

**AC2 — 슬롯 도출 규칙**
**Given** 한 룸의 영업시간·휴무·날짜
**When** 슬롯을 도출하면
**Then** 슬롯 = (요일별 영업시간 − 휴무일 − 이미 예약) 으로 계산되고, 고정 1시간 단위이며 영업시간은 같은 날 내(자정 넘김 없음)로 슬롯 소속 날짜가 모호하지 않다. (이미 예약 차감은 reservations가 존재하는 E4에서 연결되며, 그 전까지 예약 집합은 공집합으로 취급한다.)

**AC3 — 시간 규약**
**And** 모든 slot_start는 UTC로 저장되고 판정은 Asia/Seoul 기준이다(NFR-1, core/time 사용).

**AC4 — 네이밍 규약 63자 한계 회수 (Epic 1 회고 P1 / 출처 1.4 defer)**
**Given** rooms 도메인이 복합 UNIQUE 제약(`business_hours`·`holiday_exceptions`)을 추가하는 시점
**When** 마이그레이션을 생성하면
**Then** 모든 복합 제약은 **명시 단축명**(`UniqueConstraint(name=...)`)을 부여받고, 각 제약명이 **PostgreSQL 63자 식별자 한계 이내**임이 검증되며(절단 시 autogenerate 불일치·이름 충돌 방지), 향후 3~4컬럼 복합 제약은 명시 단축명을 의무화한다는 정책이 코드 주석으로 명문화된다.

## Tasks / Subtasks

> **착수 전 — 반복 함정 프리플라이트(Epic 1 회고 A1, 매 dev-story 의무).** 결과를 Dev Agent Record에 명시:
> ① Windows UTF-8 — 마이그레이션/모델 파일은 한국어 주석 포함, 파일 IO·스크립트 출력 인코딩 UTF-8 확인(cp949 회피).
> ② 신규 런타임 의존성 — **신규 의존성 0 예상**(JSONB=`sqlalchemy.dialects.postgresql.JSONB`, `Time`/`Date`=SQLAlchemy 기본, uuid·datetime=stdlib). 새 import가 필요하면 pyproject에 명시 선언 후 진행.
> ③ import 시점 부작용 금지 — `app/rooms/models.py`·`service.py`는 import 시 settings/DB 접근 금지(순수 모델 정의 + `app.core.time` import만). 슬롯 함수는 순수 함수.
> ④ 외부 라이브러리 API 실측 — SQLModel의 **JSON/JSONB 컬럼 타이핑 관용구**, `__table_args__`로 `CheckConstraint`/`UniqueConstraint` 부여, `sa.Time`/`sa.Date` 매핑은 docstring이 아니라 **설치된 sqlmodel/sqlalchemy 소스로 확인**(아래 Dev Notes의 권장 관용구를 실측 대조).

- [x] **Task 1 — `app/rooms/models.py`: rooms 도메인 ORM 모델 3종 + enum** (AC: 1, 4)
  - [x] `Room`(SQLModel, table=True, `__tablename__ = "rooms"`): `id`(uuid PK), `provider_id`(uuid FK→users.id, NOT NULL, index), `name`, `price_per_hour`(int, 원), `capacity`(int), `room_type`(str), `amenities`(list[str], JSONB, default 빈 리스트), `lat`(float), `lng`(float), `admin_dong_code`(str), `is_active`(bool, default True), `created_at`(timestamptz UTC). 1.7 `User`·`RefreshToken` 모델 스타일을 그대로 미러.
  - [x] `BusinessHours`(`__tablename__ = "business_hours"`): `id`(uuid PK), `room_id`(uuid FK→rooms.id, ondelete CASCADE, NOT NULL, index), `weekday`(int, 0~6 월=0), `open_time`(`sa.Time`, naive 시각 = ROOM_TZ 벽시계), `close_time`(`sa.Time`). `__table_args__` = 복합 UNIQUE(room_id, weekday) + CHECK(weekday 0~6) + CHECK(close_time > open_time) — **전부 명시 단축명**(AC4).
  - [x] `HolidayException`(`__tablename__ = "holiday_exceptions"`): `id`(uuid PK), `room_id`(uuid FK→rooms.id, ondelete CASCADE, NOT NULL, index), `holiday_date`(`sa.Date`, ROOM_TZ 기준 날짜). `__table_args__` = 복합 UNIQUE(room_id, holiday_date) — **명시 단축명**(AC4).
  - [x] `RoomType(StrEnum)`: `OPEN = "open"`, `PRIVATE = "private"`(1.7 `UserRole` 패턴). `room_type` 컬럼은 `role`과 동일하게 **자유 문자열 저장**(DB CHECK·Pydantic Literal 검증은 Story 2.2로 명시 편성 — Dev Notes 참조). `amenities`는 다중선택+"기타"라 JSONB 배열로 저장(코드값 리스트).
- [x] **Task 2 — Alembic env.py 모델 허브 등록** (AC: 1)
  - [x] `apps/api/alembic/env.py`의 모델 import 허브에서 이미 주석으로 자리잡은 `from app.rooms import models as _rooms_models  # noqa: F401  (Story 2.1)` 라인을 **주석 해제**(1.7 `_auth_models` 라인 아래). 이로써 autogenerate가 rooms 모델을 인식.
- [x] **Task 3 — 마이그레이션 생성·검증** (AC: 1, 3, 4)
  - [x] `down_revision = "ac9b81f7d058"`(현재 head=refresh_tokens) 위에 신규 리비전 생성. autogenerate 사용 가능(모델 등록됨)하되 **반드시 수기 검토**: 1.7/1.8 마이그레이션처럼 `import sqlmodel` 포함, `*_at`·timestamptz, FK ondelete, JSONB·Time·Date 타입 렌더 확인.
  - [x] 제약명이 1.4 `NAMING_CONVENTION`/명시 단축명과 일치하는지 확인: `pk_rooms`·`fk_rooms_provider_id_users`·`idx_rooms_provider_id`; `pk_business_hours`·`fk_business_hours_room_id_rooms`·`idx_business_hours_room_id`·`uq_business_hours_room_id_weekday`·CHECK 2종 단축명; `pk_holiday_exceptions`·`fk_holiday_exceptions_room_id_rooms`·`idx_holiday_exceptions_room_id`·`uq_holiday_exceptions_room_id_holiday_date`. **각 제약명 글자수 ≤63 검증(AC4)** 후 결과를 Completion Notes에 기록.
  - [x] `downgrade()`는 인덱스 drop 후 테이블 drop(생성 역순: holiday_exceptions → business_hours → rooms; FK 의존성 역순). 왕복 가능.
  - [x] **운영 DB 미변조**: 1.7/1.8 패턴대로 `alembic upgrade head --sql`(오프라인)로 DDL을 실증(라이브 DB 연결 없이). 출력에 3 테이블 CREATE + 제약/인덱스가 보이는지 확인.
- [x] **Task 4 — `app/rooms/service.py`: 슬롯 도출 순수 함수** (AC: 2, 3)
  - [x] `derive_slots(business_hours, holiday_dates, target_date, reserved_starts=frozenset(), tz=ROOM_TZ) -> list[datetime]` 순수 함수 구현. DB 접근 없음(인자로 데이터 주입). 반환은 **tz-aware UTC** `slot_start` 리스트(오름차순).
  - [x] 규칙: ① `target_date`가 `holiday_dates`에 있으면 `[]`(휴무). ② `target_date.weekday()`(월=0)에 해당하는 `business_hours` 행이 없으면 `[]`(그 요일 미영업). ③ 있으면 `open_time`부터 1시간 간격으로 슬롯 생성, `slot_start_walltime + 1h <= close_time`인 동안 포함(부분 잔여 시간 제외 = 고정 1시간). ④ 각 슬롯의 벽시계 `(target_date, time)`를 **ROOM_TZ로 aware 생성 후 `.astimezone(UTC)`**(core/time 규약 — naive 금지). ⑤ `reserved_starts`(UTC 집합)에 있는 slot_start는 제외(2.1은 호출부가 빈 집합 전달, E4 4.9에서 실 예약 연결).
  - [x] `datetime.now()` 직접 호출 금지. 현재시각 비교가 필요하면 `app.core.time`의 `now_utc`/`today_in_tz` 사용(단, 본 함수는 `target_date`를 인자로 받으므로 now 의존 불필요).
- [x] **Task 5 — 테스트(pytest, 실 동작 검증 — 회고 A2)** (AC: 2, 3, 4)
  - [x] `tests/rooms/test_service.py`(미러 구조): 슬롯 도출 순수 함수 단위 테스트. 평일 정상(예: 09:00~22:00 KST → slot_start 13개, 첫 슬롯=`00:00:00Z`=09:00 KST−9h, 마지막=`12:00:00Z`=21:00 KST), 휴무일→`[]`, 미영업 요일→`[]`, `reserved_starts` 차감 검증(비어있지 않은 집합 전달 시 제거), 경계(마지막 슬롯이 정확히 close에 맞물림 / 부분 잔여 1시간 미만 제외), **모든 반환 slot_start의 `tzinfo`가 UTC**임 단언. Fake 자기충족 금지 — 함수가 순수라 실제 입력→출력을 직접 단언(인자 무시 Fake 불필요).
  - [x] `tests/rooms/test_models.py` 또는 통합: 제약명 ≤63자 단언(AC4 — 모델 메타데이터에서 제약명 추출해 `len(name) <= 63` 검증 = 회귀 가드). `SQLModel.metadata.tables`에서 rooms/business_hours/holiday_exceptions의 constraint 이름을 순회.
  - [x] (선택, CI-skip 통합) `tests/integration/`에 `TEST_DATABASE_URL` 가드로 실 테이블 생성·복합 UNIQUE 위반 왕복(라이브 DB 없으면 자동 skip) — 1.7 `test_auth_migration.py` 패턴. CI 라이브 DB는 배포 준비/A2에서 해소.
  - [x] 게이트 그린: `uv run ruff check . && uv run mypy && uv run pytest`(백엔드 무회귀 — 기존 139 passed·3 skip 유지/증가). `tests/test_main.py` 불변식(모듈 레벨 import 안전) 보존.

### Review Findings

> 코드 리뷰(2026-06-15, 3레이어 적대적 — Blind Hunter·Edge Case Hunter·Acceptance Auditor, 전 레이어 성공). Auditor 판정: **AC1~4 전부 PASS·스코프 경계 5종 전부 PASS·스코프 크리프 0**(provider_id UNIQUE·room_type 검증·P2·P3 모두 미구현·문서화 확인). 아래는 하드닝/테스트 품질 항목.

- [x] [Review][Patch] derive_slots 입력 fail-fast 가드 추가 (D1 — Decision→Patch, KTH 2026-06-15 옵션1) — **적용 완료**: `derive_slots` ⓪단계에 가드 추가 — `target_date`/`holiday_dates` 항목이 `datetime`이면 `ValueError`(datetime은 date 하위형이라 isinstance 통과하나 `date==datetime`은 항상 False → 휴무/요일 조용히 빗나감), `reserved_starts` 항목이 naive면 `ValueError`(aware UTC 슬롯과 안 같아 차감 실패). core/time `_require_aware` 철학과 일관. 회귀 테스트 3종 추가. [apps/api/app/rooms/service.py:64-82] (source: blind+edge)
- [x] [Review][Patch] `test_crossing_utc_date_boundary_evening` 오라벨·진짜 UTC 날짜경계 미검증 — **적용 완료**: 오라벨 테스트를 `test_evening_hours_stay_same_utc_date`로 정정(저녁 KST는 UTC 날짜 유지를 명시 단언) + 진짜 역방향 경계 테스트 `test_morning_hours_map_to_previous_utc_date` 추가(06:00 KST=전일 21:00 UTC → slot_start UTC 날짜≠target_date 검증, AC3 핵심). [apps/api/tests/rooms/test_service.py] (source: blind)
- [x] [Review][Defer] 비-KST tz의 DST gap/fold 미처리 — `tz` 파라미터 오버라이드 가능하나 DST 존에서 슬롯이 같은 UTC 인스턴트로 침묵 중복제거. KST 기본은 안전(1.5 멀티-tz defer 연속). [apps/api/app/rooms/service.py:84] — deferred, pre-existing
- [x] [Review][Defer] derive_slots room_id 미필터 — weekday만 필터해 서로 다른 room_id 행 혼입 시 합집합으로 병합(호출부 "그 룸의 행" 계약 의존). 소비처 연결(3.1) 시 하드닝. [apps/api/app/rooms/service.py:75] — deferred, pre-existing
- [x] [Review][Defer] created_at·is_active `server_default` 부재 — ORM 기본만 존재해 raw SQL insert 시 누락 가능. 1.7/1.8 User/RefreshToken과 동일한 기존 프로젝트 패턴. [apps/api/app/rooms/models.py:99-103] — deferred, pre-existing
- [x] [Review][Defer] price_per_hour·capacity·lat·lng 범위 CHECK 부재 — 음수 금액/인원·범위 밖 좌표 삽입 가능. 값 검증은 2.2 Pydantic 쓰기 경로 소유. [apps/api/app/rooms/models.py:88-97] — deferred, pre-existing
- [x] [Review][Defer] close_time==자정/역전 행이 순수 함수 도달 시 침묵 빈 결과 — DB CHECK가 라이브 경로 차단하나 순수 함수는 무검증. 자정 마감(오버나이트 영업) 모델 미지원. [apps/api/app/rooms/service.py:80-81] — deferred, pre-existing
- [x] [Review][Defer] UNIQUE(room_id, weekday)가 분할 영업시간(점심 브레이크 등) 차단 — 서비스 루프는 요일당 다중 행 처리하나 DB는 1행만 허용(방어 루프는 무해). 분할 교대 미지원=제품 결정. [apps/api/app/rooms/models.py:137] — deferred, pre-existing

## Dev Notes

### 스코프 경계 (중요 — 스코프 크리프 차단)
- **이 스토리는 데이터 모델 + 마이그레이션 + 순수 슬롯 도출 함수까지다.** HTTP 엔드포인트·라우터·요청/응답 스키마·쓰기 서비스·권한(RBAC) 게이트는 **만들지 않는다** — 공간 등록(provider 인증 쓰기)은 Story 2.2, 가용성 집계 엔드포인트는 Story 3.1.
- 따라서 `app/rooms/`에 생성하는 파일은 `models.py`·`service.py`(+ `tests/rooms/`)뿐. `router.py`/`schemas.py`는 만들지 않는다(2.2).
- `rooms` 테이블에 `provider_id` FK는 **지금 정의한다**(완전한 데이터 모델 — 나중에 NOT NULL FK를 ALTER로 추가하는 부담 회피). 단 **MVP "제공자당 1개" 제약(`UNIQUE(provider_id)`)은 Story 2.2의 비즈니스 규칙**이므로 여기서 추가하지 않는다(2.2가 서비스+필요 시 DB 제약으로 강제).

### Epic 1 회고 deferred 회수 라우팅 (P1/P2/P3) — KTH 결정 2026-06-15
- **P1(네이밍 63자) → 본 스토리에서 회수**(AC4/Task 1·3). `business_hours`·`holiday_exceptions`의 복합 UNIQUE에 명시 단축명 부여 + ≤63자 검증 + 정책 주석화.
- **P2(`IntegrityError` 제약명 선별 변환) → Story 2.2로 명시 편성**. 트리거=rooms insert 쓰기 경로(2.2). 2.1엔 쓰기 서비스가 없어 트리거 표면 없음. *재-defer 아님 — Epic 2 내 실트리거 스토리로 편성*(deferred-work.md 회수 라우팅 결정 섹션 참조).
- **P3(`role`/enum DB CHECK) → Story 2.2로 명시 편성**. 트리거=provider 권한으로 rooms 쓰기(2.2). 본 스토리가 신규 도입하는 `room_type`도 같은 enum-CHECK 계열 → 2.2에서 `role`·`room_type` DB CHECK를 한데 묶어 회수. **2.1은 `room_type`을 `role`과 동일하게 자유 문자열로 저장**, 검증은 2.2 Pydantic `Literal` 스키마(1.7 `RegisterRequest.role` 패턴 = `app/auth/schemas.py:40`).

### 아키텍처 규약 (반드시 준수)
- **네이밍**(architecture.md §Naming Patterns L228-241): 테이블 복수 snake_case(`rooms`·`business_hours`·`holiday_exceptions`), 컬럼 snake_case, FK=`{단수}_id`(`provider_id`·`room_id`), 인덱스 `idx_{table}_{cols}`, UNIQUE `uq_{table}_{cols}`, 시각 컬럼 `*_at`=UTC `timestamptz`. 제약명은 1.4 `NAMING_CONVENTION`(`app/core/db.py:28-35`)이 자동 부여하되, **복합 UNIQUE는 명시 단축명**(AC4).
- **시간**(architecture.md L126·263, core/time = `app/core/time.py`): slot_start=UTC 저장, 판정=Asia/Seoul. 와이어는 `...Z`. naive datetime 금지. `now_utc`/`today_in_tz`/`isoformat_utc` 단일 출처 — `datetime.now()` 직접 호출 금지.
  - **벽시계 vs 인스턴트 구분(핵심)**: `business_hours.open_time`/`close_time`은 **로컬 벽시계 시각**(KST 09:00 등) = `sa.Time`(tz 없음). `holiday_date`도 **ROOM_TZ 기준 날짜** = `sa.Date`. 반면 도출된 `slot_start`는 **UTC 인스턴트** = tz-aware datetime. 슬롯 도출이 (date + 벽시계 time, KST) → UTC 변환을 담당한다. 09:00 KST = 00:00 UTC(−9h).
- **스키마 소유**: Alembic 단독(`SQLModel.metadata.create_all` 절대 금지 — `app/core/db.py:9-10`). 테이블 생성은 마이그레이션만.
- **데이터 계층**: SQLModel(`app/core/db.py` 엔진/세션·네이밍 규약 이미 확립). 모델은 1.7 `User`/1.8 `RefreshToken`(`app/auth/models.py`) 스타일을 미러.

### 권장 구현 관용구 (실측 대조 필수 — 프리플라이트 ④)
- **UUID PK / FK**(1.8 `RefreshToken` 패턴, `app/auth/models.py:72-81`):
  ```python
  id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
  room_id: uuid.UUID = Field(sa_column=Column(
      Uuid(), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True))
  ```
  - `rooms.provider_id`는 **ondelete 미지정**(NO ACTION/RESTRICT) — 룸은 종속 폐기 데이터가 아니다(architecture: 룸 삭제 없음, 운영중단=계정 비활성 E8). business_hours/holiday_exceptions → rooms는 **CASCADE**(룸 종속 데이터).
- **timestamptz**(1.7/1.8 패턴): `created_at: datetime = Field(default_factory=now_utc, sa_column=Column(DateTime(timezone=True), nullable=False))`.
- **JSONB 배열**(`amenities`): SQLModel에서 list 타입은 명시 `sa_column` 필요. 권장:
  ```python
  from sqlalchemy.dialects.postgresql import JSONB
  amenities: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
  ```
  설치된 sqlmodel 소스로 list+JSONB 매핑 관용구를 실측 확인(default_factory와 sa_column 병용 시 동작).
- **`sa.Time`/`sa.Date`**: `open_time: time = Field(sa_column=Column(Time, nullable=False))`, `holiday_date: date = Field(sa_column=Column(Date, nullable=False))`. Python `datetime.time`/`datetime.date` 매핑.
- **`__table_args__`로 복합 제약 + CHECK**(명시 단축명 — AC4):
  ```python
  from sqlalchemy import CheckConstraint, UniqueConstraint
  __table_args__ = (
      UniqueConstraint("room_id", "weekday", name="uq_business_hours_room_id_weekday"),
      CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_business_hours_weekday"),
      CheckConstraint("close_time > open_time", name="ck_business_hours_hours_order"),
  )
  ```
  - 제약명 글자수(검증 완료 예상): `uq_business_hours_room_id_weekday`=32, `uq_holiday_exceptions_room_id_holiday_date`=42, FK 최장 `fk_holiday_exceptions_room_id_rooms`=35 — 모두 ≤63. 그래도 Task 3에서 실제 len 단언으로 확정.
  - CHECK 2종은 AC2의 "weekday 0~6"·"같은 날 내(자정 넘김 없음)"를 **DB 레벨에서 강제**(close_time>open_time이면 자정 미교차). 2.2의 친절한 422 거부는 그 위 Pydantic 레이어(defense-in-depth, 1.7 email UNIQUE 패턴과 동일).

### 슬롯 도출 로직 정밀 명세 (AC2/AC3)
- 입력: 한 룸의 `business_hours`(요일별 행), `holiday_dates`(ROOM_TZ date 집합), `target_date`(도출 대상 날짜), `reserved_starts`(UTC slot_start 집합, 2.1=빈 집합), `tz`(기본 ROOM_TZ).
- 출력: 오름차순 tz-aware UTC `slot_start` 리스트. 휴무/미영업/전부예약 시 `[]`.
- 절차: 휴무 검사 → 요일 영업행 조회 → `open_time`부터 `timedelta(hours=1)` 스텝, `walltime + 1h <= close_time` 동안 슬롯 생성 → 각 슬롯 `datetime.combine(target_date, walltime, tzinfo=tz).astimezone(UTC)` → `reserved_starts` 차감 → 정렬 반환.
- 결정성: KST(Asia/Seoul)는 DST 없음 — combine+astimezone 안전(DST gap/fold 경계는 1.5 defer, 멀티-tz 도입 시). 부동소수 시간연산 미사용(정수 시간 스텝).
- 소비처(후속): Story 3.1(가용성 집계 = "오늘 남은 빈 슬롯 수"), Story 4.x(예약 차감 연결 = 4.9). 본 함수가 그 단일 출처.

### 의존 인프라 점검 (전부 done·견고 — 회고 §6)
- 1.4 DB/Alembic/네이밍 규약(`app/core/db.py`·`alembic/env.py`) · 1.5 core/time(`app/core/time.py`) · 1.5 core/errors(2.2 라우터에서 사용) · 1.7/1.8 모델 패턴(`app/auth/models.py`). 모두 그대로 재사용.

### Project Structure Notes
- 신규 파일: `apps/api/app/rooms/models.py`, `apps/api/app/rooms/service.py`, `apps/api/tests/rooms/__init__.py`, `apps/api/tests/rooms/test_service.py`, `apps/api/tests/rooms/test_models.py`, 신규 alembic 리비전 1개.
- 수정 파일: `apps/api/alembic/env.py`(rooms 모델 import 허브 주석 해제 1줄).
- `app/rooms/__init__.py`는 이미 존재(빈 패키지, 1.2 스캐폴드). `router.py`/`schemas.py` **생성 안 함**(2.2).
- 충돌/변이 없음: 기존 auth 도메인·core·main 무수정(rooms는 신규 격리 도메인, main 라우터 배선은 엔드포인트가 생기는 2.2부터).

### References
- [Source: epics.md#Story-2.1] (L464-480) — AC 원문, 슬롯 = (영업시간 − 휴무 − 예약), 고정 1h, 같은 날 내.
- [Source: epics.md#Story-2.2/2.3] (L482-524) — 후속 경계(등록=쓰기/주소검색/1개 제약=2.2, 수정=2.3, 삭제 없음).
- [Source: architecture.md#Data-Architecture] (L141-153) — 영업시간/휴무 모델, 좌표+행정동 이중 저장, slot_start=UTC.
- [Source: architecture.md#Naming-Patterns] (L226-241) — 테이블/컬럼/FK/인덱스/UNIQUE/시각 컬럼 규약.
- [Source: architecture.md#Structure-Patterns] (L248-254) — `app/{domain}/{router,models,schemas,service}.py`, tests 미러.
- [Source: architecture.md#Cross-Component] (L360-362) — 슬롯=도출(물리테이블 아님), 점유=reservations 행, UNIQUE=진실의 원천.
- [Source: app/core/db.py:28-35] — `NAMING_CONVENTION`(idx_/uq_/ck_/fk_/pk_), import 시점 등록.
- [Source: app/core/time.py] — `now_utc`/`to_tz`/`today_in_tz`/`isoformat_utc`/`_require_aware`, ROOM_TZ=Asia/Seoul.
- [Source: app/auth/models.py:40-91] — `User`/`RefreshToken` 모델 스타일(uuid PK·FK ondelete·timestamptz·StrEnum).
- [Source: app/auth/schemas.py:35-56] — (2.2 참고) `Literal` role 검증 패턴 = room_type 검증의 향후 모델.
- [Source: alembic/env.py:47-52] — rooms 모델 import 허브(주석 해제 대상).
- [Source: alembic/versions/ac9b81f7d058...py] — 현재 head(down_revision 기준점) + 수기 마이그레이션·`import sqlmodel`·FK CASCADE 패턴.
- [Source: deferred-work.md#회수-라우팅-결정] — P1(2.1)/P2·P3(2.2) 라우팅 결정 근거.
- [Source: epic-1-retro-2026-06-15.md#5·6] — A1 프리플라이트·A2 테스트 충실도·즉시회수 P1~3.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Opus 4.8, 1M context)

### Debug Log References

**반복 함정 프리플라이트 결과 (Epic 1 회고 A1 — 매 dev-story 의무):**
- ① **Windows UTF-8** — 모델/마이그레이션/테스트 파일에 한국어 주석 포함. 모든 파일은 UTF-8로
  생성됐고, 오프라인 `--sql` 출력의 한글 깨짐은 콘솔(cp949) 표시 한계일 뿐 파일 IO는 UTF-8(정상).
  pytest 실패 트레이스의 한글 깨짐도 동일(콘솔 인코딩) — 소스/테스트 파일 자체는 UTF-8.
- ② **신규 런타임 의존성 0** — 예상대로 신규 의존성 없음. `JSONB`=`sqlalchemy.dialects.postgresql`,
  `Time`/`Date`/`CheckConstraint`/`UniqueConstraint`=SQLAlchemy 기본, `uuid`/`datetime`/`zoneinfo`=stdlib.
  pyproject 무변경.
- ③ **import 시점 부작용 금지** — `models.py`는 `app.core.time`(ROOM_TZ/now_utc)만 import(순수 모델 정의).
  `service.py`는 `app.core.time`+`app.rooms.models`만 import, DB 접근 0. `derive_slots`는 순수 함수
  (모든 입력 인자 주입, `datetime.now()` 미호출). test_main 모듈 레벨 import 안전 불변식 보존(통과).
- ④ **외부 라이브러리 API 실측** — 설치된 sqlmodel 0.0.38/sqlalchemy 2.0.50로 직접 프로브 실행:
  `list[str]`+`Column(JSONB)`+`default_factory=list` 병용 동작 확인(신규 인스턴스 `[]`·왕복 보존),
  `Column(Time)`/`Column(Date)`→`TIME`/`DATE` 렌더, `__table_args__` 복합 UNIQUE/CHECK 부여 확인.

### Completion Notes List

- **신규 모듈 2개·테이블 3개로 스코프 차단 준수**: `app/rooms/models.py`(Room/BusinessHours/
  HolidayException + RoomType StrEnum)·`app/rooms/service.py`(derive_slots 순수 함수)만 생성.
  `router.py`/`schemas.py`는 만들지 않음(2.2). main 라우터 배선·쓰기 서비스·RBAC 없음.
- **AC4 회수 + 새 함정 발견·해소(이 프로젝트 첫 CHECK 제약)**: 복합 UNIQUE 2종 + CHECK 2종에 명시
  단축명 부여. 검증 중 **CHECK 제약의 이중접두 함정**을 발견 — 네이밍 규약 `ck`템플릿이
  `ck_%(table_name)s_%(constraint_name)s`라, `name="ck_business_hours_weekday"` 전체명을 주면
  `ck_business_hours_ck_business_hours_weekday`로 이중접두됨(UNIQUE는 `column_0_N_name` 기반이라
  무영향). **CHECK는 접미사만**(`name="weekday"`/`"hours_order"`) 전달해 `ck_business_hours_weekday`로
  해석. 중요: alembic `op.create_table`도 `target_metadata`의 규약을 상속하므로 **마이그레이션
  파일의 CHECK도 접미사만** 줘야 모델↔DB 이름 일치(불일치 시 autogenerate 영구 drift) — 오프라인
  `--sql`로 실증. 제약명 글자수(전부 ≤63): `uq_holiday_exceptions_room_id_holiday_date`=42(최장),
  `fk_holiday_exceptions_room_id_rooms`=35, `ck_business_hours_hours_order`=29, `pk_rooms`=8.
  `tests/rooms/test_models.py`가 ≤63 + 이중접두 부재를 회귀 가드.
- **마이그레이션 운영 DB 미변조**: 라이브 연결 없이 `alembic upgrade ac9b81f7d058:head --sql`(오프라인)로
  3테이블 CREATE + 제약/인덱스/JSONB/Time/Date/timestamptz DDL 실증, `downgrade e3dbb470902f:ac9b81f7d058
  --sql`로 왕복(역순·FK 안전) 실증. down_revision=ac9b81f7d058(현재 head=refresh_tokens). FK: rooms→users
  ondelete 미지정(룸 비폐기), business_hours/holiday_exceptions→rooms CASCADE(룸 종속).
- **슬롯 도출 = 결정적 벽시계→UTC**: `open_time`/`close_time`(벽시계 sa.Time)을 `target_date`와 결합,
  `replace(tzinfo=ROOM_TZ).astimezone(UTC)`로 UTC 인스턴트화(09:00 KST=00:00 UTC). 고정 1h
  (`walltime+1h<=close_time`), 휴무/미영업/예약 차감. 반환은 오름차순 tz-aware UTC. reserved_starts는
  2.1에서 빈 집합(실 예약 차감은 E4 4.9 연결).
- **게이트 그린**: `uv run ruff check .`(All checks passed) · `uv run mypy`(Success, 21 files) ·
  `uv run pytest` **152 passed · 4 skipped**(이전 139 passed·3 skip → 신규 통과 13 = test_service 10 +
  test_models 3, 신규 skip 1 = 통합 test_rooms_migration[TEST_DATABASE_URL 가드]). 백엔드 무회귀.

### File List

**신규:**
- `apps/api/app/rooms/models.py` — Room/BusinessHours/HolidayException ORM + RoomType StrEnum
- `apps/api/app/rooms/service.py` — derive_slots 순수 함수
- `apps/api/alembic/versions/e3dbb470902f_create_rooms_business_hours_holiday_.py` — rooms 3테이블 마이그레이션
- `apps/api/tests/rooms/__init__.py`
- `apps/api/tests/rooms/test_service.py` — 슬롯 도출 단위 테스트(10)
- `apps/api/tests/rooms/test_models.py` — 제약명 ≤63자 + 이중접두 부재 회귀 가드(3)
- `apps/api/tests/integration/test_rooms_migration.py` — 마이그레이션·복합 UNIQUE·CHECK 왕복(skipif)

**수정:**
- `apps/api/alembic/env.py` — rooms 모델 import 허브 등록(`_rooms_models`)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — 2.1 in-progress→review

## Change Log

| 날짜 | 변경 | 비고 |
|------|------|------|
| 2026-06-15 | Story 2.1 구현 완료 → review | rooms 3테이블 모델·마이그레이션·derive_slots 순수 함수. AC1~4 충족. CHECK 이중접두 함정 발견·해소. ruff/mypy 그린, pytest 152 passed·4 skip. |
| 2026-06-15 | Story 2.1 code-review → done | 3레이어 적대적 리뷰(Auditor: AC1~4·스코프 경계 5종 PASS·크리프 0). decision1/patch2/defer6/dismiss5. patch2 적용=①derive_slots 입력 fail-fast 가드(naive reserved·datetime holiday/target 거부, D1 옵션1) ②오라벨 테스트 정정+진짜 UTC 역방향 경계 테스트 추가. defer6→deferred-work(비-KST DST·room_id 미필터·server_default·범위 CHECK·자정마감·분할영업). 게이트 재그린: ruff/mypy 그린, pytest 156 passed·4 skip. |
