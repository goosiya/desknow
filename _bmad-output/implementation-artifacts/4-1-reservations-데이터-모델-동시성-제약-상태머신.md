---
baseline_commit: NO_VCS
---

# Story 4.1: reservations 데이터 모델 & 동시성 제약·상태머신

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 개발자,
I want 예약 테이블과 동시성 제약·상태 전이 머신을 정의하길,
so that 중복·부분 점유 0건과 원자·멱등 상태 전이가 데이터 계층에서 보장된다 (FR-15·16 기반, NFR-7).

이 스토리는 **데이터 계층 foundation**이다 — Story 2.1(rooms 모델 + `derive_slots` 순수 함수, 라우터 없음)과 **동형**이다. 모델·마이그레이션·서비스 프리미티브·테스트까지만 책임지고, **라우터/엔드포인트/예약 UI는 명시적으로 범위 밖**이다(아래 "범위 경계"). Epic 4의 모든 후속 스토리(4.5 즉시예약·4.6 동시성 엣지·4.7 취소·4.8 현황·4.9 차감)가 이 계층 위에 쌓인다.

## Acceptance Criteria

1. **(AC1 — 스키마·제약)** `reservations` 도메인 마이그레이션을 `alembic upgrade head`로 적용하면 **두 테이블**이 생성된다: `reservations`(예약 단위 — `booker_id`·`room_id`·`status`·`created_at`)와 `reservation_slots`(슬롯 점유 행 — `reservation_id` FK·`room_id`·`slot_start`). `reservation_slots`에 **FULL `UNIQUE(room_id, slot_start)`**(명시 단축명 `uq_reservation_slots_room_slot`)가 적용되어 한 룸·한 슬롯에 활성 점유가 **최대 1행**임을 DB가 강제한다.
2. **(AC2 — 상태 전이 원자·멱등)** 예약 상태(`confirmed`/`cancelled`/`rejected`)에서 전이를 수행하면 **원자적 단일 연산**(단일 트랜잭션 commit)이고, **종료 상태(`cancelled`·`rejected`)에 대한 추가 전이는 멱등하게 무시**되고 현재 상태를 반환한다(에러 아님).
3. **(AC3 — 동일 트랜잭션 점유/재활성)** 슬롯 점유(생성 시 `reservation_slots` INSERT)와 재활성(취소/거절 시 `reservation_slots` DELETE)은 **상태 전이와 동일 트랜잭션 내에서만** 일어난다. 점유는 **all-or-nothing**(선택 슬롯 전체 성립 또는 0건 — 부분 점유 없음)이고, 충돌 시 전체 ROLLBACK 후 `SLOT_CONFLICT`(409) 신호를 낸다.
4. **(AC4 — 회귀 가드)** `reservations` 도메인의 모든 제약·인덱스 이름이 **≤63자**(PostgreSQL 식별자 한계)이고, 복합 제약 명시 단축명(`uq_reservation_slots_room_slot`)·CHECK(`ck_reservations_status`)가 **이중접두 없이** 의도대로 해석됨을 DB-불필요 메타데이터 테스트로 검증한다(2.1 회귀 가드 패턴 계승).

> **참고(상위 스토리가 소비):** 동시성 불변식의 **진정한 멀티스레드 동시 검증(SM-4)**·409 마이크로카피·인접 슬롯 재표시는 **Story 4.6** 소유다. 본 스토리는 데이터 계층 프리미티브와 **순차 UNIQUE 왕복**(중복 INSERT→`IntegrityError`)으로 불변식의 **메커니즘**을 증명한다. 6시간 취소 윈도우는 **Story 4.7**, 예약 차감 배선은 **Story 4.9**가 소유한다.

## Tasks / Subtasks

