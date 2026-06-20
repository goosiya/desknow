"""LangGraph 챗봇 툴 (Story 7.5 — 문서검색).

그래프에 ``bind_tools``로 바인딩되는 LangChain 툴을 모은다. 7.6(자연어 예약검색)이 예약DB 툴을
**같은 모듈에 추가**한다 — 한 그래프에 여러 툴이 공존하는 단일 출처.

★함정(툴 세션 — 그래프 싱글톤엔 요청 스코프 DI 없음):
그래프·MemorySaver는 프로세스 싱글톤이고(graph.py 함정 #1), 라우터는 ``Depends(get_session)``을
쓰지 않는다(router.py 규약 — 상태는 인메모리). 따라서 툴은 요청 세션을 주입받을 수 없다 → **자체
단명 세션**(``with Session(get_engine()) as s:``)을 열고 닫는다. 임베더는 매 호출 새로 만들지 말고
**모듈 lazy 싱글톤**으로 재사용한다(클라이언트 생성 비용 회피).

검색 로직은 ``retrieval.search_documents``(순수·주입식)에 두고 툴은 **얇게** 둔다 — 단위 테스트는
``search_documents``/``_get_embedder``를 monkeypatch 해 키·DB 없이 직렬화·모름 신호를 검증한다.
"""
from __future__ import annotations

import re
from datetime import date as _date
from typing import TYPE_CHECKING, Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from sqlmodel import Session

from app.chatbot.ingest.embedding import build_embedder
from app.chatbot.retrieval import (
    DEFAULT_MAX_DISTANCE,
    DEFAULT_TOP_K,
    search_by_vector,
    search_documents,
)
from app.core.db import get_engine
from app.core.time import ROOM_TZ, today_in_tz
from app.rooms.regions import level_codes, resolve_region
from app.rooms.service import available_room_ids_at, search_rooms

if TYPE_CHECKING:
    import uuid

    from app.chatbot.ingest.embedding import Embedder
    from app.chatbot.models import DocumentChunk
    from app.rooms.schemas import RoomListItem

# 채택 청크가 없을 때 모델에게 돌려주는 **명시 신호**. 모델은 이 문자열을 보면 근거 없음으로
# 판단해 분기 b("그건 확인이 안 돼요.")로 가야 한다(프롬프트가 강제 — prompts.py). 그럴듯한
# 추측 답변을 지어내도록 유도하지 않는 게 핵심이다(환각 금지).
NO_RELEVANT_DOCS = "관련 근거를 찾지 못했어요."

# 임베더 모듈 lazy 싱글톤(매 툴 호출마다 OpenAI 클라 재생성 비용 회피 — 함정 §툴 세션).
_embedder: Embedder | None = None


def _get_embedder() -> Embedder:
    """쿼리 임베딩 클라이언트를 1회 생성해 재사용한다(7.2 ``build_embedder`` 재사용)."""
    global _embedder
    if _embedder is None:
        _embedder = build_embedder()
    return _embedder


# ── 쿼리 정제(다중쿼리 검색, KTH 2026-06-18 결정) ──
# 사용자 어휘에 검색 품질이 좌우되지 않도록, 질문을 안내 문서 검색에 적합한 정규화 쿼리 여러 개로
# 정제한다. 원문 + 변형들로 각각 검색해 회수를 높인다(한 표현이 놓쳐도 다른 표현이 근거를 찾을
# 기회). 코퍼스를 답에 맞춰 고치거나 프롬프트로 우겨넣는 대신 **검색 단계 자체**를 강건하게 만든다.
_refiner_model: Any | None = None

# 정제 변형 개수 상한(원문 제외). 원문 포함 총 검색 횟수 = _MAX_VARIANTS + 1.
_MAX_VARIANTS = 3

_REFINE_SYSTEM = (
    "너는 검색 쿼리 정제기야. 사용자의 질문을 데스크나우(스터디룸 예약 서비스) 안내 문서에서 "
    "검색하기 좋게 다듬어.\n"
    "- 질문의 **핵심 주제를 그대로 유지**해. 주제를 바꾸거나 없는 조건·키워드를 지어내지 마.\n"
    "- 어휘를 정규화/보강한 서로 다른 표현의 검색 쿼리를 정확히 3개 만들어(동의어·핵심 명사 "
    "위주, 각 쿼리는 짧은 구절).\n"
    "- 각 쿼리는 한 줄에 하나씩, 번호·따옴표·군더더기 없이 텍스트만 출력해."
)


