"""지역 코드→이름 참조 테스트 (Story 3.4 — Task 1).

``regions.py``는 순수 모듈(DB/settings 미접근)이라 입력→출력을 직접 단언한다. 번들
(``data/legal_dong.json``)은 실데이터(국토부 지역코드)라, 안정적인 표준 코드 몇 개로
매핑 적중·미매핑 ``None``·폴백·레벨 코드 슬라이스를 검증한다.
"""
from __future__ import annotations

from app.rooms.regions import (
    leaf_name,
    level_codes,
    region_name,
    resolve_region,
)


def test_level_codes_slices_with_trailing_zeros() -> None:
    """역삼동 1168010100 → 시도 1100000000·시군구 1168000000·동 1168010100(b_code 2/3/3/2)."""
    sido, sigungu, dong = level_codes("1168010100")
    assert sido == "1100000000"  # 시도(앞 2) + 0×8
    assert sigungu == "1168000000"  # 시군구(앞 5) + 0×5
    assert dong == "1168010100"  # 읍면동(앞 8) + 0×2 (이미 트레일링 00)


def test_level_codes_jongno_chungun() -> None:
    """청운동 1111010100 → 종로구 1111000000·동 1111010100(다른 시군구 슬라이스 확인)."""
    sido, sigungu, dong = level_codes("1111010100")
    assert sido == "1100000000"
    assert sigungu == "1111000000"
    assert dong == "1111010100"


def test_region_name_maps_known_codes() -> None:
    """번들 매핑 적중 — 시도/시군구/동 3레벨 전체명(시군구는 시도 포함)."""
    assert region_name("1100000000") == "서울특별시"
    assert region_name("1168000000") == "서울특별시 강남구"
    assert region_name("1168010100") == "서울특별시 강남구 역삼동"


def test_region_name_unmapped_is_none() -> None:
    """미매핑 코드(존재하지 않는/리 레벨/개편)는 None(소비처가 graceful 폴백)."""
    assert region_name("9999999999") is None
    assert region_name("1168010101") is None  # 리 레벨(번들 제외)


def test_leaf_name_takes_last_token() -> None:
    """동 짧은 라벨 = 전체명 말단 토큰(콤보 2차 옵션)."""
    assert leaf_name("서울특별시 강남구 역삼동") == "역삼동"
    assert leaf_name("경기도 수원시 장안구 파장동") == "파장동"  # 일반구 4레벨도 말단만


def test_leaf_name_single_token_and_empty() -> None:
    """공백 없는 단일 토큰·빈 문자열은 그대로(방어)."""
    assert leaf_name("서울특별시") == "서울특별시"
    assert leaf_name("") == ""


def test_bundle_excludes_ri_and_includes_three_levels() -> None:
    """번들은 시도·시군구·동 3레벨을 담고 리(里)는 제외한다(데이터 자산 충실도)."""
    # 세종(시군구 없는 특별시) — 시도 레벨 존재.
    assert region_name("3611000000") == "세종특별자치시"
    # 제주 서귀포시(시군구 레벨), 일반구 포함 시군구.
    assert region_name("5013000000") == "제주특별자치도 서귀포시"
    assert region_name("4111100000") == "경기도 수원시 장안구"


# ── 지역명 → 지역 코드 역해석(Story 7.6 — Task 1, 챗봇 예약검색 지역 인자) ──
def test_resolve_region_sigungu_full_and_stripped() -> None:
    """시군구 우선 매칭 — '강남구'(전체 말단)·'강남'(접미사 생략) 모두 같은 시군구 코드."""
    assert resolve_region("강남구") == "1168000000"
    assert resolve_region("강남") == "1168000000"


def test_resolve_region_dong_secondary() -> None:
    """읍면동 보조 매칭 — '역삼동' → 그 동 코드(번들 유일 매칭)."""
    assert resolve_region("역삼동") == "1168010100"


def test_resolve_region_strips_whitespace() -> None:
    """입력 정규화 — 앞뒤/내부 공백을 제거해도 동일 매칭."""
    assert resolve_region(" 강남구 ") == "1168000000"


def test_resolve_region_ambiguous_is_none() -> None:
    """동명 시군구(중구는 서울·부산 등 6곳)는 모호 → None(조용한 오답 금지)."""
    assert resolve_region("중구") is None


def test_resolve_region_unmapped_is_none() -> None:
    """미매핑·빈 입력은 None(소비처가 '그 지역은 못 찾았어요.' 신호로 처리)."""
    assert resolve_region("없는동네") is None
    assert resolve_region("") is None
    assert resolve_region("   ") is None


def test_resolve_region_sejong_single_level_city() -> None:
    """세종은 시군구 하위레벨이 없어 '시' 이름이 시군구 레벨 — '세종'·'세종시'·전체명 모두 해석
    (단일 '시' 접미사만 떼면 '세종특별자치'가 돼 못 잡던 갭 — 리뷰 patch)."""
    assert resolve_region("세종") == "3611000000"
    assert resolve_region("세종시") == "3611000000"
    assert resolve_region("세종특별자치시") == "3611000000"


def test_resolve_region_multi_token_last_token() -> None:
    """다중 토큰 입력은 마지막 토큰으로 보조 해석 — '강남 역삼동'→역삼동, '서울 강남구'→강남구
    (무구분 연결로는 안 잡히던 갭 — 리뷰 patch)."""
    assert resolve_region("강남 역삼동") == "1168010100"
    assert resolve_region("서울 강남구") == "1168000000"
