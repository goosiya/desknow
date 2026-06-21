"""FastAPI 앱 진입점 (Story 1.2 — walking skeleton).

- 앱 startup(lifespan) 시 ``get_settings()`` 호출로 Story 1.1의 fail-fast를 앱 기동에
  연결한다 (필수 키 누락/빈 값이면 ``ValidationError``로 기동 실패). 이어서 Story 1.4의
  ``verify_db_connection()``으로 DB 연결·pgvector 확장을 검증한다. import 시점이 아니라
  startup 시점이라, ``app.main``을 import만 하는 도구·테스트는 ``.env``/DB 없이도 안전하다.
- ``CORSMiddleware``로 웹 origin(localhost:3000/3001)을 등록한다.
  RN/모바일은 네이티브라 CORS가 적용되지 않는다(LAN IP로 직접 접근).
- 모든 라우트는 ``/api/v1`` 프리픽스 아래에 둔다(버저닝).
- 헬스 엔드포인트는 DB·외부 의존성에 접근하지 않는다(liveness만). DB readiness는
  lifespan에서만 검증한다(헬스 엔드포인트에 DB 접근을 추가하지 않는다).
- 도메인 모듈(auth/rooms/...)은 1.2에서 빈 골격이라 등록할 라우터가 없다(후속 스토리가 추가).
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.admin.router import router as admin_router
from app.auth.router import router as auth_router
from app.chatbot.router import router as chatbot_router
from app.core.config import get_settings
from app.core.db import verify_db_connection
from app.core.errors import register_exception_handlers
from app.favorites.router import router as favorites_router
from app.notifications.router import router as notifications_router
from app.reservations.router import me_router as reservations_me_router
from app.reservations.router import provider_router as reservations_provider_router
from app.reservations.router import router as reservations_router
from app.reviews.router import me_router as reviews_me_router
from app.reviews.router import reply_router as reviews_reply_router
from app.reviews.router import router as reviews_router
from app.rooms.router import router as rooms_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """앱 startup 시점에 환경·DB 검증을 트리거한다(fail-fast를 앱 기동에 연결).

    1. ``get_settings()`` — 필수 키 누락/빈 값이면 ``ValidationError``(Story 1.1).
    2. ``verify_db_connection()`` — DB 연결 실패/ pgvector 미존재면
       ``DatabaseConnectionError``(Story 1.4).

    *import 시점*이 아니라 *startup 시점*에 검증하므로, ``app.main``을 import만 하는
    도구·테스트(예: ``tests/test_main.py``)는 ``.env``/DB 없이도 안전하다
    (CI/신규 클론에서 테스트 수집이 깨지지 않는다).
    """
    get_settings()
    verify_db_connection()
    yield


# 웹 서피스 origin (Story 1.2: web=3000, admin=3001). 모바일은 네이티브라 CORS 무관.
# 배포 origin은 ``EXTRA_CORS_ORIGINS``(쉼표 구분) 환경변수로 주입한다 — 웹/어드민이 API를
# cross-origin 직접 호출(credentials:"include")하는 구조라 운영 web/admin 도메인을 화이트리스트해야
# 한다. import 시점에 ``os.environ``을 직접 읽어(``get_settings()``의 fail-fast를 import에 묶지
# 않음) ``app.main`` import-only 도구·테스트(test_main)의 안전성을 유지한다.
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    *(o.strip() for o in os.environ.get("EXTRA_CORS_ORIGINS", "").split(",") if o.strip()),
]

API_V1_PREFIX = "/api/v1"


def custom_generate_unique_id(route: APIRoute) -> str:
    """operationId를 ``{tag}_{name}``(예: ``auth_register``)로 생성한다(Story 1.9).

    FastAPI 기본 operationId(``register_api_v1_auth_register_post``)는 장황해 생성 SDK
    함수명이 보기 나쁘다. 소비처 0인 지금이 계약(operationId) 확정 적기다. 변경 시
    ``openapi.json``을 반드시 재생성해야 한다(드리프트 게이트가 잡는다).
    태그 없는 라우트는 ``default``로 폴백한다(현재 모든 라우트에 태그 존재).
    """
    # ``APIRoute.tags``는 런타임 속성이지만 이 FastAPI 버전은 cast 헬퍼로 설정해 mypy가
    # 정적으로 인식하지 못한다 → getattr로 안전 접근(태그 없는 라우트도 폴백 처리).
    tags = getattr(route, "tags", None)
    tag = str(tags[0]) if tags else "default"
    return f"{tag}_{route.name}"


app = FastAPI(
    title="DeskNow API",
    version="0.1.0",
    description="DeskNow 백엔드 API (Story 1.2 골격).",
    lifespan=lifespan,
    generate_unique_id_function=custom_generate_unique_id,
)

# 전역 예외 핸들러 배선(Story 1.5): 도메인 에러·검증 에러를 표준 스키마로 응답.
# 등록 로직은 core/errors가 소유하고 main은 배선만 한다. DB를 트리거하지 않으므로
# test_main의 모듈 레벨 TestClient(app) 패턴(lifespan 미실행)에 안전하다.
register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,  # 웹 쿠키 인증(Story 1.8) 대비
    allow_methods=["*"],
    allow_headers=["*"],
)

# 모든 도메인 라우터가 공유하는 /api/v1 프리픽스 루트 라우터.
api_router = APIRouter(prefix=API_V1_PREFIX)


@api_router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """liveness 헬스체크. DB·외부 의존성에 접근하지 않는다(DB readiness는 lifespan에서만 검증)."""
    return {"status": "ok"}


# 도메인 라우터는 /api/v1 프리픽스 아래에 둔다(버저닝). auth: 회원가입(Story 1.7).
# auth.router import는 auth.models(테이블 등록)를 끌어오지만 DB에 접근하지 않는다
# (엔진은 get_session 호출 시 지연 생성 — 1.4). → test_main 모듈 레벨 TestClient 패턴 안전.
api_router.include_router(auth_router)
# rooms: 공간 등록 + 주소 검색(Story 2.2). rooms.router import는 rooms.models(테이블 등록)를
# 끌어오나 DB 미접근(엔진 지연 생성 — 1.4). → test_main 모듈레벨 TestClient 패턴 안전.
api_router.include_router(rooms_router)
# favorites: 즐겨찾기 추가/제거/조회(Story 3.7 — web 최초 인증 필요 기능). favorites.router import는
# favorites.models(Favorite 테이블 등록)를 끌어오나 DB 미접근(엔진 지연 생성 — 1.4).
api_router.include_router(favorites_router)
# reservations: 즉시 예약 확정(Story 4.5 — POST /rooms/{room_id}/reservations). reservations.router
# import는 reservations.models(예약·점유 테이블 등록)를 끌어오나 DB 미접근(엔진 지연 생성 — 1.4).
api_router.include_router(reservations_router)
# reservations(본인 현황): GET /reservations(Story 4.8 — 룸 비결합 top-level 목록). 중첩 라우터와
# 별도 인스턴스(me_router)지만 같은 tags=["reservations"]라 operationId 규약(reservations_*) 유지.
api_router.include_router(reservations_me_router)
# reservations(제공자 현황): GET /provider/reservations(Story 6.1 — 제공자 소유 룸 예약 조회·익명
# 라벨). 여러 룸에 걸친 provider 뷰라 별도 top-level 인스턴스(provider_router)지만 같은 tags=
# ["reservations"]라 operationId는 reservations_* 규약. /provider/* 네임스페이스 신규(경로 충돌 0).
api_router.include_router(reservations_provider_router)
# notifications: 인앱 배너 조회/소멸(Story 5.1 — GET /notifications · POST .../{id}/dismiss).
# notifications.router import는 notifications.models(통지 테이블 등록)를 끌어오나 DB 미접근(엔진
# 지연 생성 — 1.4). → test_main 모듈레벨 TestClient 패턴 안전.
api_router.include_router(notifications_router)
# reviews(작성): POST /reservations/{reservation_id}/reviews(Story 5.5 — booker 인증·소유권). 예약
# 종속 top-level이라 reservations me_router와 동형 별도 인스턴스(reviews_me_router)지만 tags=
# ["reviews"]라 operationId는 reviews_* 규약. reviews.router import는 reviews.models(후기 테이블
# 등록)를 끌어오나 DB 미접근(엔진 지연 생성 — 1.4). → test_main 모듈레벨 TestClient 패턴 안전.
api_router.include_router(reviews_me_router)
# reviews(조회): GET /rooms/{room_id}/reviews(Story 5.5 — 룸 상세 후기 목록·공개 무인증).
api_router.include_router(reviews_router)
# reviews(답글): POST /reviews/{review_id}/reply(Story 5.6 — provider 인증·소유권 403). 후기 종속
# top-level이라 별도 인스턴스(reviews_reply_router)지만 tags=["reviews"]라 operationId는 reviews_*.
api_router.include_router(reviews_reply_router)
# chatbot: 비스트리밍 멀티턴 대화 + 세션 재수화/초기화(Story 7.3 — POST/GET /chatbot/messages ·
# DELETE /chatbot/session). chatbot.router import는 graph(langgraph)·llm 어댑터를 끌어오나 DB
# 미접근(상태=인메모리 MemorySaver·모델은 첫 요청에 지연 생성). → test_main TestClient 안전.
api_router.include_router(chatbot_router)
# admin: 운영(시드 관리자) 계정목록(Story 8.1 — GET /admin/accounts, require_role("admin") 가드).
# admin.router import는 admin.service→auth.models(User 테이블 등록)를 끌어오나 DB 미접근(엔진
# 지연 생성 — 1.4). → test_main 모듈레벨 TestClient 패턴 안전. CORS(localhost:3001)는 이미 허용.
api_router.include_router(admin_router)

app.include_router(api_router)