def _get_refiner() -> Any:
    """쿼리 정제용 채팅 모델을 1회 생성해 재사용한다(설정 기본 프로바이더 — 대화 모델과 별개).

    툴을 바인딩하지 않은 순수 생성 모델이다. 매 검색마다 재생성하지 않도록 모듈 싱글톤으로 둔다.
    """
    global _refiner_model
    if _refiner_model is None:
        from app.chatbot.llm import create_chat_model

        _refiner_model = create_chat_model()
    return _refiner_model


def _refine_queries(query: str) -> list[str]:
    """사용자 질문을 검색용 정규화 쿼리 변형 목록으로 정제한다(원문 제외, 최대 ``_MAX_VARIANTS``개).

    LLM 호출이 실패하면 **빈 리스트로 우아하게 강등**한다 → 호출처는 원문만으로 검색(회귀 0). 내부
    오류를 모델·사용자에게 노출하지 않는다. 단위 테스트는 이 함수를 monkeypatch 해 LLM 없이
    다중쿼리 병합을 검증한다(``_get_embedder``/``search_documents`` 주입 패턴과 동형).
    """
    try:
        reply = _get_refiner().invoke(
            [SystemMessage(content=_REFINE_SYSTEM), HumanMessage(content=query)]
        )
        raw = reply.content if isinstance(reply.content, str) else str(reply.content)
    except Exception:
        return []
    variants: list[str] = []
    for line in raw.splitlines():
        cleaned = line.strip().lstrip("-*0123456789.) ").strip().strip('"').strip()
        if cleaned and cleaned != query and cleaned not in variants:
            variants.append(cleaned)
    return variants[:_MAX_VARIANTS]


# ── 관련성 판정(CRAG-style grade, KTH 2026-06-18 결정) ──
# 코사인 거리는 "주제 관련"과 "답을 담음"을 구별하지 못한다(주차 질문이 이용 문서에 주제적으로
# 가까워도 주차 요금 답은 없음 — 임베딩 교체·청킹 실험으로 거리론 못 가름이 확인됨). 그래서 회색
# 지대 후보는 LLM이 "이 문서가 질문에 실제로 답하는가"를 의미로 판정해 채택/기각한다.
# 비용 게이팅: 명백히 가까운 후보(<= _CONFIDENT_MAX_DISTANCE)가 있으면 grade를 건너뛰고 채택한다.
_RETRIEVE_MAX_DISTANCE = 0.75  # 느슨한 회수 상한(회색지대까지 후보로 끌어온다 — recall↑)
_CONFIDENT_MAX_DISTANCE = 0.5  # 이보다 가까우면 확신 채택(grade 생략 — 비용 절감)

_GRADE_SYSTEM = (
    "너는 검색 결과 관련성 심판이야. 사용자 질문과 후보 문서들이 주어지면, 각 문서가 그 질문에 "
    "대한 답을 **실제로 담고 있는지** 판정해.\n"
    "- 주제가 비슷하거나 관련돼 보여도, 질문이 묻는 정보가 문서에 **실제로 들어있지 않으면 관련 "
    "없음**으로 판정해(예: '주차 요금'을 물었는데 문서가 이용 방법만 설명하면 관련 없음).\n"
    "- 질문에 답하는 데 쓸 수 있는 문서의 번호만 쉼표로 출력해(예: 0,2). 하나도 없으면 정확히 "
    "'none'이라고만 출력해. 번호 외 다른 말은 하지 마."
)


