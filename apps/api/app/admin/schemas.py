"""admin 응답 스키마: 운영 계정목록 (Story 8.1, AC4).

**규약(아키텍처 §Format L256-296):**

- **페이지네이션 포맷** = ``{ items, total, page, page_size }``(architecture.md L263 규약).
- **와이어 snake_case 유지**(L286, camelCase 변환 금지). ``created_at``은 ``UserPublic``과
  동일하게 UTC ISO-8601(``...Z``)로 직렬화한다(L263, ``isoformat_utc`` 단일 출처).
- **익명화 예외(중요):** provider/타인-facing 표면은 sha256 익명 라벨을 쓰지만(메모
  anonymous-booker-label-no-display-name), **admin은 운영자**(타인-facing 아님)이고 계정 관리
  (8.2 비활성 대상 식별)를 위해 **실 이메일·실 역할·실 활성여부**를 본다 — 익명화하지 않는다.
- **``password_hash`` 절대 비노출**(NFR-6). 스키마에 해당 필드를 두지 않는다.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_serializer

from app.core.time import isoformat_utc


class AdminAccountItem(BaseModel):
    """운영 계정목록 항목(booker·provider). 운영자라 실 이메일·실 역할·실 활성여부를 노출한다."""

    id: uuid.UUID
    email: str  # ⚠️ 운영자라 실 이메일 노출(익명화 안 함 — anonymous-booker-label 예외)
    role: str  # 'booker' | 'provider' (목록은 admin 제외)
    is_active: bool
    created_at: datetime  # ...Z 직렬화(UserPublic과 동일 규약)

    @field_serializer("created_at")
    def _ser_created_at(self, value: datetime) -> str:
        return isoformat_utc(value)  # 와이어 규약 ...Z(architecture.md L263)


class AdminAccountListResponse(BaseModel):
    """운영 계정목록 응답(페이지네이션). 8.2 비활성 액션 화면이 이 위에 컬럼/버튼을 더한다."""

    items: list[AdminAccountItem]
    total: int
    page: int
    page_size: int


class AdminReservationItem(BaseModel):
    """운영 예약목록/임의취소 항목(Story 8.3, AC4) — 예약 메타 + 룸 이름 + 예약자 실 이메일.

    ``GET /admin/reservations`` 목록 항목이자 ``POST .../cancel`` 응답이다.
    ``ProviderReservationItem``(제공자 표면, 6.1)의 **운영자판**으로, 예약자를 **익명 라벨이 아니라
    실 이메일**로 노출한다 — admin은 운영자(타인-facing 아님)라 ``AdminAccountItem``과 정합하게
    식별정보를 본다(메모 anonymous-booker-label 예외). ``slot_starts``는 ``Reservation.slot_starts``
    ISO ``...Z`` 스냅샷을 ``list[datetime]``로 받아 ``...Z`` 재직렬화한다(취소 후에도 잔존 — 표시
    전용 히스토리). 내부
    ``password_hash`` 등은 스키마에 두지 않는다(NFR-6 — 절대 비노출).
    """

    id: uuid.UUID  # reservation_id
    room_id: uuid.UUID
    room_name: str  # admin.service가 Room PK/배치 조회로 합성
    booker_id: uuid.UUID
    booker_email: str  # ⚠️ 운영자라 실 이메일 노출(익명 라벨 아님 — anonymous-booker-label 예외)
    status: str  # ReservationStatus 값(목록은 confirmed-only·취소 응답은 cancelled)
    slot_starts: list[datetime]  # 점유 슬롯 시작시각 스냅샷(UTC aware — ...Z 직렬화)
    created_at: datetime  # 예약 생성 시각(...Z 직렬화 — 목록 정렬·표시)

    @field_serializer("created_at")
    def _ser_created_at(self, value: datetime) -> str:
        return isoformat_utc(value)  # 와이어 규약 ...Z(architecture.md L263)

    @field_serializer("slot_starts")
    def _ser_slot_starts(self, value: list[datetime]) -> list[str]:
        return [isoformat_utc(slot_start) for slot_start in value]  # 항목별 ...Z


class AdminReservationListResponse(BaseModel):
    """운영 확정 예약목록 응답(페이지네이션 — AdminAccountListResponse 미러)."""

    items: list[AdminReservationItem]
    total: int
    page: int
    page_size: int


class AdminIngestFailure(BaseModel):
    """인제스트 부분 실패 1건(경로 + 사유) — Story 8.4, AC3.

    ``IngestReport.failed``의 ``(경로, 사유)`` 튜플을 명시 와이어 객체로 노출한다. 튜플은 JSON
    배열로 직렬화돼 SDK 타입이 ``[string, string]``으로 모호해지므로 객체로 풀어 ``path``/``reason``
    필드를 분명히 한다. 문서 경로·실패 사유만 담는다(PII 무관 — 인제스트는 corpus 문서만 다룸).
    """

    path: str  # corpus 상대 경로(POSIX)
    reason: str  # 실패 사유(예외 타입 + 메시지 — 어떤 문서가 왜 실패했는지)


class AdminIngestReport(BaseModel):
    """인제스트 처리 리포트 응답(성공/스킵/실패/정리 + 총수) — Story 8.4, AC1·AC3.

    ``POST /admin/ingest``가 ``ingest_corpus`` 실행 후 ``IngestReport``를 이 와이어 형태로 매핑해
    즉시 반환한다(동기·잡 큐 없음). 운영자가 어떤 문서가 적재/스킵/실패/정리됐는지 식별한다.
    ``total``은 dataclass property라 직렬화에 자동 포함되지 않으므로 명시 필드로 둔다(처리 문서
    총수 = 성공+스킵+실패; ``removed``는 정리분이라 총수 미포함 — ``IngestReport`` 규약 보존).
    """

    succeeded: list[str]  # 신규/변경되어 (재)적재된 문서 경로
    skipped: list[str]  # 내용 해시 동일로 적재 스킵(임베딩 호출 0)
    failed: list[AdminIngestFailure]  # 부분 실패(경로 + 사유 — 배치는 미중단)
    removed: list[str]  # corpus에 없어 정리(DELETE)된 stale 청크의 source_path(orphan)
    total: int  # 처리 문서 총수(성공+스킵+실패 — removed 미포함)


class AdminIngestDocument(BaseModel):
    """인제스트 지식베이스 문서 1건 표현 — 운영자가 실행 전에도 현재 적재 현황을 본다.

    corpus 디스크 목록(``docs_corpus/``)과 DB 적재분(``document_chunks``)을 병합해 문서별
    상태를 산출한다(``status``). 인제스트는 멱등 reconcile이라 이 상태가 곧 "다음 실행이 무엇을
    할지"를 미리 보여준다 — pending은 적재 예정, orphan은 정리(삭제) 예정, ingested는 스킵.
    """

    source_path: str  # corpus 상대 경로(POSIX)
    chunk_count: int  # 이 문서로 적재된 청크 수(pending이면 0)
    status: Literal["ingested", "stale", "pending", "orphan"]
    # ingested = 디스크 + DB 존재 + 내용 해시 동일(최신 — 다음 실행 시 스킵) /
    # stale     = 디스크 + DB 존재하나 내용 변경(해시 상이 — 다음 실행 시 재임베딩) /
    # pending   = 디스크에만 존재(미적재 신규 — 다음 실행 시 적재) /
    # orphan    = DB에만 존재(디스크에서 사라짐 — 다음 실행 시 정리 대상)


class AdminIngestDocumentList(BaseModel):
    """인제스트 문서 목록 응답 — ``GET /admin/ingest/documents``.

    페이지네이션 없는 전량 반환이다(corpus 문서는 운영자가 직접 관리하는 소수 — 계정/예약
    목록과 달리 비대 위험이 낮음). 정렬은 service가 ``source_path`` 기준 결정적으로 보장한다.
    """

    documents: list[AdminIngestDocument]
    total: int  # documents 길이(디스크∪DB의 distinct source_path 총수)
