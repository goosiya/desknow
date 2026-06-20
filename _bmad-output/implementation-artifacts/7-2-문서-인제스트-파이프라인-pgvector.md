---
baseline_commit: NO_VCS
---

# Story 7.2: 문서 인제스트 파이프라인 → pgvector

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 개발자,
I want `docs_corpus/` 디렉터리의 문서를 OpenAI `text-embedding-3-small`로 임베딩해 **멱등하게** pgvector(HNSW)에 적재하는 코어 파이프라인을 두길,
so that 후속 문서 RAG(7.5)가 근거 문서를 유사도 검색할 수 있고, 재인제스트해도 중복 벡터가 생기지 않으며 부분 실패 문서가 식별된다 (FR-26 인프라).

## Acceptance Criteria

1. **(AC1 — 인제스트 → pgvector 적재)** `apps/api/app/chatbot/` 아래에 문서 청크 ORM 모델(벡터 컬럼 보유)과 인제스트 파이프라인이 존재한다. `docs_corpus/` 디렉터리의 텍스트 문서를 읽어 청크로 분할하고, **OpenAI `text-embedding-3-small`(단일 고정, `settings.EMBEDDING_MODEL`)** 로 임베딩해 pgvector 컬럼(`vector(1536)`)에 적재한다. 임베딩 컬럼에는 **HNSW 인덱스(`vector_cosine_ops`)** 가 생성된다(프로덕션 검색 경로=코사인 — 스파이크 `seed.sql` 선례와 동일 연산자 클래스). 스키마 변경은 **Alembic 마이그레이션이 단독 소유**한다(`SQLModel.metadata.create_all` 금지 — 1.4 규약).

2. **(AC2 — 멱등 재인제스트)** 동일 문서를 다시 인제스트하면 **중복 벡터를 생성하지 않는다**. 멱등 기준: 문서의 **내용 해시(sha256)** 가 이전 적재분과 같으면 **재임베딩·재적재를 스킵**(OpenAI 호출 0). 내용이 바뀌었으면 해당 문서의 기존 청크 행을 **모두 삭제 후 재적재**(stale 벡터 잔존 0). 멱등성은 `(source_path, chunk_index)` 복합 UNIQUE로 스키마에서도 강제한다.

3. **(AC3 — 부분 실패 식별)** 한 문서의 처리(읽기/청크/임베딩/적재) 실패가 **배치 전체를 중단시키지 않는다**. 각 문서는 독립적으로 처리되고 **문서 단위로 원자 적재**(한 문서의 청크는 단일 트랜잭션 — 절반만 적재되는 일 없음)된다. 파이프라인은 **인제스트 리포트**(성공/스킵/실패 문서 목록 + 실패 문서별 사유)를 반환하며, **어떤 문서가 실패했는지 식별**된다.

4. **(AC4 — 실행 가능 진입점, 코어만)** 파이프라인을 **수동/개발 실행**할 수 있는 얇은 진입점(`python -m ...` 또는 `scripts/`)이 존재해 AC1~3을 실제로 구동할 수 있다. **관리 표면(트리거 UI·상태 조회 API)은 FR-33(Story 8.4)이 소유 — 본 스토리 범위 밖**(라우터·관리자 화면·API 엔드포인트를 만들지 않는다). 코어 파이프라인은 호출 가능한 함수로 제공해 8.4가 재사용한다.

5. **(AC5 — 게이트 그린 + 라이브 마이그레이션)** `cd apps/api && uv run ruff check . && uv run mypy && uv run pytest`가 모두 통과한다. 기본 단위 테스트는 **네트워크·실 DB 없이**(임베딩 페이크 + 인메모리/세션 페이크) 멱등·부분실패·청크·해시 로직을 실증한다. 실 OpenAI 임베딩·실 DB 적재는 **키/DB 부재 시 skip**(`@pytest.mark.integration`)된다. 신규 마이그레이션은 dev 완료 시 **라이브 Supabase에 `uv run alembic upgrade head` 실제 실행**한다(메모 dev-workflow-policy-live-db-migration — 본 스토리는 테이블 추가라 **트리거됨**).

## Tasks / Subtasks

