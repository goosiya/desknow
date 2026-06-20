"""Layer A 드리프트 게이트: ``app.openapi()`` ↔ 커밋된 ``openapi.json`` 일치 (Story 1.9, AC3).

백엔드 계약(코드)이 바뀌었는데 ``packages/api-client/openapi.json``을 재생성하지 않으면 이
테스트가 실패해 계약-SDK 체인의 첫 단계 드리프트를 차단한다(이어서 Layer B가 json→SDK를 잡음).

- 직렬화는 export 스크립트의 ``serialize_openapi()``를 **재사용**한다 → 비교 규칙 단일 소스.
- DB/.env 무관: ``scripts.export_openapi`` import는 ``app.main``을 끌어오지만 ``lifespan``을
  실행하지 않으므로 환경 검증이 트리거되지 않는다(``test_main``과 동일 import-안전 근거).
"""
from __future__ import annotations

from scripts.export_openapi import DEFAULT_OUTPUT, serialize_openapi


def test_committed_openapi_matches_app() -> None:
    """커밋된 openapi.json이 현재 app.openapi() 출력과 바이트 단위로 일치한다."""
    assert DEFAULT_OUTPUT.exists(), (
        f"{DEFAULT_OUTPUT} 없음 — `uv run python scripts/export_openapi.py` 실행 필요."
    )
    expected = serialize_openapi()
    actual = DEFAULT_OUTPUT.read_text(encoding="utf-8")
    assert actual == expected, (
        "커밋된 openapi.json이 app.openapi()와 불일치 — 백엔드 계약 변경 후 재생성 누락. "
        "`uv run python scripts/export_openapi.py`를 재실행하고 이어서 "
        "`pnpm --filter @desknow/api-client generate`로 SDK도 재생성하라."
    )
