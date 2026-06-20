"""admin 라우터: 운영 계정목록 (Story 8.1, AC2·AC4).

``main.py``가 ``api_router``(``/api/v1``) 아래에 포함하므로 최종 경로는
``/api/v1/admin/*``가 된다.

**규약:**

- **RBAC 가드(1.8 ``core/security`` 재사용):** ``require_role("admin")`` → 비-admin 403
  ``FORBIDDEN_ROLE``, 무토큰 401 ``UNAUTHENTICATED``(``get_current_principal`` 선처리).
  새 RBAC 코드를 작성하지 않고 기존 의존성만 소비한다(아키텍처 L167 — 백엔드 최종 강제).
- **모듈 레벨 싱글톤 의존성:** ``_require_admin = require_role("admin")`` — ``Depends`` 인자에
  ``require_role(...)``를 인라인 호출하면 ruff B008(기본값에서 함수 호출)에 걸린다(rooms 선례).
- **에러 계약 OpenAPI 노출:** ``responses={401,403}``으로 SDK(1.9)가 ``detail.code``
  (``UNAUTHENTICATED``/``FORBIDDEN_ROLE``) 타입을 생성하게 한다.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.admin import service
from app.admin.schemas import (
    AdminAccountItem,
    AdminAccountListResponse,
    AdminIngestDocumentList,
    AdminIngestReport,
    AdminReservationItem,
    AdminReservationListResponse,
)
from app.core.db import get_session
from app.core.errors import ErrorResponse
from app.core.security import AuthPrincipal, require_role

router = APIRouter(prefix="/admin", tags=["admin"])

# 모듈 레벨 싱글톤(B008 회피). 비-admin 403 FORBIDDEN_ROLE·무토큰 401 UNAUTHENTICATED.
_require_admin = require_role("admin")


@router.get(
    "/accounts",
    response_model=AdminAccountListResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def list_accounts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),  # 상한 100 — 무제한 결과셋 차단
    _: AuthPrincipal = Depends(_require_admin),
    session: Session = Depends(get_session),
) -> AdminAccountListResponse:
    """booker·provider 계정 목록을 조회한다 → 200(admin 가드, 읽기 전용·페이지네이션, AC4).

    로그인 → RBAC 403 게이트 → 실데이터 조회를 end-to-end로 실증한다(AC2·AC4).
    """
    return service.list_accounts(session, page=page, page_size=page_size)


@router.post(
    "/accounts/{account_id}/deactivate",
    response_model=AdminAccountItem,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def deactivate_account(
    account_id: uuid.UUID,
    _: AuthPrincipal = Depends(_require_admin),
    session: Session = Depends(get_session),
) -> AdminAccountItem:
    """계정을 비활성한다(provider면 룸 캐스케이드) → 200(admin 가드, 멱등, Story 8.2).

    행 삭제가 아닌 ``is_active`` flip이라 액션 동사 ``POST .../deactivate``를 쓴다(취소/거절
    4.7/6.2 선례). 멱등(이미 비활성)은 200이라 별도 status 없음. admin 대상/미존재는 404
    ``ACCOUNT_NOT_FOUND``(존재 누설 방지). 캐스케이드·원자성·멱등은 전부 service가 보장한다.
    """
    return service.deactivate_account(session, account_id=account_id)


@router.get(
    "/reservations",
    response_model=AdminReservationListResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def list_reservations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),  # 상한 100 — 무제한 결과셋 차단
    _: AuthPrincipal = Depends(_require_admin),
    session: Session = Depends(get_session),
) -> AdminReservationListResponse:
    """확정 예약 목록을 조회한다 → 200(admin·읽기 전용·confirmed-only·페이지네이션, Story 8.3).

    운영자가 임의 취소 대상(확정 예약)을 식별하는 목록이다. 예약자는 실 이메일로 노출한다
    (익명 라벨 아님 — accounts 정합). 정렬·페이지네이션·N+1 합성은 전부 service가 보장한다.
    """
    return service.list_reservations(session, page=page, page_size=page_size)


@router.post(
    "/reservations/{reservation_id}/cancel",
    response_model=AdminReservationItem,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def cancel_reservation(
    reservation_id: uuid.UUID,
    _: AuthPrincipal = Depends(_require_admin),
    session: Session = Depends(get_session),
) -> AdminReservationItem:
    """확정 예약을 임의 취소한다(슬롯 재활성 + 예약자 통지) → 200(admin 가드, 멱등, Story 8.3).

    상태 전이(``cancelled``) + 점유 슬롯 DELETE(재활성) + 예약자 ``status_change``/``cancelled``
    통지가 **단일 트랜잭션으로 원자**(deferred L42 회수). 행 삭제가 아닌 status flip이라 액션 동사
    ``POST .../cancel``을 쓴다(4.7/6.2 선례). 멱등(이미 종료)은 200(별도 409 없음). 미존재는 404
    ``RESERVATION_NOT_FOUND``(누설 방지). **시간 게이트 없음**(admin 권한 — service가 프리미티브
    직접 호출). 슬롯 재활성·통지 원자·멱등은 전부 service가 보장한다.
    """
    return service.force_cancel_reservation(session, reservation_id=reservation_id)


@router.get(
    "/ingest/documents",
    response_model=AdminIngestDocumentList,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def list_ingest_documents(
    _: AuthPrincipal = Depends(_require_admin),
    session: Session = Depends(get_session),
) -> AdminIngestDocumentList:
    """인제스트 지식베이스 문서 목록을 상태와 함께 조회한다 → 200(admin 가드, 읽기 전용).

    운영자가 인제스트 메뉴 진입 시 현재 적재 현황(어떤 문서가 ingested/pending/orphan인지)을
    본다. **읽기 전용**(OpenAI·DB 쓰기 0) — ``POST /ingest``의 파괴적 실행과 분리돼, 메뉴를
    여는 것만으로 인제스트가 돌지 않는다. 정적 경로 ``/ingest/documents``가 ``POST /ingest``와
    충돌하지 않도록 별도 서브패스로 둔다(메서드+경로 모두 구분).
    """
    return service.list_ingest_documents(session)


@router.post(
    "/ingest",
    response_model=AdminIngestReport,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def trigger_ingest(
    _: AuthPrincipal = Depends(_require_admin),
    session: Session = Depends(get_session),
) -> AdminIngestReport:
    """``docs_corpus/`` 문서 인제스트를 트리거하고 처리 리포트를 반환한다(Story 8.4, AC1·3·5).

    **★동기 ``def`` 핸들러(``async def`` 절대 금지):** ``ingest_corpus``·``build_embedder``(OpenAI
    HTTP)·``SqlDocumentChunkStore``(동기 psycopg3 commit)는 전부 블로킹이다. FastAPI는 **동기
    ``def`` 라우트를 스레드풀에서 실행**해 이벤트 루프를 막지 않는다 — ``async def``로 만들면 블로킹
    호출이 루프를 직접 막아 전 서버가 정지한다(반복 함정). 처리 후 ``IngestReport``를 200으로 즉시
    반환한다(잡 큐·폴링 없음). 멱등·부분실패·stale 청크 reconcile은 전부 service/코어가 보장한다.

    **에러 계약:** 무토큰 401 ``UNAUTHENTICATED``·비-admin 403 ``FORBIDDEN_ROLE``만. per-doc 실패는
    리포트 본문(``failed``)이라 엔드포인트 자체는 200(404/409 없음).
    """
    return service.trigger_ingest(session)