def _grade_relevance(
    query: str, candidates: list[tuple[DocumentChunk, float]]
) -> list[tuple[DocumentChunk, float]]:
    """후보 청크 중 질문에 **실제로 답하는** 것만 LLM이 의미로 판정해 남긴다(CRAG grade).

    LLM 호출/파싱 실패 시 **엄격 거리 임계값(``DEFAULT_MAX_DISTANCE``)으로 강등**한다 — grade는
    향상이고 거리 임계값이 바닥이다(근거를 통째로 잃거나 과채택하지 않도록). 단위 테스트는 이
    함수를 monkeypatch 해 LLM 없이 검증한다(``_refine_queries`` 패턴과 동형).
    """
    try:
        listing = "\n\n".join(
            f"[{i}] {chunk.content}" for i, (chunk, _d) in enumerate(candidates)
        )
        reply = _get_refiner().invoke(
            [
                SystemMessage(content=_GRADE_SYSTEM),
                HumanMessage(content=f"질문: {query}\n\n후보 문서:\n{listing}"),
            ]
        )
        raw = reply.content if isinstance(reply.content, str) else str(reply.content)
    except Exception:
        return [cd for cd in candidates if cd[1] <= DEFAULT_MAX_DISTANCE]
    keep = {int(n) for n in re.findall(r"\d+", raw)}
    return [cd for i, cd in enumerate(candidates) if i in keep]


@tool
def search_service_docs(query: str) -> str:
    """서비스 이용방법·FAQ·예약/취소/환불 규정 등 **서비스 안내 문서**에서 근거를 검색한다.

    사용자가 데스크나우 이용 방법, 자주 묻는 질문, 예약·취소·환불·이용 규정처럼 **문서에 적혀 있을
    법한 안내**를 물으면 이 툴을 호출해 근거를 회수한다. 잡담이나 스터디룸 추천·예약 검색에는
    호출하지 않는다. 반환된 근거 안에서만 답하고, "관련 근거를 찾지 못했어요."가 오면 지어내지
    말고 모른다고 안내한다.

    Args:
        query: 검색할 자연어 질의(사용자 질문 또는 그 핵심).

    Returns:
        채택된 문서 청크들을 출처와 함께 직렬화한 그라운딩 컨텍스트. 채택 청크가 없으면
        ``NO_RELEVANT_DOCS`` 문자열.
    """
    embedder = _get_embedder()
    # 단명 세션(요청 스코프 DI 부재 — 함정 §툴 세션). search는 세션 수명을 넘기지 않는다.
    with Session(get_engine()) as session:
        # 1) 빠른 경로(raw-first): 원문 쿼리만으로 먼저 검색. 확신 적중이면(<= 확신 임계값) 쉬운
        #    질문이라 정제·grade를 **둘 다 생략**하고 즉시 채택(지연·비용↓ — 대부분 질문).
        raw_results = search_documents(
            session, query, embedder, max_distance=_RETRIEVE_MAX_DISTANCE
        )
        confident_raw = (
            bool(raw_results) and raw_results[0][1] <= _CONFIDENT_MAX_DISTANCE
        )
        if confident_raw:
            candidates = raw_results
        else:
            # 2) 느린 경로(애매·미적중만): 질문을 정규화 쿼리로 정제하고 변형들을 **한 번에 배치
            #    임베딩**해 검색, 원문 결과와 청크별 최소 거리로 병합한다(round-trip↓·회수↑).
            best: dict[uuid.UUID, tuple[DocumentChunk, float]] = {
                chunk.id: (chunk, dist) for chunk, dist in raw_results
            }
            variants = _refine_queries(query)
            if variants:
                for vec in embedder.embed_documents(variants):
                    for chunk, distance in search_by_vector(
                        session, vec, max_distance=_RETRIEVE_MAX_DISTANCE
                    ):
                        current = best.get(chunk.id)
                        if current is None or distance < current[1]:
                            best[chunk.id] = (chunk, distance)
            candidates = sorted(best.values(), key=lambda cd: cd[1])[:DEFAULT_TOP_K]
    if not candidates:
        return NO_RELEVANT_DOCS
    # 3) 채택 결정: 거리는 "주제 관련"만 알려줘 답 포함 여부를 못 가른다. 확신 적중이면(raw 또는
    #    변형) 엄격 거리 바닥(DEFAULT_MAX_DISTANCE) 내에서 채택(grade 생략), 전부 회색지대면 LLM이
    #    "질문에 실제로 답하는가"를 판정한다.
    if confident_raw or candidates[0][1] <= _CONFIDENT_MAX_DISTANCE:
        adopted = [cd for cd in candidates if cd[1] <= DEFAULT_MAX_DISTANCE]
    else:
        adopted = _grade_relevance(query, candidates)
    if not adopted:
        return NO_RELEVANT_DOCS
    # 채택 청크를 출처와 함께 직렬화한다 — 모델이 근거 텍스트 안에서만 답하도록 그라운딩 컨텍스트로
    # 넘긴다. 거리는 모델에 노출하지 않는다(채택 여부는 거리+grade로 이미 판정 — 노이즈 제거).
    blocks = [
        f"[출처: {chunk.source_path}]\n{chunk.content}" for chunk, _distance in adopted
    ]
    return "\n\n".join(blocks)


