"""rooms Haversine 거리 순수 함수 테스트 (Story 3.5 — 반경 검색 AC1·AC4).

``haversine_km`` 은 순수 함수라 라이브 DB·Fake 없이 입력→출력을 직접 단언한다
(``derive_slots`` 테스트 정신 계승). 부동소수 근사라 알려진 거리는 허용 오차로 비교한다.
"""
from __future__ import annotations

import math

from app.rooms.geo import haversine_km

# 안정적 표준 좌표(서울).
SEOUL_CITY_HALL = (37.5665, 126.9780)  # 서울시청
GANGNAM_STATION = (37.4979, 127.0276)  # 강남역


def test_identical_coords_is_zero() -> None:
    """동일 좌표 사이 거리는 0(자기 자신)."""
    lat, lng = SEOUL_CITY_HALL
    assert haversine_km(lat, lng, lat, lng) == 0.0


def test_symmetry_a_to_b_equals_b_to_a() -> None:
    """대칭성: a→b 거리 == b→a 거리(인자 순서 무관)."""
    a_lat, a_lng = SEOUL_CITY_HALL
    b_lat, b_lng = GANGNAM_STATION
    d1 = haversine_km(a_lat, a_lng, b_lat, b_lng)
    d2 = haversine_km(b_lat, b_lng, a_lat, a_lng)
    assert math.isclose(d1, d2, rel_tol=1e-12)


def test_known_distance_seoul_cityhall_to_gangnam() -> None:
    """서울시청↔강남역 ≈ 8~9km(알려진 근사 — 구면 오차 허용)."""
    a_lat, a_lng = SEOUL_CITY_HALL
    b_lat, b_lng = GANGNAM_STATION
    dist = haversine_km(a_lat, a_lng, b_lat, b_lng)
    # 실제 직선거리 ~8.4km. 구면 근사 허용범위로 단언.
    assert 8.0 <= dist <= 9.0


def test_one_degree_latitude_is_about_111km() -> None:
    """위도 1도 차이 ≈ 111km(자오선 1도 ≈ 지구둘레/360). 적도 부근 경도 무관 단순 케이스."""
    dist = haversine_km(0.0, 0.0, 1.0, 0.0)
    assert math.isclose(dist, 111.19, abs_tol=0.5)


def test_returns_nonnegative_float() -> None:
    """반환값은 음이 아닌 float."""
    dist = haversine_km(37.5, 127.0, 35.1, 129.0)  # 서울↔부산 근처
    assert isinstance(dist, float)
    assert dist > 0
