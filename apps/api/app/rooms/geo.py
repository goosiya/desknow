"""rooms 공간 거리 순수 함수: Haversine 대권 거리 (Story 3.5 — 반경 검색).

반경 검색의 공간 필터는 **Haversine(구면 근사)** 으로 한다 — PostGIS 가 아니다
(architecture.md L151-152: "반경 = PostGIS ST_DWithin **또는** Haversine, MVP 규모는
후자도 충분"). ``Room.lat``/``Room.lng`` 는 일반 float 컬럼이고 PostGIS 확장·geometry
컬럼·공간 인덱스가 없으므로(도입 시 마이그레이션·확장 프로비저닝 필요), MVP 는 좌표를
인-메모리로 받아 거리를 계산하고 ``service.search_rooms`` 가 Python 에서 필터·정렬한다.

**이 모듈은 순수하다** — DB/``get_settings``/외부 호출 0, import 시점 부작용 0
(``regions.py``/``derive_slots`` 와 동형). 신규 백엔드 의존성 0(거리 계산은 stdlib
``math`` 만 사용). ``test_main`` 의 모듈레벨 ``TestClient`` 불변식(import 시 DB/settings
미접근)을 깨지 않는다.

SQL 공간쿼리/PostGIS 공간 인덱스 최적화는 ``search_rooms`` 의 region Python 필터와
동일 계열의 **deferred**(데이터 증가 시점 — bbox 계열, deferred-work.md).
"""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

# 지구 평균 반경(km). 구면 근사(타원체 아님) — MVP 반경 검색에 충분한 정밀도.
_EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표(십진 위경도, 도) 사이의 대권 거리를 km 로 반환한다(Story 3.5).

    Haversine 공식으로 구면 위 두 점의 최단(대권) 거리를 계산한다. 입력은 **십진
    위경도(도 단위)** 이고 출력은 **km** 다. 지구를 반지름 ``_EARTH_RADIUS_KM``(6371km)
    의 완전 구로 근사한다(타원체 아님) — 반경 검색(기본 3km) 규모에서 오차는 무시할
    수준이라 MVP 에 충분하다(정밀 측지 거리는 후속 deferred).

    Args:
        lat1: 점1 위도(도, [-90, 90]).
        lng1: 점1 경도(도, [-180, 180]).
        lat2: 점2 위도(도).
        lng2: 점2 경도(도).

    Returns:
        두 점 사이의 대권 거리(km, 음이 아닌 float). 동일 좌표면 0.0. 인자 순서를
        바꿔도 같은 값(대칭).
    """
    # 위경도를 라디안으로 변환 후 위도/경도 차이를 구한다.
    phi1 = radians(lat1)
    phi2 = radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lng2 - lng1)

    # Haversine: a = sin²(Δφ/2) + cosφ1·cosφ2·sin²(Δλ/2), 거리 = 2R·asin(√a).
    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    # 대척점 근처(a≈1)에서 부동소수 오차로 sqrt(a)가 1을 미세하게 초과하면 asin이 math
    # domain error(ValueError)를 던진다. 반경 검색(≤50km)에선 a가 1 근처로 안 가지만, 순수
    # 함수 재사용(장거리) 대비 [0,1]로 클램프한다(code-review 2026-06-16).
    return 2 * _EARTH_RADIUS_KM * asin(min(1.0, sqrt(a)))