- [x] **Task 1 — ORM 모델 2종 정의** (AC: 1, 4) — `apps/api/app/reservations/models.py` (신규)
  - [x] `ReservationStatus(StrEnum)`: `CONFIRMED="confirmed"` · `CANCELLED="cancelled"` · `REJECTED="rejected"`. **코드 측 참조값** — `room_type`/`role`(1.7/2.1) 동일 패턴(자유 문자열 저장 + DB CHECK + Pydantic Literal로 최종 검증). 종료 상태 집합 상수 `_TERMINAL_STATUSES = frozenset({CANCELLED, REJECTED})`를 함께 정의(상태머신 단일 출처).
  - [x] `Reservation(SQLModel, table=True)` `__tablename__="reservations"` — `id`(UUID PK) · `booker_id`(FK `users.id`, **ondelete 미지정=RESTRICT**, `index=True`) · `room_id`(FK `rooms.id`, **ondelete 미지정=RESTRICT**, `index=True`) · `status: str`(`ReservationStatus` 값, 기본 `confirmed`) · `created_at`(UTC `timestamptz`, `default_factory=now_utc`). `__table_args__`: `CheckConstraint("status IN ('confirmed','cancelled','rejected')", name="status")` → 최종명 `ck_reservations_status`(**ck 규약 이중접두 함정 — name엔 접미사만**, 2.1 `business_hours` 선례).
  - [x] `ReservationSlot(SQLModel, table=True)` `__tablename__="reservation_slots"` — `id`(UUID PK) · `reservation_id`(FK `reservations.id`, **ondelete=CASCADE** — 점유는 예약 종속 자식 데이터, `index=True`) · `room_id`(FK `rooms.id`, **ondelete 미지정=RESTRICT**, denormalized — UNIQUE·4.9 조회를 조인 없이) · `slot_start`(**UTC `timestamptz`** = `Column(DateTime(timezone=True), nullable=False)` — `derive_slots`가 내는 aware UTC 인스턴트와 동형). `__table_args__`: `UniqueConstraint("room_id", "slot_start", name="uq_reservation_slots_room_slot")`(복합 2컬럼 → **명시 단축명**, 회고 P1 + deferred L71 회수, 30자 ≤63 ✓).
  - [x] **재활성=DELETE 설계 근거를 docstring에 고정**: `cancelled`/`rejected` 시 `reservation_slots` 행을 **DELETE**하므로 테이블엔 **활성(confirmed) 점유만 잔존** → **FULL UNIQUE로 충분**(부분 인덱스 `WHERE status='confirmed'` 불요). 예약 단위(`reservations`)는 status로 히스토리에 남는다(4.7 "예약은 히스토리에 취소 상태로 남는다" + 4.8 현황).
- [x] **Task 2 — 마이그레이션 생성** (AC: 1, 3) — `apps/api/alembic/versions/*_create_reservations_tables.py` (신규)
  - [x] `down_revision` = **현재 head**(favorites `181925e12bb8`로 추정 — `uv run alembic heads`로 **반드시 실측 확인** 후 단일 head에 체이닝). 두 테이블 + 제약 모두 생성. autogenerate(`uv run alembic revision --autogenerate -m "create reservations tables"`) 후 **수기 검수**(`import sqlmodel` 라인 보존·제약명 일치).
  - [x] **`--sql` 오프라인 산출명이 모델 메타와 정확히 일치**하는지 확인(drift 0 — 2.2 패턴): `uq_reservation_slots_room_slot` · `ck_reservations_status`(이중접두 아님) · PK/FK/INDEX 규약 자동명.
  - [x] **라이브 DB 적용 의무**(메모 [[dev-workflow-policy-live-db-migration]]): dev 완료 시 라이브 Supabase에 `uv run alembic upgrade head` **실제 실행** + `downgrade -1`/`upgrade head` 왕복 무결성 확인.
- [x] **Task 3 — 서비스 프리미티브(전체 데이터 계층)** (AC: 2, 3) — `apps/api/app/reservations/service.py` (신규)
  - [x] `create_reservation(session, *, booker_id, room_id, slot_starts: Collection[datetime]) -> Reservation`: ⓐ 입력 계약 fail-fast(`slot_starts` 비어있으면 `ValueError`; 각 항목 **aware UTC** 아니면 `ValueError` — `core/time` `_require_aware` 철학·`derive_slots` 선례). ⓑ `Reservation(status=confirmed)` + 각 `slot_start`당 `ReservationSlot` **단일 트랜잭션 다중행 INSERT**. ⓒ **all-or-nothing**: 어느 슬롯이라도 `uq_reservation_slots_room_slot` 충돌 시 `IntegrityError` → `session.rollback()`(전체 0건 — 부분 점유 없음) → `violated_constraint(exc) == "uq_reservation_slots_room_slot"`이면 `DomainError(ErrorCode.SLOT_CONFLICT)`(409)로 변환, **무관 위반은 re-raise**(P2 과대캐치 금지). ⓓ 성공 시 `commit`+`refresh` 후 `Reservation` 반환.
  - [x] `cancel_reservation(session, reservation) -> Reservation`: 종료 상태면(`status in _TERMINAL_STATUSES`) **멱등 no-op**(현재 상태 그대로 반환·DB 쓰기 0 — AC2). 아니면 `status=CANCELLED` + `_release_slots`(아래) **동일 트랜잭션** `commit`(AC3).
  - [x] `reject_reservation(session, reservation) -> Reservation`: `cancel_reservation`과 동형(목표 상태 `REJECTED`). 제공자 거절(E6/4.x)이 소비. 멱등·동일 트랜잭션 동일.
  - [x] `_release_slots(session, reservation_id) -> None`(내부): `DELETE FROM reservation_slots WHERE reservation_id=...`(`session.exec(delete(...))` 또는 행 조회 후 `session.delete`). 재활성 = 점유 행 제거(슬롯이 다시 빔). **commit은 호출처가**(동일 트랜잭션 보장 — `update_room`의 flush 선례 참조).
  - [x] `confirmed_slot_starts(session, room_id, *, on_or_after: datetime | None = None) -> set[datetime]`(읽기 전용, **Story 4.9 차감 seam**): 그 룸의 활성 점유 `slot_start`(UTC aware) 집합 반환. **도메인 경계 준수**(architecture.md L354) — 4.9의 `rooms.service`가 `reservation_slots` SQL을 직접 만지지 않고 이 함수를 경유해 `derive_slots(..., reserved_starts=...)`에 주입한다. 본 스토리는 함수를 **정의**만 하고(테스트 포함), 실제 `derive_slots` 배선은 4.9.
  - [x] **상태머신 단일 출처**: 허용 전이(`confirmed→cancelled`·`confirmed→rejected`)·종료 상태·멱등 규칙을 모듈 docstring에 명문화(추측 금지 — architecture.md "상태 전이는 서버 단일 연산").