- [x] **Task 1 — 문서 청크 ORM 모델 (AC1, AC2)**
  - [x] `apps/api/app/chatbot/models.py` 신규: `DocumentChunk(SQLModel, table=True)` (`__tablename__ = "document_chunks"`). 컬럼: `id`(PK uuid), `source_path`(text — `docs_corpus/` 기준 상대 경로), `content_hash`(text — 문서 파일 전체 sha256, 문서 단위 멱등 기준), `chunk_index`(int — 문서 내 순서), `content`(text — 청크 원문), `embedding`(`pgvector.sqlalchemy.Vector(1536)`), `created_at`(UTC `timestamptz`, `core/time.now_utc` 단일 출처).
  - [x] 임베딩 차원은 모듈 상수 `EMBEDDING_DIM = 1536`(text-embedding-3-small 고정)로 둔다. **하드코딩 금지 금지가 아님** — 차원은 모델 교체 시 전체 재임베딩이라 고정 상수가 맞다(architecture L132). 주석으로 "모델 교체=전체 재임베딩+차원 변경 마이그레이션" 명시.
  - [x] 복합 UNIQUE `(source_path, chunk_index)` → 명시 단축명 `uq_document_chunks_source_path_chunk_index`(회고 P1, 42자 ≤63 ✓ — notifications 선례). 단일 제약(PK)·`source_path` 조회 인덱스는 1.4 `NAMING_CONVENTION` 자동(`idx_document_chunks_source_path`는 `index=True`로). HNSW는 모델이 아니라 **마이그레이션에서 수동 생성**(Task 2 — autogenerate가 opclass HNSW를 못 만든다).
  - [x] (선택) `CheckConstraint("chunk_index >= 0")` 추가 시 — ⚠️ **이중접두 함정**: `name`엔 **접미사만**(예 `name="chunk_index_non_negative"`) 주고 마이그레이션에서 `op.f(...)`로 감싼다(메모 migration-check-constraint-opf-trap·notifications `ck_notifications_type` 선례). 안 쓰면 생략 가능. → **미사용**: chunk_index는 enumerate(0..)로만 생성돼 음수가 구조적으로 불가능 → CHECK 생략(불필요한 제약 회피).
- [x] **Task 2 — Alembic 마이그레이션 (AC1, AC5)**
  - [x] `app/chatbot` 모델을 **alembic env.py 모델 import 허브**에 등록: `alembic/env.py` 블록에 `from app.chatbot import models as _chatbot_models  # noqa: F401` 추가. ⚠️ **추가 발견**: import 허브에 notifications(5.1)·reviews/review_replies(5.5/5.6)가 **누락**돼 있어 autogenerate가 그 테이블을 삭제 대상으로 오감지(잠복 버그) → 누락 3종도 함께 등록 복구.
  - [x] `uv run alembic revision --autogenerate -m "create document_chunks table"`로 생성 후 **수기 보정**: (a) 파일 상단에 `import pgvector` 추가 — autogenerate가 렌더한 `pgvector.sqlalchemy.vector.VECTOR` 타입의 `NameError` 방지. (b) **HNSW 인덱스 수기 추가**: `op.create_index('idx_document_chunks_embedding_hnsw', 'document_chunks', ['embedding'], postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})`, `downgrade`에 drop 대칭. (c) CHECK 미사용이라 `op.f()` 래핑 무관.
  - [x] `down_revision` = 실제 현재 head `c9d3e5b7f1a4`(review_replies, 5.6). ⚠️ 스토리 명시 `a7c9e1b3d5f2`는 create-story 시점(5.5/5.6 dev 이전) 값이라 outdated → 실제 head로 보정. baseline(`124a50c37b8c`)이 `CREATE EXTENSION vector`를 소유하므로 본 마이그레이션은 확장을 다시 만들지 않는다.
  - [x] ⚠️ **라이브 적용 의무**: 라이브 Supabase에 `uv run alembic upgrade head` **실제 실행 완료**(메모 dev-workflow-policy-live-db-migration) — `document_chunks` 테이블·HNSW 코사인 인덱스·복합 UNIQUE·source_path 인덱스 생성 확인.
- [x] **Task 3 — 청킹 + 해시 (AC1, AC2)**
  - [x] `app/chatbot/ingest/` 패키지 신규. **자체 결정적 청커**(`chunking.chunk_text` — 문자 길이 기반 + overlap, 표준 라이브러리만). `langchain-text-splitters`는 미설치라 **도입하지 않음**(MVP 텍스트엔 단순 청커로 충분 — 신규 의존성 0).
  - [x] 문서 로딩(`chunking.load_document_text`/`iter_corpus_files`): `docs_corpus/` 하위 `.md`/`.txt` 재귀 스캔(정렬=결정적). 바이너리 파서는 범위 밖. 빈 파일·디코드 실패는 `DocumentLoadError`로 부분 실패 처리(AC3).
  - [x] `compute_content_hash` = 파일 전체 내용의 sha256 hexdigest(문서 단위 멱등 기준). `hashlib` 표준 라이브러리(신규 의존성 0).
- [x] **Task 4 — 임베딩 클라이언트 (AC1, AC5)**
  - [x] `langchain_openai.OpenAIEmbeddings`(이미 설치 — 신규 의존성 0) 사용. `build_embedder()`가 `model=settings.EMBEDDING_MODEL`·`openai_api_key=settings.OPENAI_API_KEY`를 **명시 전달**(7.1 footgun 일관성). 파이프라인은 `Embedder` Protocol에만 의존(테스트 페이크 주입). 배치 임베딩 `embed_documents(list[str])`.
  - [x] 임베딩은 **7.1 멀티 LLM 어댑터를 거치지 않는다**(Dev Notes §경계) — `chatbot/llm/`(채팅)과 별개 경로(`chatbot/ingest/embedding.py`).
  - [x] 임베딩 실패(OpenAI 예외)는 **문서 단위 부분 실패**로 흡수(AC3) — 파이프라인 try/except가 사유를 리포트 `failed`에 기록. 새 공개 `ErrorCode` 추가 **없음**(OpenAPI/SDK 재생성 불필요).
