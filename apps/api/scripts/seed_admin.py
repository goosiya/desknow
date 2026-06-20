"""시드 관리자 계정 부트스트랩 (Story 8.1, AC3 — 멱등 수동/개발 실행 진입점).

관리자는 **가입으로 생성 불가**하다(``RegisterRequest.role``이 admin을 422 거부 — 1.8). 이
스크립트가 ``User(role="admin")``을 직접 구성하는 것이 admin 생성의 **유일한 정당 경로**다
(DB ``ck_users_role``이 'admin'을 허용). **라우터·엔드포인트가 아니다** — 1회 수동/개발 실행이다.

사용:
    python scripts/seed_admin.py           (또는 uv run python scripts/seed_admin.py)

``SEED_ADMIN_EMAIL``/``SEED_ADMIN_PASSWORD``(.env/환경변수)로 멱등 생성/갱신한다. 둘 중
하나라도 미설정/공백이면 종료 코드 1로 안내한다. 라이브 반영은 라이브 DB를 가리키는 env로
1회 실행한다(스키마 마이그레이션 아님 — 데이터 insert). 비밀번호는 절대 출력하지 않는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

# ``python scripts/seed_admin.py`` 실행 시 sys.path[0]는 scripts/라 app 패키지를 못 찾는다.
# apps/api(=parents[1])를 경로에 추가해 cwd 무관하게 import가 안정적이게 한다(ingest_docs 선례).
_API_ROOT = Path(__file__).resolve().parents[1]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from sqlmodel import Session, select  # noqa: E402  (sys.path 부트스트랩 후 import)

from app.auth.models import User  # noqa: E402
from app.core.config import _ensure_utf8_streams, get_settings, mask_secret  # noqa: E402
from app.core.db import get_engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402


def seed_admin(session: Session, email: str, password: str) -> int:
    """시드 관리자를 멱등 생성/갱신한다. 종료 코드(0=성공, 1=거부)를 반환한다.

    - **미존재:** ``role="admin"``·``is_active=True``로 생성.
    - **존재 & admin:** 비밀번호 재해싱(로테이션) + ``is_active=True`` 보장(멱등 — 중복 행 없음).
    - **존재 & 비-admin:** **권한 상승 거부**(booker/provider 이메일을 조용히 admin으로
      바꾸지 않는다 — 보안). 에러 안내 후 1 반환.
    """
    normalized = email.strip().lower()  # register/login과 동일 정규화
    existing = session.exec(select(User).where(User.email == normalized)).first()

    if existing is None:
        session.add(
            User(
                email=normalized,
                password_hash=hash_password(password),
                role="admin",
                is_active=True,
            )
        )
        session.commit()
        print(f"[OK] 시드 관리자 생성: {mask_secret(normalized)}")
        return 0

    if existing.role != "admin":
        # 권한 상승 거부 — 이미 booker/provider로 존재하는 이메일을 admin으로 둔갑시키지 않는다.
        print(
            f"[거부] 이미 '{existing.role}'(으)로 존재하는 이메일입니다: "
            f"{mask_secret(normalized)}. 다른 이메일을 쓰세요(권한 상승은 허용하지 않습니다).",
            file=sys.stderr,
        )
        return 1

    # 존재 & admin — 비밀번호 로테이션 + 활성 보장(멱등 재실행 안전).
    existing.password_hash = hash_password(password)
    existing.is_active = True
    session.add(existing)
    session.commit()
    print(f"[OK] 기존 시드 관리자 갱신(비밀번호 로테이션): {mask_secret(normalized)}")
    return 0


def main() -> int:
    # Windows cp949/리다이렉트 환경에서 한글·기호 출력 UnicodeEncodeError 방지(ingest_docs 선례).
    _ensure_utf8_streams()
    settings = get_settings()
    email = settings.SEED_ADMIN_EMAIL
    password = settings.SEED_ADMIN_PASSWORD
    if not email or not email.strip() or not password or not password.strip():
        print(
            "❌ SEED_ADMIN_EMAIL/SEED_ADMIN_PASSWORD를 .env(또는 환경변수)에 설정하세요 "
            "(시드 관리자 부트스트랩 전용 — 앱 기동과 무관).",
            file=sys.stderr,
        )
        return 1

    with Session(get_engine()) as session:
        return seed_admin(session, email, password)


if __name__ == "__main__":
    raise SystemExit(main())
