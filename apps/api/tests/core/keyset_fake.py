"""keyset 페이징 Fake 세션 헬퍼 (F — 목록 무한스크롤 통합 테스트 공용).

라우터 통합 테스트의 Fake 세션은 ``where``/``limit``를 무시하고 전체 행을 돌려준다(기존 비페이징
검증엔 충분). 그러나 ``list_*_page`` 서비스는 ``(created_at, id) < cursor`` keyset 술어 +
``limit+1`` 로 페이지를 자르므로, **2페이지 이후가 1페이지와 같아지는** 가짜 결과가 나온다.

이 헬퍼는 컴파일된 statement에서 keyset 커서(``created_at_1``/``id_1``)와 ``limit``을 뽑아, 실제
DB와 **동일하게** 행을 ``(created_at desc, id desc)`` 정렬 → 커서 술어 필터 → ``limit`` 절단한다.
각 Fake의 ``exec``가 페이징 select를 만났을 때 이 함수로 행을 가공해 ``keyset_page``를 옳게 만든다.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any


def apply_keyset(statement: Any, rows: list[Any]) -> list[Any]:
    """페이징 select에 대해 실제 DB의 keyset 페이징 행 가공을 모사한다(정렬·커서·limit).

    - 정렬: ``created_at desc, id desc`` (서비스 order_by와 일치).
    - 커서 술어: 컴파일 파라미터에 ``created_at_1``/``id_1``이 있으면(=cursor 지정)
      ``(created_at, id) < (ts, id)`` 행만 통과(``keyset_predicate`` 전개와 동일).
    - limit: statement의 ``_limit``(=``limit+1``)만큼만 돌려준다(``keyset_page``가 +1로 더 있음 봄).

    rows의 항목은 ``created_at``·``id`` 속성을 가진다(Reservation/Favorite/Review 모두 충족).
    """
    ordered = sorted(rows, key=lambda r: (r.created_at, r.id), reverse=True)

    params = statement.compile().params
    ts = params.get("created_at_1")
    cursor_id = params.get("id_1")
    if ts is not None and cursor_id is not None:
        cursor_ts = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
        cursor_uuid = (
            cursor_id if isinstance(cursor_id, uuid.UUID) else uuid.UUID(str(cursor_id))
        )
        ordered = [
            r
            for r in ordered
            if (r.created_at < cursor_ts)
            or (r.created_at == cursor_ts and r.id < cursor_uuid)
        ]

    limit = getattr(statement, "_limit", None)
    if limit is not None:
        ordered = ordered[:limit]
    return ordered