- [x] **Task 4 — 메타데이터 회귀 테스트(DB 불필요)** (AC: 4) — `apps/api/tests/reservations/test_models.py` (신규, `tests/rooms/test_models.py` 미러)
  - [x] `test_all_constraint_names_within_63_chars`: `reservations`·`reservation_slots` 모든 제약·인덱스 ≤63자.
  - [x] `test_expected_composite_constraint_names_present`: `uq_reservation_slots_room_slot` 존재 + `ck_reservations_status` 존재 + **이중접두 부재**(`ck_reservations_ck_reservations_status` not in).
  - [x] `test_expected_pk_fk_index_names_present`: `pk_reservations`·`fk_reservations_booker_id_users`·`fk_reservations_room_id_rooms`·`idx_reservations_booker_id`·`idx_reservations_room_id`·`pk_reservation_slots`·`fk_reservation_slots_reservation_id_reservations`·`fk_reservation_slots_room_id_rooms`·`idx_reservation_slots_reservation_id` 자동명 존재(FK 자동명 길이도 ≤63 — `fk_reservation_slots_reservation_id_reservations`=48자 ✓).
- [x] **Task 5 — 상태머신 단위 테스트(DB 불필요)** (AC: 2) — `apps/api/tests/reservations/test_service.py` (신규)
  - [x] 멱등성: 이미 `cancelled`/`rejected`인 예약에 `cancel_reservation`/`reject_reservation` 재호출 → **현재 상태 그대로·쓰기 0**(Fake/스텁 세션의 `commit`/`delete` 미호출 단언 — 1.7 `FakeSession` 패턴 참고하되 쿼리 무시 한계 인지).
  - [x] 입력 계약: `create_reservation`에 빈 `slot_starts`·naive datetime → `ValueError`(라이브 DB 불필요한 fail-fast 경로).
- [x] **Task 6 — 마이그레이션·제약·상태머신 왕복 통합 테스트(라이브 DB·기본 skip)** (AC: 1, 2, 3) — `apps/api/tests/integration/test_reservations_migration.py` (신규, `test_rooms_migration.py` 미러·`TEST_DATABASE_URL` 가드)
  - [x] `upgrade head` 후 두 테이블 + `uq_reservation_slots_room_slot`·`ck_reservations_status` 존재.
  - [x] **UNIQUE 왕복**: provider+room+booker 시드 → `create_reservation([slotA])` 성공 → 동일 `(room_id, slotA)` 재점유 시도 → `SLOT_CONFLICT`(부분 점유 0 — `reservation_slots` 행 수 불변 단언).
  - [x] **all-or-nothing**: `create_reservation([slotA, slotB])`에서 `slotA`가 이미 점유면 **전체 실패·0건**(slotB도 미점유 단언).
  - [x] **재활성 왕복(AC3)**: 점유 → `cancel_reservation` → `reservation_slots` DELETE 확인 + `reservations.status='cancelled'` **잔존**(히스토리) → **같은 슬롯 재점유 성공**(slot 재활성 증명).
  - [x] **CHECK**: `status='pending'`(비허용) ORM 삽입 → `IntegrityError`(`ck_reservations_status`).
  - [x] `finally: downgrade base` 정리.

## Dev Notes

