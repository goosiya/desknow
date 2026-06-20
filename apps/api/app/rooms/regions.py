"""지역 코드→이름 정적 참조 (Story 3.4 — 지역 콤보 목록 조회).

``Room.admin_dong_code``에는 **b_code(10자리 숫자)만** 저장되고(2.2 geocode
``address.b_code``), 사람이 읽는 지역명(시/군/구·동/읍/면)은 어디에도 저장되지 않는다
(2.2가 ``address_name``을 silent-drop). 이 모듈은 그 갭을 **모델·2.2·마이그레이션을
건드리지 않고** 메운다 — 보유 룸의 b_code를 정적 참조에 조인해 콤보 라벨·필터를 구성한다
(KTH 결정 #1 옵션 A — 자기완결·마이그레이션 0).

**※ 용어 = "지역"으로 통일:** 이 프로젝트의 지역 코드는 **지번 주소 b_code 기준**이다
(좌표와 함께 2.2 geocode가 저장 — 지번 기준이 더 안정적·표준). UI·코드·문서 어디서도
"행정동/법정동" 같은 표현은 쓰지 않고 모두 "지역"으로 부른다. 아래 데이터 출처 표기에만
원본 공공데이터셋의 **공식 명칭**으로 그 단어가 남는다(고유명사 — 동일 데이터셋 재확보용 보존).

**데이터 자산(``data/legal_dong.json``):** 국토교통부 **법정동코드** 공공데이터셋
(data.go.kr 15123287, 행정안전부 법정동코드 전체자료 계열 — 데이터셋 공식 명칭)을
**시도·시군구·읍면동
3레벨로 트림**한 ``code → 지역명`` 매핑이다. **리(里) 레벨·폐지(말소) 항목은 제외**한다
(존재 항목만, 전국 ~5.3천 항목). 이름은 행안부가 발행한 **전체 계층명 그대로**다
(예: ``"서울특별시 강남구 역삼동"`` — 데이터 날조 없음, 회고 ④ 실측 준수). 시군구 이름은
시도명을 포함해 동명 시군구 모호성을 없앤다(예: ``"서울특별시 강남구"``).

**import 부작용 = 순수 데이터 로드만**(DB/``get_settings`` 미접근) — ``test_main`` 모듈레벨
``TestClient`` 불변식과 ``export_openapi`` 안전성을 보존한다(1.4/1.8 패턴).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import cast

# b_code 10자리 = 시도(2) + 시군구(3) + 읍면동(3) + 리(2). 레벨 코드는 트레일링 0으로 만든다:
#   시도   = XX00000000 (앞 2자리 + 0×8)
#   시군구 = XXXXX00000 (앞 5자리 + 0×5)
#   읍면동 = XXXXXXXX00 (앞 8자리 + 0×2)
_BCODE_LENGTH = 10
_SIDO_DIGITS = 2
_SIGUNGU_DIGITS = 5
_EUPMYEONDONG_DIGITS = 8

# 데이터 번들은 모듈 옆 data/ 에 둔다. importlib.resources 대신 모듈 상대 경로로 1회 로드한다
# (순수 파일 읽기 — DB/settings 미접근). UTF-8 한글(회고 ① CP949 함정 회피).
_DATA_PATH = Path(__file__).parent / "data" / "legal_dong.json"


def _load_bundle() -> dict[str, str]:
    """지역 코드→이름 번들을 1회 로드한다(모듈 import 시점, 순수 데이터)."""
    with _DATA_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    # 키·값이 모두 문자열인 평면 dict(code → 지역명). 자기 소유 데이터 자산이라 런타임 타입
    # 방어 없이 신뢰하고, json.load의 Any를 선언 타입으로 좁힌다(mypy no-any-return).
    return cast(dict[str, str], data)


# 모듈레벨 상수 — import 시 1회 로드해 조회를 O(1) dict 룩업으로 만든다(요청마다 파일 IO 0).
_LEGAL_DONG: dict[str, str] = _load_bundle()


def _pad(prefix: str) -> str:
    """앞자리 prefix를 트레일링 0으로 10자리 레벨 코드로 만든다."""
    return prefix.ljust(_BCODE_LENGTH, "0")


def level_codes(b_code: str) -> tuple[str, str, str]:
    """지역 b_code에서 (시도·시군구·읍면동) 레벨 코드를 도출한다.

    각 레벨 코드는 해당 자릿수까지 보존하고 나머지를 0으로 채운 10자리다. 룸의 b_code를
    이 코드들로 환산해 콤보 그룹핑·지역 필터 동등 매칭에 쓴다.

    예: ``"1168010100"``(역삼동) → (``"1100000000"`` 서울, ``"1168000000"`` 강남구,
        ``"1168010100"`` 역삼동).

    b_code가 10자리가 아니어도(손상 데이터) 슬라이스는 안전하다 — 짧으면 그만큼만 보존된다.
    """
    return (
        _pad(b_code[:_SIDO_DIGITS]),
        _pad(b_code[:_SIGUNGU_DIGITS]),
        _pad(b_code[:_EUPMYEONDONG_DIGITS]),
    )


def region_name(code: str) -> str | None:
    """레벨 코드의 지역명을 번들에서 조회한다. 미매핑이면 ``None``(소비처가 graceful 폴백).

    반환은 행안부 전체 계층명이다(시군구=``"서울특별시 강남구"``, 동=``"서울특별시 강남구
    역삼동"``). 동 단위 짧은 라벨이 필요한 콤보는 ``leaf_name``으로 마지막 토큰을 취한다.
    번들에 없는 코드(행정구역 개편·번들 갱신 지연·손상 b_code)는 ``None``을 돌려주고,
    서비스가 코드 원문 또는 "(지역 미상)"으로 표시한다(3.3 미지정 amenity 폴백 선례 — 조용한
    크래시 금지).
    """
    return _LEGAL_DONG.get(code)


def leaf_name(full_name: str) -> str:
    """전체 계층명에서 말단(동/읍/면) 토큰만 취한다(콤보 2차 옵션 짧은 라벨).

    ``"서울특별시 강남구 역삼동"`` → ``"역삼동"``. 지역명은 공백으로 계층을 연결하고
    말단(동/읍/면)은 공백 없는 단일 토큰이라 마지막 토큰이 곧 동 이름이다. 빈 문자열이면
    그대로 빈 문자열을 돌려준다(방어).
    """
    return full_name.rsplit(" ", 1)[-1] if full_name else full_name


# ── 지역명 → 코드 역해석(Story 7.6 — 챗봇 예약검색 지역 인자) ──
# 시군구 접미사(자치구=구·군·시·일반구=구). '강남구' 외에 '강남'처럼 접미사 생략 입력도
# 같은 코드로 잡기 위해 역인덱스에 접미사 제거 변형을 함께 등록한다.
_SIGUNGU_SUFFIXES = ("구", "군", "시")

# 세종처럼 시군구 하위레벨이 없어 '시' 이름 자체가 시군구 레벨로 들어오는 특별 케이스용 복합
# 접미사(긴 것 우선 매칭). '세종특별자치시' → 별칭 '세종'·'세종시'를 등록해 자연어 입력을 잡는다
# (단일 접미사 '시'만 떼면 '세종특별자치'가 돼 '세종'/'세종시'를 영영 못 잡는 갭 — 리뷰 patch).
_CITY_SUFFIXES = ("특별자치시", "특별자치도", "광역시", "특별시", "자치시", "자치도")


def _is_sigungu(code: str) -> bool:
    """시군구 레벨 코드(앞 5자리 중 시군구부 유효 + 뒤 5자리 0)인지(시도 레벨 제외)."""
    return (
        code[_SIDO_DIGITS:_SIGUNGU_DIGITS] != "000"
        and code[_SIGUNGU_DIGITS:] == "00000"
    )


def _is_dong(code: str) -> bool:
    """읍면동 레벨 코드(읍면동부 유효 + 뒤 2자리 0)인지(시군구 레벨 제외)."""
    return (
        code[_SIGUNGU_DIGITS:_EUPMYEONDONG_DIGITS] != "000"
        and code[_EUPMYEONDONG_DIGITS:] == "00"
    )


def _sigungu_aliases(leaf: str) -> list[str]:
    """시군구 말단명에서 접미사 생략/구어 별칭을 만든다(역인덱스 추가 등록용).

    일반 시군구는 '구/군/시' 접미사를 떼어 '강남구'→'강남'을 추가한다. 세종처럼 '특별자치시'
    등 복합 접미사로 끝나는 단일레벨 시는 베이스('세종')와 구어형('세종시')을 함께 만들어,
    '세종'·'세종시' 자연어 입력이 해석되게 한다(단일 '시'만 떼면 '세종특별자치'가 돼 못 잡음).
    """
    for suffix in _CITY_SUFFIXES:
        if leaf.endswith(suffix) and len(leaf) > len(suffix):
            base = leaf[: -len(suffix)]
            return [base, base + "시"]  # '세종' + 구어형 '세종시'
    for suffix in _SIGUNGU_SUFFIXES:
        if leaf.endswith(suffix) and len(leaf) > 1:
            return [leaf[: -len(suffix)]]  # '강남구' → '강남'
    return []


def _build_reverse_index() -> tuple[dict[str, str | None], dict[str, str | None]]:
    """``_LEGAL_DONG``(code→이름)에서 이름→코드 역인덱스를 import 시점 1회 구성한다.

    시군구·읍면동 두 레벨을 분리한 dict를 만든다(말단 토큰 → 코드). 같은 말단명이 여러 코드에
    걸리면(동명 시군구 '중구' 등) **모호 표식 ``None``**을 넣어, 해석 시 조용한 오답 대신 미해석
    신호로 떨어지게 한다(데이터 날조·환각 금지 — 회고 ④). 순수 데이터 가공만 한다(DB/IO 0).
    """
    sigungu: dict[str, str | None] = {}
    dong: dict[str, str | None] = {}

    def _add(index: dict[str, str | None], name: str, code: str) -> None:
        # 이미 다른 코드가 들어 있으면 모호(None) 표식, 같은 코드 재등록이면 그대로 둔다.
        if name in index and index[name] != code:
            index[name] = None
        elif name not in index:
            index[name] = code

    for code, full_name in _LEGAL_DONG.items():
        leaf = leaf_name(full_name)
        if not leaf:
            continue
        if _is_sigungu(code):
            _add(sigungu, leaf, code)
            # 접미사 생략/구어 별칭('강남구'→'강남', '세종특별자치시'→'세종'·'세종시')도 등록 —
            # 다른 시군구와 겹치면 _add가 모호 처리.
            for alias in _sigungu_aliases(leaf):
                _add(sigungu, alias, code)
        elif _is_dong(code):
            _add(dong, leaf, code)
    return sigungu, dong


# 모듈레벨 역인덱스 — import 시 1회 구성(요청마다 재구성 0). 값이 None이면 모호 매칭.
_SIGUNGU_BY_NAME, _DONG_BY_NAME = _build_reverse_index()


def _lookup(token: str) -> str | None:
    """정규화된 단일 토큰을 **시군구 우선·동 보조**로 해석한다(모호/미매핑이면 ``None``).

    ★시군구 모호(None) 폴백: ``in`` 검사는 "모호"와 "부재"를 구분 못 하므로, 모호 시군구
    토큰이 명확한 동(洞)일 수 있는 경우 동 폴백에 도달하도록 ``.get``으로 값을 확인한다
    (모호 시군구라 해서 동 매칭을 단락시키지 않음 — 리뷰 patch).
    """
    if not token:
        return None
    sigungu_code = _SIGUNGU_BY_NAME.get(token)
    if sigungu_code is not None:
        return sigungu_code  # 단일 매칭 시군구
    return _DONG_BY_NAME.get(token)  # 모호 시군구/미등록이면 동 보조(없으면 None)


def resolve_region(name: str) -> str | None:
    """자연어 지역명을 지역 코드(시군구/읍면동 레벨)로 해석한다(미해석/모호면 ``None``).

    챗봇 예약검색 툴(7.6)이 "강남"·"강남구"·"역삼동" 같은 지역 토큰을 ``search_rooms`` 의
    ``region_code`` 로 넘기기 위한 역방향 변환이다. 매칭 규칙(MVP, 결정적):

    - 입력을 정규화(앞뒤·내부 공백 제거)한 뒤 **① 시군구 레벨 우선**으로 찾고, 없으면
      **② 읍면동 레벨**로 보조 매칭한다.
    - 시군구는 말단 토큰('강남구')과 접미사 생략형('강남'), 단일레벨시 별칭('세종'/'세종시')을
      모두 인식한다.
    - **다중 토큰**('강남 역삼동')은 무구분 연결로는 안 잡히므로 마지막 토큰('역삼동')으로
      보조 해석한다(더 구체적인 동/시군구 우선 — 리뷰 patch).
    - 동명 시군구('중구' 등)처럼 **모호하거나 미매핑이면 ``None``** — 조용한 빈 결과로 오인하지
      않게 소비처(툴)가 "그 지역은 못 찾았어요." 신호로 처리한다(``region_name`` graceful 정신).

    반환 코드는 ``level_codes`` 가 도출하는 시군구(``XXXXX00000``)·동(``XXXXXXXX00``) 레벨과
    정합하므로 ``search_rooms`` 의 동등 매칭에 그대로 쓰인다.
    """
    collapsed = "".join(name.split())  # 앞뒤+내부 공백 제거 정규화
    code = _lookup(collapsed)
    if code is not None:
        return code
    # 다중 토큰 보조 — '강남 역삼동'처럼 공백으로 갈린 입력은 연결형이 안 잡히므로 마지막
    # 토큰으로 한 번 더 시도한다(단일 토큰이면 parts 길이 1 → 위에서 이미 끝).
    parts = name.split()
    if len(parts) > 1:
        return _lookup(parts[-1])
    return None