- [x] **Task 5 — 인제스트 파이프라인 + 리포트 (AC2, AC3, AC4)**
  - [x] `app/chatbot/ingest/service.py`: `ingest_corpus(store, corpus_dir, embeddings, ...) -> IngestReport`. ⚠️ **설계 개선**: 첫 인자를 raw `session` 대신 `DocumentChunkStore`(store.py)로 — pgvector 미지원 SQLite 없이 페이크 store로 멱등/부분실패 단위 검증 가능(Dev Notes §함정 #6). 흐름: 스캔 → 문서별 [해시 계산 → 기존 해시 대조 → 동일=skip(임베딩 0) / 변경·신규=청크→임베딩→DELETE 후 INSERT].
  - [x] `IngestReport`(dataclass): `succeeded`/`skipped`/`failed: list[tuple[str,str]]`(경로,사유) + `total`. 부분 실패 식별 = `failed`(AC3).
  - [x] **문서 단위 원자성**: `SqlDocumentChunkStore.replace_document_chunks`의 DELETE+INSERT가 단일 트랜잭션(commit/rollback). 문서별 try/except 격리 — 한 문서 실패가 이미 커밋된 문서를 롤백하지 않음. 멱등 DELETE→INSERT가 UNIQUE 위반 없이 동작(stale 0).
  - [x] `apps/api/scripts/ingest_docs.py`(export_openapi.py 스타일): `get_engine`·`Session`·`build_embedder`를 배선해 `ingest_corpus` 호출, 리포트를 사람이 읽게 출력(실패 시 exit 1). **라우터 아님**(AC4 — 8.4가 API/UI 소유). cp949 콘솔 보호 위해 `_ensure_utf8_streams` 재사용.
  - [x] `apps/api/docs_corpus/` 신규(architecture L341): `README.md` + `sample-service-guide.txt`(수동 실행/점검 샘플). 실 운영 문서는 8.4/배포 시점.
- [x] **Task 6 — 테스트 (AC2, AC3, AC5)**
  - [x] `apps/api/tests/chatbot/test_ingest.py` 신규 — **네트워크·실 DB 없이**(페이크 Embedder + 인메모리 FakeStore): 청커 결정성·overlap·경계, `content_hash` 안정성, **멱등(AC2)**(2회차 임베딩 호출 0·행 증가 0; 내용 변경 시 stale 0 교체), **부분 실패(AC3)**(임베딩 예외·디코드 실패 격리·사유 기록), 빈 코퍼스, 청크 메타데이터.
  - [x] `apps/api/tests/chatbot/test_models.py` 신규(notifications 미러): 테이블명·복합 UNIQUE명·PK/인덱스명·벡터 컬럼 차원(1536)·63자 가드 단언.
  - [x] (선택) `tests/chatbot/test_ingest_integration.py` — `TEST_DATABASE_URL`+`OPENAI_API_KEY` 게이트(skipif, test_migrations 패턴): 실 임베딩 적재→코사인 `<=>` 유사도 검색 1위 반환→재인제스트 멱등→정리. 미설정 시 skip. **추가로 라이브 수동 실행**(`scripts/ingest_docs.py`)으로 실 DB 적재·멱등 스킵을 실증.
  - [x] 신규 마이그레이션 `downgrade`는 HNSW drop 포함 대칭 작성. ⚠️ `test_migrations.py` 왕복은 `downgrade base`로 DB를 비우므로 **throwaway `TEST_DATABASE_URL` 전용**(라이브 Supabase에 절대 실행 금지) — 라이브 dev DB 보호 위해 본 환경에선 미실행, 대칭 downgrade 코드로 보증.

## Dev Notes

### 이 스토리의 본질 — 무엇을 만들고 무엇을 만들지 않는가

7.2는 **문서 RAG의 데이터 계층 인프라**다. "문서를 벡터로 멱등 적재"하는 **코어 파이프라인**이 목표이지, RAG 검색·답변 생성이나 관리 UI를 만드는 게 아니다.

| 관심사 | 7.2 책임 | 소유 스토리 |
|---|---|---|
| 문서 청크 모델 + pgvector 적재 | ✅ 본 스토리 | — |
| 멱등 재인제스트 + 부분 실패 식별 | ✅ 본 스토리 | — |
| 수동/개발 실행 진입점(CLI) | ✅ 얇게 | — |
| **유사도 검색·RAG 답변(3분기)** | ❌ 검색 쿼리/툴 안 만듦 | **7.5(문서 RAG)** |
| **문서검색 LangChain 툴** | ❌ | **7.5** (7.1의 자리표시 도구 대체) |
| **관리자 트리거·상태조회 UI/API** | ❌ 라우터·화면 0 | **8.4(FR-33)** |
| **chat model 어댑터** | ❌ 임베딩≠chat | **7.1(완료)** |

**IN(본 스토리):** `chatbot/models.py`(DocumentChunk + 벡터 컬럼), `chatbot/ingest/` 파이프라인(로딩·청킹·해시·임베딩·멱등 upsert·부분실패 리포트), Alembic 마이그레이션(테이블+HNSW), 얇은 실행 진입점, `docs_corpus/` 디렉터리, 네트워크리스 단위 테스트.
**OUT(만들지 말 것 — 반복함정 #reinvent/#scope):** 유사도 검색 쿼리·RAG 리트리버·문서검색 툴(7.5), 관리자 인제스트 API/화면(8.4), chat model 경로(7.1), SSE(7.4), 골든셋(7.7), PDF/docx 바이너리 파서(MVP는 텍스트), 별도 벡터 DB·임베딩 어댑터 레이어(단일 고정 모델이라 불필요).

### ★설계 의도 — 바퀴 재발명 금지 (이미 있는 것 재사용)

1. **pgvector 확장은 이미 활성** — baseline 마이그레이션(`124a50c37b8c`)이 `CREATE EXTENSION vector`를 단독 소유한다. 다시 만들지 말 것. `verify_db_connection`(`core/db.py:83`)이 기동 시 확장 존재를 검증한다.
2. **벡터 SQLAlchemy 타입은 `pgvector.sqlalchemy.Vector`** — `pgvector>=0.4.2`가 이미 런타임 의존성(`pyproject.toml`). 직접 raw SQL로 vector 컬럼 DDL을 손코딩하지 말 것(모델은 `Vector(1536)`, DDL은 Alembic).
3. **임베딩 클라이언트는 `langchain_openai.OpenAIEmbeddings`** — `langchain-openai`가 이미 7.1에서 의존성으로 설치됨(**신규 의존성 0**). `openai` SDK를 직접 import해 임베딩 HTTP를 손코딩하지 말 것(7.1 어댑터 정신과 동일 — LangChain이 이미 통일).
4. **HNSW + 코사인은 스파이크가 검증한 경로** — `spikes/phase0/pgvector/seed.sql`이 `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)`, 차원 1536을 이미 증명. 프로덕션 검색(7.5)도 코사인이므로 **같은 연산자 클래스**를 쓴다.
5. **모델/마이그레이션 패턴은 notifications(5.1)가 최신 선례** — `app/notifications/models.py` + `a7c9e1b3d5f2_create_notifications_table.py`를 미러. 네이밍 규약 자동(1.4 `NAMING_CONVENTION`), 복합 제약 명시 단축명, `op.f()` 래핑, `core/time.now_utc`.

### ★알려진 함정 (구현 전 반드시 확인 — 프리플라이트)

1. **autogenerate가 pgvector `Vector` 타입을 렌더하며 import 누락 → `NameError`:** 마이그레이션 상단에 `import pgvector`(또는 `from pgvector.sqlalchemy import Vector`)를 `import sqlmodel`처럼 추가. autogenerate 결과를 그대로 믿지 말고 점검.
2. **autogenerate는 HNSW opclass 인덱스를 만들지 못한다:** 벡터 인덱스는 **수기 추가** 필수(`postgresql_using='hnsw'`, `postgresql_ops={'embedding': 'vector_cosine_ops'}`). 빠뜨리면 컬럼만 생기고 인덱스가 없어 검색(7.5)이 느려진다. `downgrade`에 drop 대칭.
3. **CHECK 제약 이중접두(메모 migration-check-constraint-opf-trap):** CHECK를 쓴다면 모델 `name`엔 접미사만, 마이그레이션에선 `op.f()`로 감싼다. `test_models`는 못 잡고 라이브에서 `ck_x_ck_x` 이중접두가 된다. (본 스토리는 CHECK가 선택 — 안 쓰면 무관.)
4. **alembic env.py 모델 import 허브 누락:** `app/chatbot/models`를 env.py L47-53 블록에 등록 안 하면 autogenerate가 테이블을 **인식조차 못 한다**(빈 마이그레이션 생성). 등록 필수.
5. **OpenAIEmbeddings api_key 명시 전달(7.1 footgun 일관성):** env 자동 픽업에 의존하지 말고 `settings.OPENAI_API_KEY`를 명시 전달(키 백엔드 격리 NFR-6). 모델명도 `settings.EMBEDDING_MODEL`(하드코딩 금지).
6. **SQLite로 벡터 테스트 불가:** SQLite 인메모리는 pgvector 타입을 모른다. 단위 테스트는 **페이크 세션**(DB 미접속, 멱등 결정 로직·해시·리포트 검증)으로, 실 DB 적재·유사도는 `@pytest.mark.integration` 키/`TEST_DATABASE_URL` 게이트로 분리.
7. **임베딩 차원 불변식:** 컬럼은 `vector(1536)` 고정. `EMBEDDING_MODEL`을 1536이 아닌 모델로 바꾸면 적재가 깨진다 → 모델 교체는 **전체 재임베딩 + 차원 변경 마이그레이션**(architecture L132 "교체 시 전체 재임베딩"). 주석으로 명시.

### ★멱등 전략 (AC2 — 핵심 설계)

- **멱등 단위 = 문서(파일)**. 각 문서의 전체 내용 sha256을 `content_hash`로 청크 행에 denormalize 저장.
- 재인제스트 시 문서별로: 기존 적재분의 `content_hash`(해당 `source_path`) 조회 →
  - **동일** → 임베딩·DB 쓰기 **모두 스킵**(OpenAI 비용 0, skipped 리포트).
  - **다름/신규** → 단일 트랜잭션에서 `DELETE WHERE source_path=?` 후 새 청크 INSERT(stale 벡터 0).
- `(source_path, chunk_index)` UNIQUE가 동시/중복 INSERT를 스키마에서도 막는다(멱등 이중 방어).
- **대안(과설계 주의):** `documents` 부모 테이블 + `document_chunks` 자식 2테이블 정규화도 가능하나, MVP는 단일 테이블 + denormalized `content_hash`로 충분(부분실패 식별·멱등 모두 만족). 2테이블은 후속 필요 시.

### ★부분 실패 (AC3 — 핵심 설계)

- 문서 루프는 try/except로 문서별 격리. 실패해도 `continue`하고 `report.failed.append((path, reason))`.
- 문서 단위 트랜잭션 경계 → 한 문서의 임베딩/쓰기 실패가 **이미 커밋된 다른 문서를 롤백하지 않는다**.
- 리포트가 **어떤 문서가 왜 실패했는지** 식별(AC3 문자 그대로 충족). 8.4가 이 리포트를 관리 화면에 노출(상태 확인)할 때 재사용한다.

### ★청킹 (의존성 결정)

- **권장: 자체 결정적 청커**(문자 길이 기반 + overlap, 표준 라이브러리만 — 신규 의존성 0·테스트 결정적). MVP 텍스트 문서엔 충분.
- 대안: `langchain-text-splitters`(`RecursiveCharacterTextSplitter`) — **현재 미설치**라 쓰려면 `pyproject.toml`에 명시 추가(`uv add`)해야 한다. 더 정교한 분할이 필요할 때만 채택. 본 스토리에선 자체 청커로 충분하므로 의존성 추가를 권장하지 않는다(범위 최소).

### 기존 코드·패턴 정렬 (반드시 따를 것)

- **도메인 모듈 구조**(architecture L255, L338): `app/chatbot/`. 모델은 `app/chatbot/models.py`(타 도메인 `{domain}/models.py` 일관), 파이프라인은 `app/chatbot/ingest/`. 7.1이 만든 `chatbot/llm/`(chat 어댑터)와 형제 — 임베딩/인제스트는 별 경로.
- **설정 로딩:** `get_settings()`(`core/config.py`) 싱글톤만. `EMBEDDING_MODEL`(이미 선언·기본 `text-embedding-3-small`)·`OPENAI_API_KEY`(필수) 사용. 직접 `os.environ` 금지. **본 스토리는 신규 설정 필드 불필요**(EMBEDDING_MODEL·OPENAI_API_KEY 이미 존재 → `_assert_key_lists_match_model` 가드 무관).
- **DB 세션:** `get_session`(`core/db.py`) 의존성/`Session(get_engine())`. 동기 엔진(psycopg3). `create_all` 금지(스키마=Alembic 단독).
- **시간:** `core/time.now_utc`로 `created_at`(UTC `timestamptz`). `datetime.now()` 직접 금지.
- **네이밍:** 1.4 `NAMING_CONVENTION`(`idx_`/`uq_`/`ck_`/`fk_`/`pk_`) 자동 + 복합 제약 명시 단축명(회고 P1, 63바이트 절단 방지).
- **마이그레이션:** notifications(`a7c9e1b3d5f2`) 미러 — `import sqlmodel`/`import pgvector` 헤더, `op.f()` 래핑, head 체인 정확히.
- **타입/린트:** ruff(E,F,I,B,UP, line-length 100) + mypy(strict, pydantic plugin). `from __future__ import annotations`. 모든 함수 타입.
- **테스트 미러:** `tests/chatbot/test_*.py`. 네트워크/실키/실DB 없이 페이크로 단위 검증. 실연동은 `@pytest.mark.integration` 키/`TEST_DATABASE_URL` 게이트(`tests/integration/test_migrations.py` 선례).
- **주석 한국어**, 변수·함수명 영어(전역 규약).

### ★OpenAPI/SDK 재생성 — 본 스토리 불필요 (단 조건부 주의)

- 7.2는 **라우터를 노출하지 않는다**(인제스트=CLI/내부 함수, API=8.4). `app/main.py` 변경 0 → OpenAPI 계약 불변 → **SDK 재생성 불필요**.
- ⚠️ **단, 새 공개 `ErrorCode`를 추가하면 재생성 트리거됨:** 7.1 교훈 — `ErrorCode` enum은 `ErrorDetail.code`로 노출되는 **공개 스키마 컴포넌트**라, 추가 시 Layer A 드리프트 게이트(`tests/test_openapi_export.py`)가 잡고 `scripts/export_openapi.py` + SDK 재생성이 필요하다. **권장: 본 스토리는 새 공개 ErrorCode를 추가하지 않는다** — 임베딩/적재 실패는 인제스트 리포트의 내부 사유 문자열로만 다루고(API 미노출), 공개 에러 표면은 8.4(관리 API)가 필요 시 결정. 부득이 추가하면 재생성 의무 인지.

### 정책·범위 메모 (혼동 방지)

- **라이브 DB 마이그레이션 — 본 스토리 해당(트리거됨):** 7.2는 `document_chunks` 테이블을 **추가**한다 → 매 스토리 dev 완료 시 라이브 Supabase에 `uv run alembic upgrade head` **실제 실행** 의무가 발생(메모 dev-workflow-policy-live-db-migration). 배포 시 dump→Railway. (7.1은 무상태라 미해당이었으나 7.2는 해당 — 빠뜨리지 말 것.)
- **웹–모바일 짝 점검 — 본 스토리 미해당:** 7.2는 순수 백엔드 파이프라인으로 UI 표면 0. 인제스트 관리 화면은 8.4(관리자 웹 전용 — 모바일 짝 없음). `apps/web`·`apps/mobile`·`apps/admin` 변경 0(메모 web-is-booker-only-provider-api-only·E7≠모바일 버킷).
- **deferred-work 의무 회수 — 본 스토리 트리거 아님(단 인지):** deferred-work.md L126-128 "pgvector 데이터 충실도 검증(행수·체크섬·NN 단언)"의 트리거는 **소스 pgvector→Railway로 실 임베딩을 처음 1회 이관하는 시점**(=배포 준비). 7.2는 인제스트 *파이프라인*을 만들 뿐 **실 이관(dump/restore)을 수행하지 않으므로** 이 회수 트리거가 아니다. 단 7.2의 적재가 그 이관의 *데이터 원천*이 되므로, 배포 시 `verify.sql` 강화(행수 자동대조·정답 NN) 회수가 후행함을 인지. L120 "Phase 0 ③ 실 이관 미실행"도 동일하게 배포 트리거.
- **신규 설정 필드 없음:** `EMBEDDING_MODEL`(text-embedding-3-small)·`OPENAI_API_KEY`가 이미 config에 있어 추가 등록 불필요(config 가드 무관). 임베딩 차원만 코드 상수.

### Project Structure Notes

- **신규(app):** `app/chatbot/models.py`(DocumentChunk), `app/chatbot/ingest/__init__.py`, `app/chatbot/ingest/service.py`(또는 `pipeline.py` — `ingest_corpus`+`IngestReport`), `app/chatbot/ingest/chunking.py`(결정적 청커, 선택 분리), `app/chatbot/ingest/__main__.py`(또는 `apps/api/scripts/ingest_docs.py` — 얇은 실행 진입점).
- **신규(migration):** `apps/api/alembic/versions/<rev>_create_document_chunks_table.py`(테이블 + HNSW 수기).
- **신규(corpus):** `apps/api/docs_corpus/`(+`.gitkeep` 또는 샘플 텍스트). architecture L341 위치.
- **신규(tests):** `apps/api/tests/chatbot/test_ingest.py`, (모델 등록) `tests/chatbot/test_models.py`. `tests/chatbot/__init__.py`는 7.1이 이미 생성.
- **수정:** `apps/api/alembic/env.py`(모델 import 허브에 `app.chatbot.models` 등록 — L47-53 블록). 마이그레이션 head 체인.
- **변경 0:** `app/main.py`(라우터 없음), OpenAPI/SDK(라우터·공개 ErrorCode 미추가 시), 프론트 3면, `pyproject.toml`(자체 청커 채택 시 — langchain-text-splitters 미추가). config.py(신규 필드 없음).
- **회귀 위험:** 낮음. 신규 테이블은 기존 도메인과 FK 무관(독립). 마이그레이션 head 체인만 정확히. 단위 테스트는 네트워크/실DB 없이 통과해야 정상.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 7.2 (L1060-1076)] — AC 원문(docs_corpus→text-embedding-3-small→pgvector HNSW 적재·멱등·부분실패 식별·관리표면=FR-33/E8).
- [Source: _bmad-output/planning-artifacts/epics.md#FR-26 (L75), #FR-33 (L84)] — 문서 RAG 인프라·인제스트 멱등(중복 벡터 미생성)·부분 실패 식별·UI 업로드 아님(디렉터리 배치).
- [Source: _bmad-output/planning-artifacts/architecture.md#L128-132, L143, L202] — 임베딩 OpenAI text-embedding-3-small 단일 고정(교체=전체 재임베딩), PostgreSQL+pgvector(HNSW), 디렉터리 배치 멱등 인제스트·부분 실패 식별.
- [Source: _bmad-output/planning-artifacts/architecture.md#L338, L341, L364, L396] — chatbot 도메인(langgraph/llm/tools/**ingest**/sse), `docs_corpus/` 디렉터리, 단일 PostgreSQL 벡터+예약 공존, 문서검색=pgvector(검색 경로는 7.5).
- [Source: apps/api/app/notifications/models.py + alembic/versions/a7c9e1b3d5f2_*.py] — 모델+마이그레이션 최신 선례(네이밍 규약 자동·복합 제약 명시 단축명·`op.f()`·`core/time.now_utc`·`import sqlmodel`).
- [Source: apps/api/app/core/db.py (L83-111)] — `verify_db_connection`이 pgvector 확장 존재 검증, baseline이 확장 소유, `create_all` 금지(스키마=Alembic).
- [Source: apps/api/alembic/versions/124a50c37b8c_baseline_enable_pgvector_extension.py] — `CREATE EXTENSION vector` 단독 소유(본 스토리 재실행 금지).
- [Source: apps/api/alembic/env.py (L47-53)] — 모델 import 허브(신규 도메인 모델 등록 위치).
- [Source: apps/api/app/core/config.py (L24, L34, L42, L82, L91)] — EMBEDDING_MODEL(text-embedding-3-small 기본)·OPENAI_API_KEY(필수) 이미 선언(신규 필드 불필요).
- [Source: spikes/phase0/pgvector/seed.sql, RUNBOOK.md] — 검증된 벡터 패턴: `vector(1536)`, `CREATE INDEX USING hnsw (embedding vector_cosine_ops)`, 확장 선설치 교훈.
- [Source: apps/api/tests/integration/test_migrations.py, tests/notifications/test_models.py] — `TEST_DATABASE_URL` 게이트 통합 테스트·모델 등록 단위 테스트 선례.
- [Source: _bmad-output/implementation-artifacts/7-1-멀티-llm-어댑터-레이어.md] — 임베딩≠chat 경로 경계, api_key 명시 전달 footgun, OpenAPI/SDK 재생성=공개 ErrorCode 추가 시만.
- [Source: _bmad-output/implementation-artifacts/deferred-work.md (L120, L126-128)] — pgvector 실 이관·데이터 충실도 검증은 배포 시점 트리거(7.2 적재가 원천이나 이관 수행은 아님).
- [메모: dev-workflow-policy-live-db-migration] — 테이블 추가 → dev 완료 시 라이브 `alembic upgrade head` 실행 의무.
- [메모: migration-check-constraint-opf-trap] — CHECK 사용 시 `op.f()` 래핑(이중접두 방지, test_models 미포착).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Claude Opus 4.8, 1M context) — bmad-dev-story 워크플로우.

### Debug Log References

- **autogenerate 오염(잠복 버그 발견·수정):** 1차 autogenerate가 `notifications`·`reviews`·`review_replies`를 **삭제 대상**으로 감지. 원인 = `alembic/env.py` 모델 import 허브에 5.1/5.5/5.6 도메인 모델 누락(기존 잠복 버그). 누락 3종(notifications·reviews) 등록 복구 후 재생성 → `document_chunks`만 깨끗이 감지.
- **mypy 2건:** (1) `delete().where(col == x)`가 bool로 추론 → `sqlmodel.delete`+`col()` 사용(reservations 선례). (2) `OpenAIEmbeddings(api_key=...)` 거부 → 필드명 `openai_api_key=`로 전달(런타임 `populate_by_name`·mypy 둘 다 통과).
- **청커 테스트 계산 오류 1건:** 길이 2500/step 800 → 3청크인데 기대 4로 오기 → 수정.
- **cp949 콘솔 인코딩:** `scripts/ingest_docs.py`의 이모지·em-dash 출력이 Windows cp949에서 `UnicodeEncodeError`(파이프라인은 정상 실행, 출력만 실패) → `_ensure_utf8_streams`(config.py 선례) 재사용으로 해결.

### Completion Notes List

- **AC1(인제스트→pgvector 적재):** `DocumentChunk` 모델(`vector(1536)`) + Alembic 마이그레이션(`7a6edff2b9ef`)이 테이블·HNSW 코사인 인덱스를 생성. 라이브 Supabase 적용 완료, 실 OpenAI 임베딩으로 샘플 2문서 적재(1536차원·sha256 64자) 검증.
- **AC2(멱등 재인제스트):** 내용 해시(sha256) 동일 시 임베딩·DB 쓰기 모두 스킵(단위 테스트로 임베딩 호출 0 실증 + 라이브 재실행 2문서 SKIP 실증). 내용 변경 시 기존 청크 전량 DELETE 후 재적재(stale 0). `(source_path, chunk_index)` UNIQUE로 스키마 이중 방어.
- **AC3(부분 실패 식별):** 문서별 try/except 격리 + 문서 단위 트랜잭션. `IngestReport.failed=[(경로,사유)]`로 어떤 문서가 왜 실패했는지 식별. 임베딩 예외·디코드 실패 단위 테스트로 실증(다른 문서 정상·실패 문서 미적재).
- **AC4(실행 진입점, 코어만):** `scripts/ingest_docs.py`가 코어 함수 `ingest_corpus`를 배선·구동. 라우터·API·UI 0(8.4가 소유·재사용). `app/main.py` 무변경 → OpenAPI/SDK 재생성 불필요.
- **AC5(게이트 그린+라이브 마이그레이션):** `ruff check`·`mypy`(56파일)·`pytest`(611 passed, 13 skipped) 전부 통과. 단위 테스트는 네트워크·실 DB 없이(페이크 Embedder/Store) 동작. 실 연동은 `@integration`(skipif) 게이트. 신규 마이그레이션 라이브 `upgrade head` 실제 실행 완료.
- **설계 결정:** 파이프라인 첫 인자를 raw `session` 대신 `DocumentChunkStore`(Protocol)로 — SQLite가 pgvector를 모르는 제약(Dev Notes §함정 #6)을 페이크 store로 우회해 멱등/부분실패를 실 DB 없이 단위 검증.
- **범위 외 잠복 버그 수정:** `alembic/env.py` import 허브에 누락돼 있던 notifications·reviews·review_replies 모델을 함께 등록(향후 autogenerate 오삭제 방지).

### File List

**신규(app):**
- `apps/api/app/chatbot/models.py` — `DocumentChunk` + `EMBEDDING_DIM`
- `apps/api/app/chatbot/ingest/__init__.py` — 패키지 공개 표면
- `apps/api/app/chatbot/ingest/chunking.py` — 결정적 청커·해시·문서 로딩
- `apps/api/app/chatbot/ingest/embedding.py` — `Embedder` Protocol·`build_embedder`
- `apps/api/app/chatbot/ingest/store.py` — `DocumentChunkStore`·`SqlDocumentChunkStore`
- `apps/api/app/chatbot/ingest/service.py` — `ingest_corpus`·`IngestReport`

**신규(migration):**
- `apps/api/alembic/versions/7a6edff2b9ef_create_document_chunks_table.py`

**신규(corpus):**
- `apps/api/docs_corpus/README.md`
- `apps/api/docs_corpus/sample-service-guide.txt`

**신규(script):**
- `apps/api/scripts/ingest_docs.py`

**신규(tests):**
- `apps/api/tests/chatbot/test_ingest.py`
- `apps/api/tests/chatbot/test_models.py`
- `apps/api/tests/chatbot/test_ingest_integration.py`

**수정:**
- `apps/api/alembic/env.py` — 모델 import 허브에 chatbot·notifications·reviews 등록(누락 복구 포함)

### Change Log

| 날짜 | 변경 |
|---|---|
| 2026-06-17 | Story 7.2 create-story — 컨텍스트 엔진 분석 완료(에픽·아키텍처·7.1·기존 코드·스파이크·deferred 정책 교차분석). ready-for-dev. |
| 2026-06-17 | Story 7.2 dev-story 구현 완료 — DocumentChunk 모델+pgvector HNSW 마이그레이션(라이브 적용), 결정적 청커·sha256 멱등·부분실패 리포트 파이프라인, OpenAI 임베딩 클라이언트, 실행 진입점, 단위/통합 테스트. env.py import 허브 누락(notifications·reviews) 잠복 버그 동반 수정. 게이트 그린(ruff·mypy·pytest 611 passed). Status → review. |

## Review Findings

> code-review 2026-06-17 — 3-레이어 병렬 적대적 리뷰(Blind Hunter·Edge Case Hunter·Acceptance Auditor). Acceptance Auditor: AC1~AC5·Dev Notes 함정 전부 충족(머지 가능 수준), 스펙 이탈 0. 아래는 견고성/멱등 경계에 대한 잔여 발견.

### Decision Needed

- [x] [Review][Decision] **(해결: 방식 c로 patch 적용)** **단일 공유 Session에서 DB 레벨 오류 시 트랜잭션 abort 연쇄로 AC3 문서 격리가 좁게 깨질 수 있음** — `scripts/ingest_docs.py:67-69`가 단일 `Session`을 전체 코퍼스에 주입한다. `replace_document_chunks`(store.py:62-74)는 자체 `rollback()`으로 자가복구하나, 임베딩 단계 실패는 `replace`를 호출하지 않아 rollback이 일어나지 않고, 만약 `get_content_hash` SELECT(store.py:50-55)가 DB 레벨 오류로 트랜잭션을 aborted 상태로 남기면 후속 문서의 SELECT가 `InFailedSqlTransaction`으로 연쇄 실패 → AC3 "문서 단위 격리" 보장에 좁은 구멍. 단위 테스트는 `FakeStore`라 실 세션 상호작용을 검증하지 못함(사각지대). 수정 방향 트레이드오프: (a) 문서별 새 Session, (b) 문서별 savepoint(`session.begin_nested()`), (c) service except에서 `store.rollback()` 호출(Protocol 확장). MVP·CLI·통제된 corpus라 현 발생확률은 낮음. (blind+edge)

### Patch

- [x] [Review][Patch] **(적용됨)** **content_hash가 BOM/CRLF에 민감 — OS·에디터 경계에서 멱등(AC2) 조용히 무력화** [chunking.py:81-104] — `load_document_text`를 `utf-8-sig`(BOM 제거) + `\r\n`/`\r`→`\n` 정규화로 수정. 회귀 테스트 `test_reingest_is_stable_across_newline_and_bom`(BOM+CRLF 재인제스트 시 skip·재임베딩 0) 추가.
- [x] [Review][Patch] **(적용됨)** **빈/공백 청크 방어 가드 부재(현 경로 미발현·8.4 재사용 잠재 데이터 소실)** [service.py, store.py] — service에서 공백-only 청크 제거 + 유효 청크 0이면 skip(빈 replace 차단), `SqlDocumentChunkStore.replace_document_chunks`에 빈 시퀀스 no-op 가드(8.4 재사용 방어). 회귀 테스트 `test_whitespace_only_chunks_are_dropped` 추가.

### Deferred (pre-existing/scope — deferred-work.md 동기화됨)

- [x] [Review][Defer] **대용량 단일 문서 단일 배치 임베딩 → OpenAI 배치/토큰 한도 초과 시 문서 전체 적재 불가** [service.py:85] — deferred, MVP 통제 corpus라 현 위험 낮음(부분실패로 흡수되나 큰 문서는 영영 미적재).
- [x] [Review][Defer] **corpus에서 삭제/리네임된 문서의 stale 청크 GC 경로 부재(orphan 영구 잔존)** [service.py, store.py] — deferred, 7.2 범위 밖(코퍼스 동기화/GC ≠ 인제스트; 8.4 관리 표면 후보).