### 핵심 설계 결정 (KTH 확정 2026-06-16)

1. **2-테이블 설계 확정.** `reservations`(예약 단위 = 상태머신·히스토리 보유, 1행/예약) + `reservation_slots`(점유 행 = room_id·slot_start, N행/예약). **이유:** 세 요구를 동시에 깔끔히 만족 — ⓐ 취소 예약은 히스토리에 남고(4.7·4.8: `reservations.status='cancelled'` 잔존) ⓑ 슬롯은 재활성(4.7: `reservation_slots` 행 DELETE → 슬롯이 다시 빔) ⓒ UNIQUE(room_id, slot_start)로 중복·부분점유 0(4.6). 상태가 **단일 행 1컬럼**이라 전이가 원자·멱등 자명(단일행 status flip). 4.8 히스토리는 **예약 단위 조회**(슬롯 아님)라 자연스럽다.
   - **아키텍처와의 관계:** architecture.md L366("점유는 reservations 행(room_id, slot_start)으로 표현 → UNIQUE 제약이 진실의 원천")·L149-150("확정 예약은 slot_start 자체 보유")는 prose가 점유 행을 "reservations 행"으로 접어 표현한 것이다. 본 설계는 그 **점유 행을 `reservation_slots`로 분리해 정밀화**한 refinement이며 모순이 아니다 — 점유의 진실의 원천은 여전히 `UNIQUE(room_id, slot_start)`이고, 확정 예약 슬롯은 `reservation_slots.slot_start`(UTC)를 보유해 영업시간 변경에 독립(FR-22, `update_room` docstring L617-621이 이미 이 불변식을 전제).
   - **FULL UNIQUE(부분 인덱스 불요):** 취소/거절 시 점유 행을 **DELETE**하므로 `reservation_slots`엔 항상 **활성(confirmed) 점유만** 존재한다 → `WHERE status='confirmed'` 부분 유니크 인덱스가 필요 없다. `reservation_slots`엔 status 컬럼 자체를 두지 않는다(상태는 부모 `reservations`에만 — 단일 출처).

2. **4.1 = 전체 데이터 프리미티브 확정.** `create_reservation`(원자 all-or-nothing) + `cancel`/`reject`(멱등·동일트랜잭션 재활성) + `confirmed_slot_starts`(4.9 seam) + 상태머신을 모두 4.1이 소유·테스트한다. 제목("동시성 제약·상태머신")을 실체화·자기완결한다. **쓰기 경로의 상위 절반(엔드포인트·동시성 409 마이크로카피·예약 UI·6h 윈도우·실 동시 SM-4 테스트)은 4.5~4.7 소유**(아래 범위 경계).

### 범위 경계 (스코프 크리프 방지 — 2.1과 동형)

| 본 스토리(4.1) **소유** | 명시적 **범위 밖**(후속) |
|---|---|
| `reservations`·`reservation_slots` 모델 + 마이그레이션 + UNIQUE/CHECK | 라우터·엔드포인트·OpenAPI/SDK 재생성 (4.5 즉시예약 / 4.7 취소 / 4.8 현황) |
| 서비스 프리미티브: `create_reservation`·`cancel`·`reject`·`_release_slots`·`confirmed_slot_starts` | 예약 UI·달력·슬롯 피커·연속 선택 (4.2·4.3·4.4) |
| 상태머신(전이·종료·멱등) + 순차 UNIQUE 왕복 통합 테스트 | 실 멀티스레드 동시 SM-4 테스트·409 카피·인접 슬롯 재표시 (4.6) |
| `confirmed_slot_starts` **정의**(4.9 차감 seam) | 6h 취소 윈도우(`is_within_hours`) (4.7) · `derive_slots` 실제 차감 배선 (4.9) |

- **신규 ErrorCode 0.** `SLOT_CONFLICT`(409)는 1.5에서 이미 정의됨(`core/errors.py:36`). `CANCEL_WINDOW_PASSED`(409)도 1.5에 있으나 **4.7 소유**(본 스토리 미사용). 새 코드 추가 금지.
- **`reservations/schemas.py`·`router.py`는 본 스토리에서 생성하지 않는다.** 응답 DTO(`ReservationPublic` 등)는 엔드포인트가 생기는 4.5/4.8이 소유한다. `reservations/__init__.py`는 이미 존재(빈 패키지).

### 코드 재사용 / 따라야 할 선례 (재발명 금지)

