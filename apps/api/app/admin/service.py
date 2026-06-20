"""admin 도메인 서비스: 운영 계정목록 조회 (Story 8.1, AC4 — 읽기 전용).

도메인 조회 로직을 라우터에서 분리한다(아키텍처 §Boundaries L355 — 라우터는 SQL 직접
접근 금지). ``User`` 모델은 ``app.auth.models``에서 재사용한다(도메인 간 모델 재정의 금지).

**deferred 교훈 선반영(메모 dev-workflow-policy — 반복 함정 프리플라이트):**

- **정렬 결정성:** ``created_at`` 단일 키는 동률 시 비결정 순서가 된다(4.8/6.1이 그래서
  deferred). 보조 키 ``id``를 **처음부터** 포함해 안정 정렬을 보장한다(재-defer 금지).
- **페이지네이션:** LIMIT 없는 전량 반환은 목록 비대(favorites/4.8/6.1 누적 deferred)를
  답습한다. ``offset``/``limit``을 **처음부터** 적용하고 상한은 라우터가 강제한다(≤100).
"""
from __future__ import annotations

import uuid
from pathlib import Path

from sqlmodel import Session, col, func, select, update

from app.admin.schemas import (
    AdminAccountItem,
    AdminAccountListResponse,
    AdminIngestDocument,
    AdminIngestDocumentList,
    AdminIngestFailure,
    AdminIngestReport,
    AdminReservationItem,
    AdminReservationListResponse,
)
from app.auth.models import User
from app.chatbot.ingest import (
    DEFAULT_CORPUS_DIR,
    SqlDocumentChunkStore,
    build_embedder,
    compute_content_hash,
    ingest_corpus,
    iter_corpus_files,
    load_document_text,
)
from app.core.errors import DomainError, ErrorCode
from app.reservations import service as reservations_service
from app.reservations.models import Reservation, ReservationStatus
from app.rooms.models import Room

# admin 계정은 목록에서 제외한다 — 시드 운영자 자기 자신 노출/오조작 방지. 8.2 비활성 대상은
# booker·provider뿐이라 정합한다(필요 시 admin 자체 조회는 별도 결정).
_EXCLUDED_ROLE = "admin"

# 합성 시 룸/예약자를 못 찾는 도달 불가 경로의 폴백 표시값(FK RESTRICT라 정상 경로엔 항상 존재).
_UNKNOWN_ROOM_NAME = "알 수 없는 공간"
_UNKNOWN_EMAIL = "알 수 없음"


