"""``app.openapi()`` → ``packages/api-client/openapi.json`` 오프라인 export (Story 1.9).

백엔드 OpenAPI 계약을 **결정적(deterministic)** JSON으로 직렬화해 SDK 생성기
(``@hey-api/openapi-ts``)의 입력으로 커밋한다.

- **``.env``/DB 불필요:** ``app.main`` import는 ``lifespan``(startup)을 실행하지 않으므로
  ``get_settings()``/``verify_db_connection()``이 트리거되지 않는다(``test_main``의 모듈 레벨
  ``TestClient`` 패턴과 동일 근거). → 어떤 환경에서도 안전하게 스키마만 뽑는다.
- **결정성:** ``sort_keys=True`` + 고정 ``indent`` + 끝 개행으로 dict 순서 비결정성을 제거한다.
  Layer A 드리프트 테스트(``test_openapi_export.py``)가 ``serialize_openapi()``를 **재사용**해
  커밋본과 1:1 비교한다 → 직렬화 로직은 반드시 이 단일 소스로 통일한다.

사용:
    uv run python scripts/export_openapi.py [출력경로]
기본 출력: ``<repo>/packages/api-client/openapi.json``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# ``python scripts/export_openapi.py`` 실행 시 sys.path[0]는 ``scripts/``라 ``app`` 패키지를
# 찾지 못한다. apps/api(=parents[1])를 경로에 추가해 cwd와 무관하게 import가 안정적이게 한다.
_API_ROOT = Path(__file__).resolve().parents[1]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.main import app  # noqa: E402  (sys.path 부트스트랩 후 import해야 함)

# 저장소 루트: apps/api/scripts/export_openapi.py → parents[3] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = _REPO_ROOT / "packages" / "api-client" / "openapi.json"


def serialize_openapi() -> str:
    """``app.openapi()``를 결정적 문자열로 직렬화한다(sort_keys + 고정 indent + 끝 개행).

    Layer A 드리프트 테스트가 동일 함수를 재사용하므로 직렬화 규칙 변경은 여기 한 곳만 고친다.
    """
    schema = app.openapi()
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    output = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n"로 OS 무관 LF를 강제한다(Windows write_text 기본 텍스트모드는 \n→\r\n 변환).
    # serialize_openapi()는 LF만 내보내므로, 이 인자가 없으면 커밋본이 환경마다 다른 개행을
    # 갖게 돼 "바이트 단위 결정성"이 깨진다(Layer A read_text 정규화가 그 차이를 가린다).
    output.write_text(serialize_openapi(), encoding="utf-8", newline="\n")
    print(f"OpenAPI 스키마 export 완료 → {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