- **모델 패턴** = `apps/api/app/favorites/models.py`(3.7, 가장 최근 신규 도메인 테이블) + `apps/api/app/rooms/models.py`(2.1, CHECK·복합 UNIQUE·StrEnum 선례). `Column(Uuid(), ForeignKey, nullable=False, index=True)` FK 형식·`default_factory=now_utc` `timestamptz`·복합 제약 명시 단축명을 **그대로** 따른다.
- **마이그레이션 패턴** = `apps/api/alembic/versions/181925e12bb8_create_favorites_table.py`(3.7). `import sqlmodel` 라인·`op.f()` 자동명·복합 UNIQUE `name=` 명시·한국어 docstring(down_revision·라이브 DB 적용 명시)을 따른다.
- **`IntegrityError` 선별 변환** = `apps/api/app/core/db.py:violated_constraint`(2.2 도입) + `rooms/service.py:create_room`(L581-590) 선례. `except IntegrityError → rollback → violated_constraint로 제약명 식별 → 해당 위반만 DomainError 변환, 그 외 re-raise`. **포괄 캐치(과대캐치) 금지**(1.7 P2 회고).
- **시간 규약** = `apps/api/app/core/time.py`. `slot_start`는 UTC aware(`now_utc`·`derive_slots` 출력과 동형). naive 거부(`_require_aware` 철학). `datetime.now()` 직접 호출 금지.
- **순수/주입 테스트 가능성** = `derive_slots`(2.1)·`aggregate_availability`(3.1)의 `now` 주입·읽기전용 단언 패턴. 서비스 함수는 `session` 주입.
- **메타데이터 회귀 테스트** = `tests/rooms/test_models.py`(2.1) **거의 그대로** 미러(테이블명·기대 제약명만 교체).
- **통합 테스트** = `tests/integration/test_rooms_migration.py`(2.1) 미러(`TEST_DATABASE_URL` 가드·`get_settings/get_engine.cache_clear()`·`finally downgrade base`).

### 반복 함정 프리플라이트 (메모 [[dev-workflow-policy-deferred-and-repeat-mistakes]] ⑤⑥ + Epic1~3 회고)

1. **ck 이중접두 함정(2.1 실발생):** `CheckConstraint(name=...)`의 `name`엔 **접미사만**(`"status"`) — ck 규약 `ck_%(table_name)s_%(constraint_name)s`가 접두하므로 전체명을 주면 `ck_reservations_ck_reservations_status`가 된다. Task 4 테스트가 이 회귀를 가드.
2. **63바이트 절단(deferred L71, 1.4 — 본 스토리에서 발화·회수):** 복합 UNIQUE는 **명시 단축명**(`uq_reservation_slots_room_slot`) 부여 + ≤63 테스트. FK 자동명 중 가장 긴 `fk_reservation_slots_reservation_id_reservations`(48자, 규약 `fk_{table}_{col}_{ref}`)도 ≤63 확인.
3. **IntegrityError 과대캐치(1.7 P2):** `violated_constraint`로 `uq_reservation_slots_room_slot`만 `SLOT_CONFLICT` 변환. 무관 위반(FK 등) re-raise.
4. **부분 점유(4.6 불변식의 데이터 근거):** 다중행 INSERT는 **단일 트랜잭션** — 한 슬롯 충돌 시 전체 ROLLBACK으로 0건(plain 다중행 INSERT + `IntegrityError` 캐치면 자연히 all-or-nothing; `ON CONFLICT DO NOTHING` + affected=N 검증도 동등 — 어느 쪽이든 **부분 커밋 금지**가 핵심). 겹치되 시작 다른 두 예약(14~17 vs 16~18)도 한쪽 전체 성립·다른쪽 0 점유가 자동 만족(4.6 AC2의 데이터 근거).
5. **server_default 부재(누적 defer — 1.7/2.1과 동일 패턴 유지):** `created_at`·`status` 기본값은 ORM 레이어(`now_utc`·`default`)에만 둔다(프로젝트 일관 — ORM이 유일 writer). raw SQL writer 도입 시점에 일괄 `server_default` 회수(기존 defer와 통합 — 본 스토리에서 신규 도입 안 함).
6. **naive datetime:** `create_reservation`이 `slot_start` aware UTC를 fail-fast 검증(조용한 차감 실패 방지 — `derive_slots`의 `reserved_starts` naive 거부와 동일 철학).

### 의무 회수 / Forward seam