# ── 예약검색 툴(Story 7.6 — 자연어 예약 검색, 문서검색과 같은 그래프에 공존) ──
# 명시 신호 문자열(7.5 NO_RELEVANT_DOCS 패턴 미러). 모델은 이 신호를 보면 환각 없이 안내·재질문
# 한다(프롬프트가 강제 — prompts.py §예약 검색). 조용한 빈 결과로 오인하지 않게 하는 게 핵심이다.
REGION_NOT_FOUND = "그 지역은 못 찾았어요."
NO_AVAILABLE_ROOMS = "조건에 맞는 빈 방을 찾지 못했어요."
# 잘못된 시간 인자(범위 밖 시각·파싱 불가 날짜)는 무필터로 삼키지 않고 명시 신호로 돌려 모델이
# 재질문하게 한다(조건이 사라진 무필터 결과를 "요청 시각에 맞는 것처럼" 내지 않기 — 리뷰 patch).
INVALID_TIME = "시간 조건을 이해하지 못했어요. 다시 말씀해 주실래요?"
# near_me 검색용 — 위치 좌표가 요청에 없을 때(권한 거부·미측정) 모델에 돌려주는 명시 신호. 모델은
# 위치를 켜달라거나 동네를 알려달라고 재질문한다(조용한 빈 결과로 위장 금지 — 프롬프트 §예약 검색).
LOCATION_UNAVAILABLE = "위치 정보를 받지 못했어요."

# 챗봇 "내 주변" 기본 반경(km)과 상한(km). 사용자가 더 넓게 요청하면 radius_km로 상향하되 상한 절삭.
_NEARBY_DEFAULT_RADIUS_KM = 5.0
_NEARBY_MAX_RADIUS_KM = 10.0

# 본문에 펼쳐 보여줄 상위 후보 수. 초과분은 "더보기 → /"로 안내(AC3 — 표현은 모델이 생성).
_DISPLAY_LIMIT = 3


def _rank_candidates(items: list[RoomListItem]) -> list[RoomListItem]:
    """후보를 신선 잔여 슬롯 내림차순(동률은 이름 오름차순)으로 정렬한다(표시 안정성)."""
    return sorted(items, key=lambda item: (-item.remaining_slots, item.name))


def _serialize_candidate(item: RoomListItem, *, time_filtered: bool) -> str:
    """후보 1곳을 모델 그라운딩용 블록으로 직렬화(이름·가격·룸형태·부대시설·상세 링크).

    최종 자연어 표현(상위 3 + 더보기 문장)은 모델이 프롬프트 지침으로 만들고, 툴은 **근거·링크
    데이터**만 제공한다(7.5 그라운딩 선례). 상세 링크는 공개 라우트 ``/rooms/{room_id}``다.
    """
    amenities = ", ".join(item.amenities) if item.amenities else "없음"
    lines = [
        f"- 이름: {item.name}",
        f"- 상세: /rooms/{item.room_id}",
        f"- 가격: {item.price_per_hour:,}원/시간",
        f"- 룸형태: {item.room_type}",
        f"- 부대시설: {amenities}",
    ]
    # 시간 미지정 후보는 "오늘 남은 슬롯 수"를 함께 노출(모델이 가용 강도 표현에 활용).
    if not time_filtered:
        lines.append(f"- 오늘 남은 슬롯: {item.remaining_slots}개")
    return "\n".join(lines)