def list_accounts(
    session: Session, *, page: int, page_size: int
) -> AdminAccountListResponse:
    """booker·provider 계정 목록을 페이지네이션해 반환한다(AC4 — RBAC end-to-end 실증용).

    ``total``은 같은 where(admin 제외)로 집계하므로 페이지 수 계산이 정확하다. 정렬은
    ``created_at`` 내림차순 + ``id`` 오름차순(동률 안정화)이다. 실 이메일/역할/활성여부를
    노출하되(운영자 — 익명화 예외), ``password_hash``는 스키마에 부재라 절대 새지 않는다.
    """
    where = col(User.role) != _EXCLUDED_ROLE
    total = session.exec(select(func.count()).select_from(User).where(where)).one()
    rows = session.exec(
        select(User)
        .where(where)
        # 보조 키 id로 created_at 동률의 비결정 정렬을 막는다(4.8/6.1 deferred 선반영).
        .order_by(col(User.created_at).desc(), col(User.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        AdminAccountItem(
            id=u.id,
            email=u.email,
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in rows
    ]
    return AdminAccountListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


def deactivate_account(
    session: Session, *, account_id: uuid.UUID
) -> AdminAccountItem:
    """계정을 비활성하고(provider면 그의 룸까지 캐스케이드) 갱신된 항목을 반환한다(AC1·2·4).

    **비활성 단방향(KTH 2026-06-18):** 재활성/토글은 없다 — 본 함수는 비활성 방향만 수행한다.

    **동작(조건부 원자 UPDATE·멱등·캐스케이드 — 단일 트랜잭션):**

    1. **대상 가드:** 미존재 또는 admin 대상(자기 자신 포함)이면 ``ACCOUNT_NOT_FOUND``(404)로
       거부한다(미존재·admin을 합쳐 admin 존재 누설·자기/타admin 비활성을 동시에 차단 —
       ``list_accounts``의 ``_EXCLUDED_ROLE`` 미러).
    2. **계정 비활성(조건부 원자):** ``UPDATE users SET is_active=false WHERE id=:id AND
       is_active=true``. ``rowcount==0``=이미 비활성(멱등 패자) → no-op(예외 아님, 그대로 진행).
       ``_transition_to_terminal``(4.7/6.2)의 단일-승자 중재 정신 — read-then-flip 비원자 금지.
    3. **provider 캐스케이드:** provider면 그의 룸(``WHERE provider_id=:id AND is_active=true``)을
       비활성한다. ``uq_rooms_provider_id``로 현재는 0..1개이나 ``WHERE provider_id``로 0..n을
       안전 처리한다(타 provider 룸은 격리되어 불변). booker는 룸 미소유라 캐스케이드 없음.
    4. **reservations/slots는 건드리지 않는다**(AC2 — 기존 확정 예약 유지·예약 임의취소는 8.3).
    5. 한 번의 ``commit`` 후 ``refresh``로 갱신 상태를 읽어 ``AdminAccountItem``을 반환한다.
    """
    target = session.get(User, account_id)
    if target is None or target.role == _EXCLUDED_ROLE:
        # 미존재·admin을 404로 합침 — admin 존재 누설/자기·타admin 비활성 금지.
        raise DomainError(ErrorCode.ACCOUNT_NOT_FOUND, "해당 계정을 찾을 수 없습니다.")

    # 계정 비활성(조건부 원자) — rowcount 0이면 이미 비활성(멱등 no-op), 에러 아님.
    session.exec(
        update(User)
        .where(col(User.id) == account_id, col(User.is_active).is_(True))
        .values(is_active=False)
    )

    # provider 캐스케이드 — 그의 룸을 같은 트랜잭션에서 비활성(0..n·이미 비활성 룸은 미변경).
    if target.role == "provider":
        session.exec(
            update(Room)
            .where(col(Room.provider_id) == account_id, col(Room.is_active).is_(True))
            .values(is_active=False)
        )

    # 부분 적용 방지 — 계정 + 룸 UPDATE를 한 번에 commit. 이후 refresh로 갱신 상태를 읽는다
    # (Core UPDATE는 identity-map 객체를 자동 동기화하지 않음 — _transition_to_terminal 정신).
    session.commit()
    session.refresh(target)
    return AdminAccountItem(
        id=target.id,
        email=target.email,
        role=target.role,
        is_active=target.is_active,
        created_at=target.created_at,
    )


def _to_admin_reservation_item(
    reservation: Reservation, *, room_name: str, booker_email: str
) -> AdminReservationItem:
    """``Reservation`` + 합성 룸이름/예약자이메일을 ``AdminReservationItem``으로 매핑한다(공유).

    ``list_reservations``(배치 합성)·``force_cancel_reservation``(단건 합성)이 공유한다.
    ``slot_starts``는 ``Reservation.slot_starts``(ISO ``...Z`` 문자열 스냅샷)를 그대로 넘겨
    Pydantic이 ``list[datetime]``로 코어스하게 한다(``ReservationListItem`` 라우터 합성 선례).
    """
    return AdminReservationItem(
        id=reservation.id,
        room_id=reservation.room_id,
        room_name=room_name,
        booker_id=reservation.booker_id,
        booker_email=booker_email,
        status=reservation.status,
        slot_starts=list(reservation.slot_starts),
        created_at=reservation.created_at,
    )


def list_reservations(
    session: Session, *, page: int, page_size: int
) -> AdminReservationListResponse:
    """확정(``confirmed``) 예약 목록을 페이지네이션해 반환한다(Story 8.3, AC4 — 취소 대상 식별).

    **confirmed-only:** 취소 대상은 확정 예약뿐이고 종료(취소/거절) 예약은 멱등 no-op이라 목록에
    무의미하므로 ``status='confirmed'``만 싣는다(집합이 취소로 자연 축소된다). ``total``은 같은
    where로 집계해 페이지 수가 정확하다. 정렬은 ``created_at`` 내림차순 + 보조키 ``id``(동률
    비결정 정렬 방지 — 8.2 ``list_accounts`` 선반영). 페이지네이션은 ``offset``/``limit``(상한 100은
    라우터 강제).

    **N+1 금지 합성:** 페이지 행의 ``room_id``·``booker_id``를 모아 룸/유저를 **각 1회 배치
    조회**(``IN (...)``)해 이름/이메일 맵을 만든 뒤 항목을 합성한다(라우터 PK 합성 정신을 service
    조합 계층에서·행별 재조회 회피). 운영자라 예약자 **실 이메일**을 노출한다(익명 라벨 아님 —
    accounts 정합·메모 anonymous-booker-label 예외).
    """
    where = col(Reservation.status) == ReservationStatus.CONFIRMED
    total = session.exec(
        select(func.count()).select_from(Reservation).where(where)
    ).one()
    rows = session.exec(
        select(Reservation)
        .where(where)
        # 보조 키 id로 created_at 동률의 비결정 정렬을 막는다(8.2 list_accounts 선반영).
        .order_by(col(Reservation.created_at).desc(), col(Reservation.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    # 룸/예약자 배치 조회(각 1쿼리 — 행별 get(Room)/get(User) N+1 회피). 빈 집합이면 쿼리 미발행.
    room_ids = {r.room_id for r in rows}
    booker_ids = {r.booker_id for r in rows}
    rooms = (
        session.exec(select(Room).where(col(Room.id).in_(room_ids))).all()
        if room_ids
        else []
    )
    bookers = (
        session.exec(select(User).where(col(User.id).in_(booker_ids))).all()
        if booker_ids
        else []
    )
    room_names = {room.id: room.name for room in rooms}
    booker_emails = {u.id: u.email for u in bookers}

    items = [
        _to_admin_reservation_item(
            r,
            room_name=room_names.get(r.room_id, _UNKNOWN_ROOM_NAME),
            booker_email=booker_emails.get(r.booker_id, _UNKNOWN_EMAIL),
        )
        for r in rows
    ]
    return AdminReservationListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


def force_cancel_reservation(
    session: Session, *, reservation_id: uuid.UUID
) -> AdminReservationItem:
    """시드 관리자가 특정 예약을 임의 취소한다(Story 8.3, AC1·2·3·5 — 슬롯 재활성 + 예약자 통지).

    **동작(reservations 프리미티브 위임 — 재구현 0):**

    1. **대상 가드:** ``session.get(Reservation, id)`` → 미존재면 ``RESERVATION_NOT_FOUND``(404 —
       누설 방지, 4.7/6.2 미러).
    2. **임의 취소(원자):** ``reservations_service.admin_force_cancel_reservation``이 confirmed면
       status flip + 슬롯 DELETE(재활성) + 예약자 ``status_change``/``reason="cancelled"`` 통지를
       **단일 commit으로 원자**(deferred L42 회수)하고, 이미 종료면 멱등 no-op(효과 0 — AC3).
       **시간 게이트 없음**(admin 권한 — 게이팅 래퍼 우회·프리미티브 직접).
    3. **항목 합성:** 갱신된 예약을 룸 이름·예약자 실 이메일과 함께 ``AdminReservationItem``으로
       반환한다(취소 후 점유 슬롯은 0건이나 ``slot_starts``는 ``Reservation`` 스냅샷이 잔존).

    **도메인 경계(architecture L355):** admin(운영 도메인)이 reservations.service 프리미티브를
    호출해 조합한다(라우터는 SQL 직접 접근 금지). 슬롯/통지 직접 SQL은 프리미티브에 위임한다.
    """
    reservation = session.get(Reservation, reservation_id)
    if reservation is None:
        # 미존재를 404로 — 타인 예약 존재 누설 방지(4.7/6.2 RESERVATION_NOT_FOUND 미러).
        raise DomainError(ErrorCode.RESERVATION_NOT_FOUND, "예약을 찾을 수 없습니다.")

    updated = reservations_service.admin_force_cancel_reservation(session, reservation)

    room = session.get(Room, updated.room_id)
    booker = session.get(User, updated.booker_id)
    return _to_admin_reservation_item(
        updated,
        room_name=room.name if room is not None else _UNKNOWN_ROOM_NAME,
        booker_email=booker.email if booker is not None else _UNKNOWN_EMAIL,
    )


def trigger_ingest(
    session: Session, *, corpus_dir: Path | None = None
) -> AdminIngestReport:
    """``docs_corpus/`` 문서 인제스트를 트리거하고 처리 리포트를 반환한다(Story 8.4, AC1·3·5).

    **얇은 운영 레이어 — 코어 재구현 0:** 7.2 ``ingest_corpus``를 그대로 호출해 멱등(sha256)·문서
    단위 원자성·부분 실패 격리·stale 청크 reconcile(8.4 추가)를 전부 재사용한다. 본 함수는
    (a) 임베더/스토어 배선, (b) ``IngestReport`` → ``AdminIngestReport`` 와이어 매핑만 한다.

    **동기 실행(KTH 2026-06-18):** 라우터가 ``def``(동기)라 FastAPI 스레드풀에서 실행되고, 이
    함수는 ``ingest_corpus``(OpenAI 임베딩 + DB 쓰기, 블로킹)를 끝까지 돌린 뒤 리포트를 즉시
    반환한다(잡 큐·폴링 없음).

    **세션:** 라우터의 요청 스코프 세션(``get_session``)을 ``SqlDocumentChunkStore``에 그대로
    주입한다(store가 자체 commit/rollback이라 요청 세션과 정합 — scripts는 자체 세션 생성이나
    admin은 요청 세션 재사용). corpus 디렉터리 부재는 ``ingest_corpus``가 빈 리포트로 흡수한다
    (``iter_corpus_files``가 non-dir에 빈 순회 + reconcile present_paths 공집합 스킵 — raise 없음).

    Args:
        corpus_dir: 인제스트 대상 디렉터리. 기본값(None)이면 ``DEFAULT_CORPUS_DIR``(테스트 주입용).
    """
    # 임베더/스토어 배선(scripts/ingest_docs.py 골격 미러 — 세션만 요청 스코프 재사용).
    embeddings = build_embedder()
    store = SqlDocumentChunkStore(session)
    report = ingest_corpus(store, corpus_dir or DEFAULT_CORPUS_DIR, embeddings)
    # IngestReport(dataclass) → AdminIngestReport(와이어). failed 튜플을 명시 객체로 변환하고,
    # property인 total을 명시 필드로 옮긴다(dataclass property는 직렬화 자동 포함 안 됨).
    return AdminIngestReport(
        succeeded=report.succeeded,
        skipped=report.skipped,
        failed=[AdminIngestFailure(path=path, reason=reason) for path, reason in report.failed],
        removed=report.removed,
        total=report.total,
    )


def list_ingest_documents(
    session: Session, *, corpus_dir: Path | None = None
) -> AdminIngestDocumentList:
    """인제스트 지식베이스의 문서 목록을 상태와 함께 반환한다(운영 가시성 — 실행 전 현황 표현).

    **상태 산출(인제스트 reconcile 의미를 그대로 미러):** corpus 디스크 목록과 DB 적재분(청크 수
    + content_hash)을 병합해 문서별 상태를 매긴다 — 인제스트가 멱등 reconcile(7.2/8.4)이므로 이
    상태가 곧 "다음 실행이 무엇을 할지"의 예고다.

    - ``ingested``: 디스크 + DB 존재 + **내용 해시 동일**(최신 — 다음 실행 시 스킵).
    - ``stale``: 디스크 + DB 존재하나 **디스크 내용이 적재분과 다름**(변경 — 다음 실행 시 재임베딩).
    - ``pending``: 디스크에만 존재(미적재 신규 — 다음 실행 시 임베딩·적재).
    - ``orphan``: DB에만 존재(디스크에서 삭제/리네임 — 다음 실행 시 reconcile로 정리).

    멱등 대조와 동일한 ``compute_content_hash(load_document_text(...))``로 디스크 해시를 계산해
    적재 해시와 대조하므로, 여기서 ``stale``로 뜬 문서는 실제 인제스트에서 재임베딩되고
    ``ingested``는 스킵된다(표시와 실행의 일관 — 운영자 신뢰).

    **읽기 전용·부작용 0:** 임베더(OpenAI)·DB 쓰기 없이 디스크 스캔 + 단일 집계 쿼리 + 해시
    계산만 한다(``trigger_ingest``의 파괴적 실행과 분리 — 메뉴 진입만으로 인제스트가 돌지 않는다).
    정렬은 ``source_path`` 기준 결정적(admin 목록 안정 정렬 정책 미러).

    Args:
        corpus_dir: 스캔 대상 디렉터리. 기본값(None)이면 ``DEFAULT_CORPUS_DIR``(테스트 주입용).
    """
    # 디스크 corpus 파일(rel POSIX 경로 → 절대 경로) — 파일이 있으면 orphan 아님(적재 여부 무관).
    base = corpus_dir or DEFAULT_CORPUS_DIR
    disk_files = {path.relative_to(base).as_posix(): path for path in iter_corpus_files(base)}
    # DB 적재분(source_path별 (청크 수, 대표 content_hash)) — 단일 GROUP BY 집계.
    loaded = SqlDocumentChunkStore(session).summarize_loaded_documents()

    documents: list[AdminIngestDocument] = []
    # 디스크∪DB의 distinct 경로를 결정적 순서로 — 한 문서가 한 행으로만 나오도록 합집합 순회.
    for source_path in sorted(disk_files.keys() | loaded.keys()):
        on_disk = source_path in disk_files
        chunk_count, loaded_hash = loaded.get(source_path, (0, None))
        if not on_disk:
            status: str = "orphan"  # DB에만 — 디스크에서 사라짐(정리 예정)
        elif loaded_hash is None:
            status = "pending"  # 디스크에만 — 미적재 신규
        else:
            # 디스크 내용 해시 vs 적재 해시(멱등 대조와 동일 계산). 읽기 실패는 stale로 본다
            # (실제 인제스트가 그 문서를 재시도/실패 보고하므로 운영자에게 주의를 남기는 게 옳다).
            try:
                disk_hash = compute_content_hash(load_document_text(disk_files[source_path]))
            except Exception:  # noqa: BLE001 — 읽기 실패는 변경 취급(주의 환기)
                disk_hash = None
            status = "ingested" if disk_hash == loaded_hash else "stale"
        documents.append(
            AdminIngestDocument(
                source_path=source_path, chunk_count=chunk_count, status=status
            )
        )
    return AdminIngestDocumentList(documents=documents, total=len(documents))