- ✅ **회수(트리거 발화):** deferred-work.md L71(1.4 code review — "네이밍 규약 63자 한계, 트리거=4.1 reservations 등 복합 UNIQUE 추가 시점")를 본 스토리에서 회수 — `uq_reservation_slots_room_slot` 명시 단축명 + Task 4 ≤63 회귀 테스트. dev 완료 시 deferred-work.md에 회수 표기.
- 🔜 **Forward(본 스토리 정의·후속 소비):** `confirmed_slot_starts`는 4.9가 `derive_slots(..., reserved_starts=...)`에 주입(2.1 deferred L38 "derive_slots reserved_starts seam"의 데이터 공급원). 본 스토리는 함수 정의·테스트까지, 배선은 4.9.
- 🔜 **Forward(미발화 — 후속 소유):** `hours_until` float 경계 정밀도(deferred L77, 1.5)는 **4.7**(6h 취소)이 트리거. 본 스토리는 시간 경계 판정 없음(상태 전이만) → 해당 없음.

### Project Structure Notes

- **신규 파일:** `apps/api/app/reservations/{models,service}.py` · `apps/api/alembic/versions/*_create_reservations_tables.py` · `apps/api/tests/reservations/{__init__,test_models,test_service}.py` · `apps/api/tests/integration/test_reservations_migration.py`.
- **수정 파일:** 없음(앱 코드). `reservations/__init__.py` 기존 빈 패키지 유지. `alembic/env.py`는 `app.*.models`를 이미 import하면 추가 불필요 — **실측 확인**(`env.py`가 reservations 모델을 metadata에 등록하는지: 미등록이면 autogenerate가 테이블을 못 봄 → import 추가). `app.main`/라우터 등록은 본 스토리 무변경(엔드포인트 없음).
- **도메인 경계(architecture.md L354-355):** `reservations.service`는 `reservations`·`reservation_slots`만 만진다. `rooms`를 import하지 않는다(4.9가 역방향으로 `rooms.service`에서 `reservations.service.confirmed_slot_starts`를 호출). 챗봇 예약검색 툴(E7)도 이 service를 경유(SQL 직접 접근 금지).
- **네이밍(architecture.md L233-251):** 테이블 복수 snake_case(`reservations`·`reservation_slots`) · FK `{단수}_id` · 와이어 전 구간 snake_case · 시각 `*_at` UTC `timestamptz`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.1] — AC 3종(스키마+UNIQUE, 원자·멱등 전이, 동일 트랜잭션 점유/재활성). Epic 4 전체(4.2~4.9) 의존 맥락.
- [Source: _bmad-output/planning-artifacts/architecture.md#Data Architecture L141-158] — UNIQUE(room_id, slot_start)·단일 트랜잭션 multi-row INSERT·상태 전이 원자/멱등·슬롯 재활성 동일 트랜잭션·확정 예약 slot_start 보유(영업시간 독립).
- [Source: architecture.md#Data Boundaries L363-367] — 슬롯=도출/점유=행·UNIQUE=진실의 원천. [#Component Boundaries L354-355] 도메인 service 경계.
- [Source: architecture.md#Naming/Format/Enforcement L233-301] — snake_case·`uq_{table}_{cols}`·표준 에러코드 상수·동일 트랜잭션 재활성·금지 안티패턴.
- [Source: apps/api/app/rooms/models.py] — CHECK·복합 UNIQUE·StrEnum·FK ondelete·복합 제약 명시 단축명·ck 이중접두 함정 선례.
- [Source: apps/api/app/rooms/service.py:67-145 derive_slots / L148-222 aggregate_availability] — `reserved_starts` seam(L83·L172·L208-214 "Story 4.9 예약 차감 연결 지점")·slot_start aware UTC 계약.
- [Source: apps/api/app/favorites/models.py + alembic/versions/181925e12bb8] — 최근 신규 도메인 테이블·마이그레이션 패턴.
- [Source: apps/api/app/core/errors.py:36,40] — `SLOT_CONFLICT`(409)·`CANCEL_WINDOW_PASSED`(409, 4.7) 기정의. [core/db.py:66-81 violated_constraint] 선별 변환. [core/time.py] UTC/aware 규약.
- [Source: apps/api/tests/rooms/test_models.py + tests/integration/test_rooms_migration.py] — 미러할 테스트 골격(≤63 가드·라이브 DB 왕복·`TEST_DATABASE_URL` skip).
- [Source: deferred-work.md L71] — 1.4 "63자 한계, 트리거=4.1" 회수 대상. [메모 [[dev-workflow-policy-live-db-migration]]] 라이브 DB 적용 의무. [[dev-workflow-policy-deferred-and-repeat-mistakes]] 반복함정·의무회수.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (dev-story 워크플로우, 2026-06-16)

### Debug Log References

- `uv run alembic heads` / `alembic current` — 라이브 head = `181925e12bb8`(favorites) 확인 후 체이닝.
- `uv run alembic revision --autogenerate -m "create reservations tables"` → `d8afe1726e81` 생성.
- `uv run alembic upgrade 181925e12bb8:d8afe1726e81 --sql` — 오프라인 산출명 = 모델 메타 정확 일치(drift 0):
  `ck_reservations_status`(이중접두 아님)·`uq_reservation_slots_room_slot`·`...ON DELETE CASCADE`.
- **라이브 DB 적용(정책 의무):** `uv run alembic upgrade head`(181925e12bb8→d8afe1726e81) 실제 실행 +
  왕복 무결성 `downgrade -1`(→181925e12bb8) / `upgrade head`(→d8afe1726e81) 확인.
- 게이트: `uv run pytest -q` 326 passed / 5 skipped(통합 1건 신규 skip 포함) · `uv run ruff check .` 통과 ·
  `uv run mypy` 32 files clean.

### Completion Notes List

- **Task 1 — ORM 모델 2종(AC1·AC4):** `Reservation`(상태머신·히스토리, 1행/예약) + `ReservationSlot`
  (점유 행, N행/예약) 2-테이블. `ReservationStatus(StrEnum)` + `_TERMINAL_STATUSES` 상태머신 단일 출처.
  CHECK 명시 단축명 `ck_reservations_status`(접미사만 — 2.1 이중접두 함정 회피), 복합 UNIQUE
  `uq_reservation_slots_room_slot`. FK ondelete: users/rooms=RESTRICT, `reservation_id`=CASCADE.
  재활성=DELETE 설계 근거를 docstring에 고정(FULL UNIQUE로 충분, 부분 인덱스 불요).
- **Task 2 — 마이그레이션(AC1·AC3):** autogenerate → 한국어 docstring 보강(down_revision·라이브 적용 명시·
  deferred L71 회수 명기). 오프라인 `--sql` 산출명 = 모델 메타 정확 일치(drift 0). 라이브 Supabase 적용 +
  왕복 무결성 확인 완료.
- **Task 3 — 서비스 프리미티브(AC2·AC3):** `create_reservation`(입력 fail-fast + 단일 트랜잭션 다중행
  INSERT all-or-nothing + `violated_constraint` 선별 변환 SLOT_CONFLICT, 무관 위반 re-raise) ·
  `cancel_reservation`/`reject_reservation`(종료 상태 멱등 no-op + 동일 트랜잭션 `_release_slots` 재활성) ·
  `confirmed_slot_starts`(4.9 차감 seam, 읽기 전용). 도메인 경계 준수(rooms 미import).
- **Task 4 — 메타데이터 회귀 테스트(AC4):** ≤63자 · 복합 단축명 존재 + 이중접두 부재 · PK/FK/INDEX 자동명
  (가장 긴 FK 48자 ≤63) 3종. DB 불필요.
- **Task 5 — 상태머신 단위 테스트(AC2):** 종료 상태 멱등 no-op(쓰기 0) · confirmed→종료 단일 commit ·
  `create_reservation` 빈/naive 입력 fail-fast · aware 통과 검증. FakeSession(쓰기 호출만 기록).
- **Task 6 — 통합 테스트(AC1·AC2·AC3):** `TEST_DATABASE_URL` 가드(기본 skip). UNIQUE 왕복(중복→
  SLOT_CONFLICT·부분 점유 0) · all-or-nothing(다중 슬롯 중 하나 충돌→전체 0) · 재활성 왕복(취소→슬롯
  DELETE·status 잔존→재점유 성공) · `confirmed_slot_starts` seam · CHECK 위반 6종. `finally downgrade base`.
- **의무 회수:** deferred-work.md L71(1.4 — "63자 한계, 트리거=4.1 복합 UNIQUE") **회수 완료** 표기.
- **범위 경계 준수:** 라우터/엔드포인트/schemas/OpenAPI·SDK 재생성/예약 UI 미생성(4.5~4.9 소유). 신규
  ErrorCode 0(`SLOT_CONFLICT` 1.5 기정의 재사용).

### File List

**신규:**
- `apps/api/app/reservations/models.py` — `Reservation`·`ReservationSlot`·`ReservationStatus`·`_TERMINAL_STATUSES`
- `apps/api/app/reservations/service.py` — `create_reservation`·`cancel_reservation`·`reject_reservation`·`_release_slots`·`confirmed_slot_starts`
- `apps/api/alembic/versions/d8afe1726e81_create_reservations_tables.py` — 2테이블 마이그레이션
- `apps/api/tests/reservations/__init__.py`
- `apps/api/tests/reservations/test_models.py` — 메타데이터 회귀(AC4)
- `apps/api/tests/reservations/test_service.py` — 상태머신·입력계약 단위(AC2)
- `apps/api/tests/integration/test_reservations_migration.py` — 라이브 DB 왕복(AC1·2·3, skip 가드)

**수정:**
- `apps/api/alembic/env.py` — 모델 import 허브에 `app.reservations.models` 등록(autogenerate 인식)

## Change Log

- 2026-06-16: Story 4.1 구현 완료(reservations 2-테이블 모델 + 마이그레이션 + 서비스 프리미티브 +
  메타/단위/통합 테스트). 라이브 Supabase 마이그레이션 적용 + 왕복 무결성 확인. deferred L71(63자 한계) 회수.
  게이트 그린(pytest 326 passed/5 skipped·ruff·mypy). Status: ready-for-dev → in-progress → review.

## Review Findings

> 2026-06-16 code-review(3레이어 적대적 리뷰 — Blind Hunter·Edge Case Hunter·Acceptance Auditor).
> raw 32건 → 병합 28건 → decision 1·patch 1·defer 5·dismiss 21. AC1~AC4·범위 경계·도메인 경계·
> 의무 회수(deferred L71) 모두 충족 확인(Acceptance Auditor 차단성 위반 0건).

### Patch

- [x] [Review][Patch] create_reservation slot_starts 진입부 materialize — `slot_starts`가 일회성 이터러블(제너레이터)이면 입력 계약 검사 루프(`for slot_start in slot_starts: _require_aware`)가 소진시켜 이후 INSERT 루프가 빈 채로 돌아 **슬롯 0개짜리 confirmed 예약**이 조용히 commit된다. **적용:** 진입부 `slot_starts = tuple(slot_starts)` + 시그니처 `Collection`→`Iterable`(materialize 후 정직한 계약). 테스트 `test_create_reservation_materializes_iterable_slots` 추가. [apps/api/app/reservations/service.py:97]
- [x] [Review][Patch] 동일 호출 내 중복 slot_start → ValueError fail-fast (D1 결정 2026-06-16: KTH 확정 (b)) — `create_reservation(slot_starts=[slot_a, slot_a])` 시 자기충돌이 `SLOT_CONFLICT(409 "이미 예약됨")`로 오변환되던 것을, 진입부에서 `len(set(...)) != len(...)`로 중복을 감지해 `ValueError`로 즉시 거부한다(빈 입력·naive datetime fail-fast와 동일 패턴). `SLOT_CONFLICT`(=타 예약 충돌)와 "내 입력이 중복"을 의미상 분리. 테스트 `test_create_reservation_rejects_duplicate_slots` 추가. [apps/api/app/reservations/service.py:97-113]

### Deferred

- [x] [Review][Defer] denormalized `reservation_slots.room_id` ↔ 부모 `reservations.room_id` 정합성 DB 미강제 [apps/api/app/reservations/models.py:156-163] — deferred, pre-existing. service가 단일 writer라 현재 무해. service 우회 writer 도입 시 복합 FK(`reservations(id, room_id)` 참조) 하드닝.
- [x] [Review][Defer] 동시 cancel/reject 낙관적 락 부재(read-then-flip race) [apps/api/app/reservations/service.py:144-161] — deferred, pre-existing. 둘째 commit은 무해 no-op(데이터 손상 없음). 진정한 멀티스레드 동시성·`SELECT FOR UPDATE`/버전 컬럼은 Story 4.6(동시성) 소유.
- [x] [Review][Defer] `confirmed_slot_starts` on_or_after 경계(`>=`)·윈도잉(상한) 테스트 부재 [apps/api/app/reservations/service.py:178-204] — deferred, pre-existing. zero-occupancy는 통합 테스트가 커버(line 148). on_or_after off-by-one 경계 테스트 + 상한 윈도잉은 실제 차감 배선 시점인 Story 4.9 소유.
- [x] [Review][Defer] reservation 행 하드삭제 시 `ondelete=CASCADE` 회귀 테스트 부재 [apps/api/tests/integration/test_reservations_migration.py] — deferred, pre-existing. 현 앱은 예약을 하드삭제하지 않음(취소=status flip). CASCADE 회귀 테스트는 하드삭제 경로(E8 계정 비활성 캐스케이드) 도입 시 회수.
- [x] [Review][Defer] 예약 단위 멱등성 키 부재(네트워크 재시도 시 중복 `Reservation` 생성 가능) [apps/api/app/reservations/service.py:71-127] — deferred, pre-existing. UNIQUE는 슬롯 겹침만 막고 예약 단위 중복은 막지 않음. idempotency-key는 쓰기 엔드포인트 책임 → Story 4.5(즉시예약) 소유.