def _coords_from_config(config: RunnableConfig | None) -> tuple[float, float] | None:
    """그래프 config(configurable.user_coords)에서 사용자 좌표를 안전 추출한다(없거나 형식 이상이면 None).

    좌표는 라우터→서비스→graph config로 주입된다(LLM 비노출 — 요청 스코프 DI 부재라 config 채널로
    흘린다, 함정 §툴 세션 동형). (lat, lng) 둘 다 유효 숫자일 때만 통과시킨다.
    """
    if config is None:
        return None
    coords = (config.get("configurable") or {}).get("user_coords")
    if (
        isinstance(coords, (tuple, list))
        and len(coords) == 2
        and all(isinstance(c, (int, float)) for c in coords)
    ):
        return (float(coords[0]), float(coords[1]))
    return None


@tool
def search_available_rooms(
    region: str | None = None,
    date: str | None = None,
    start_hour: int | None = None,
    near_me: bool = False,
    radius_km: float | None = None,
    *,
    config: RunnableConfig,
) -> str:
    """지역·시간 조건으로 **예약 가능한 스터디룸 후보**를 검색한다.

    사용자가 "강남 오후 3시 빈 방"처럼 **지역·시간·'빈 방'·룸 추천**을 묻거나, "내 주변 빈방"·
    "근처 스터디룸"처럼 **현재 위치 기준**(이때 ``near_me=True``)을 물으면 이 툴을 호출해 조건에
    맞는 룸 후보를 회수한다. 잡담이나 서비스 이용/규정 안내 질문에는 호출하지 않는다
    (그건 ``search_service_docs`` 담당 — 역할 분리). 반환된 후보(이름·가격·특징·상세 링크) 안에서
    답을 만들고, "그 지역은 못 찾았어요."/"조건에 맞는 빈 방을 찾지 못했어요."가 오면 지어내지
    말고 그대로 안내·재질문한다.

    Args:
        region: 자연어 지역명(예: "강남", "강남구", "역삼동"). 생략하면 지역 필터 없이 검색한다.
            ``near_me=True``면 무시된다(좌표 우선).
        date: 날짜(ISO ``YYYY-MM-DD``). 생략하면 오늘(KST) 기준. ``date``/``start_hour``가 오면
            그 시점에 실제 예약 가능한 슬롯이 있는 룸만 추린다.
        start_hour: 시작 시각(0~23, KST). 예: 오후 3시 → 15. 생략하면 그날 아무 가용 슬롯이나 있으면
            후보로 본다. 범위 밖(예: 25·-1)이면 ``INVALID_TIME`` 신호.
        near_me: 사용자가 "내 주변"·"근처"·"가까운"처럼 **현재 위치 기준**을 말하면 True. 요청에 담긴
            사용자 좌표로 반경 검색한다(기본 5km·가까운 순). 좌표가 없으면 ``LOCATION_UNAVAILABLE``
            신호(너는 위치를 직접 계산하지 마 — 의도만 True로 표시).
        radius_km: ``near_me``일 때 반경(km). 사용자가 "더 넓게"·"10km로" 요청하면 그 값을 넣어. 생략 시
            5km. **최대 10km로 제한**된다(초과 입력은 10km로 절삭 — 그 이상이면 "최대 10km까지"라고 안내).

    Returns:
        상위 후보를 이름·가격·룸형태·부대시설·상세 경로(``/rooms/{room_id}``)와 함께 직렬화한
        그라운딩 컨텍스트(3곳 초과면 "더보기 → /" 메타 포함). 지역 미해석이면 ``REGION_NOT_FOUND``,
        시간 인자가 잘못되면(파싱 불가 날짜·범위 밖 시각) ``INVALID_TIME``, 조건에 맞는 후보가
        없으면 ``NO_AVAILABLE_ROOMS``, near_me인데 위치 좌표가 없으면 ``LOCATION_UNAVAILABLE`` 신호 문자열.
    """
    # ⓪ near_me — 요청에 주입된 사용자 좌표로 반경 검색(LLM은 좌표 모름). region보다 우선한다.
    coords = _coords_from_config(config) if near_me else None
    if near_me and coords is None:
        return LOCATION_UNAVAILABLE
    radius: float | None = None
    if near_me:
        r = radius_km if (radius_km is not None and radius_km > 0) else _NEARBY_DEFAULT_RADIUS_KM
        radius = min(r, _NEARBY_MAX_RADIUS_KM)  # 최대 10km 제한(초과 절삭)

    # ① 지역 해석 — near_me가 아니고 region이 주어졌으면 코드로 변환. 미해석이면 명시 신호(AC4).
    region_code: str | None = None
    if not near_me and region is not None and region.strip():
        region_code = resolve_region(region)
        if region_code is None:
            return REGION_NOT_FOUND

    # ② 시간 조건 정규화 — date/start_hour 중 하나라도 오면 신선 슬롯으로 정합 판정(AC5). 잘못된
    # 값(파싱 불가 날짜·범위 밖 시각)은 무필터로 강등하지 않고 INVALID_TIME 신호로 즉시 반환한다
    # (조건이 사라진 무필터 결과를 "요청 시각에 맞는 것처럼" 내지 않기 — 리뷰 patch).
    target_date: _date | None = None
    if date is not None and date.strip():
        try:
            target_date = _date.fromisoformat(date.strip())
        except ValueError:
            return INVALID_TIME
    hour: int | None = None
    if start_hour is not None:
        if 0 <= start_hour <= 23:
            hour = start_hour
        else:
            return INVALID_TIME
    time_filtering = target_date is not None or hour is not None

    # ③ 단명 세션(요청 스코프 DI 부재 — 함정 §툴 세션). 필요한 값은 세션 안에서 모두 추출한다.
    # RoomListItem은 평문 값 DTO라 세션 밖 lazy 접근 위험이 없다(7.5 review 교훈).
    with Session(get_engine()) as session:
        # search_rooms가 내부적으로 reservations.service로 활성 예약을 차감(4.9 seam) — 툴은 raw
        # SQL/ORM에 직접 접근하지 않고 서비스 reader만 호출한다(AC2 도메인 경계).
        # near_me면 좌표 반경(Haversine·가까운 순), 아니면 region_code 필터(둘 다 search_rooms 단일 reader).
        if near_me and coords is not None:
            candidates = search_rooms(
                session, center_lat=coords[0], center_lng=coords[1], radius_km=radius
            )
        else:
            candidates = search_rooms(session, region_code=region_code)
        if time_filtering:
            # 시각 정합은 available_room_ids_at 벌크 reader로 룸 전체를 1회(영업시간/휴무/예약 각
            # 1쿼리)에 판정한다 — 룸별 get_room_slots N+1·버려지는 30일 루프 회피(리뷰 patch).
            day = target_date if target_date is not None else today_in_tz(ROOM_TZ)
            available_ids = available_room_ids_at(
                session, [item.room_id for item in candidates], day, hour
            )
            matched = [item for item in candidates if item.room_id in available_ids]
        else:
            # 시간 미지정 → 오늘(KST) 현재시각 이후 잔여 슬롯 ≥ 1인 룸을 가용으로 본다.
            matched = [item for item in candidates if item.remaining_slots >= 1]
        ranked = _rank_candidates(matched)
        rows = [
            _serialize_candidate(item, time_filtered=time_filtering)
            for item in ranked[:_DISPLAY_LIMIT]
        ]

    if not rows:
        return NO_AVAILABLE_ROOMS

    total = len(matched)
    header = f"예약 가능한 룸 후보 {total}곳을 찾았어요."
    body = "\n\n".join(f"[{i}]\n{row}" for i, row in enumerate(rows, start=1))
    parts = [header, body]
    if total > _DISPLAY_LIMIT:
        # 초과분 안내 — 더보기 타깃을 **그 지역으로 필터된 탐색 목록 딥링크**로 준다(KTH 2026-06-18).
        # region 이 해석됐으면 시군구 레벨(level_codes[1])로 필터된 목록(/?view=list&sigungu=...)을,
        # 지역 미지정이면 홈(/)으로. 프론트 ExploreView 가 이 쿼리로 목록 뷰 + 지역 콤보를 미리 잡는다.
        if not near_me and region_code is not None:
            sigungu_code = level_codes(region_code)[1]
            more_target = f"/?view=list&sigungu={sigungu_code}"
        else:
            # near_me(반경) 또는 지역 미지정 → 홈(지도 '내 반경')으로 더보기 안내.
            more_target = "/"
        parts.append(
            f"표시는 상위 {_DISPLAY_LIMIT}곳까지예요. "
            f"더 많은 후보는 더보기({more_target})로 안내해요."
        )
    return "\n\n".join(parts)
