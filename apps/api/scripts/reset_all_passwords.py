"""users 테이블 전 계정 비밀번호를 ``Test1234!`` 로 일괄 재설정한다(admin 포함, dev 전용 유틸).

KTH 요청(2026-06-19): dev Supabase의 시드/테스트 계정 로그인 401(비번 불일치)을 해소하기 위해
모든 사용자 비밀번호를 통일한다. **앱과 동일한 해셔**(``app.core.security.hash_password`` = pwdlib
Argon2)로 해시를 만들어야 로그인(``verify_password``)이 정상 동작한다.

실행: ``uv run --no-sync python scripts/reset_all_passwords.py``
(API 서버 실행 중이면 ``--no-sync`` 필수 — 잠긴 .pyd 손상 방지.)
"""
from __future__ import annotations

import sys
from pathlib import Path

# scripts/ 에서 직접 실행 시 app 패키지를 찾도록 저장소 루트(apps/api)를 path 에 추가한다
# (export_openapi.py 선례).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session, select  # noqa: E402

from app.auth.models import User  # noqa: E402
from app.core.db import get_engine  # noqa: E402
from app.core.security import hash_password, verify_password  # noqa: E402

NEW_PASSWORD = "Test1234!"


def main() -> None:
    engine = get_engine()
    host = engine.url.host or "(unknown)"
    print(f"대상 DB host: {host}")

    # 동일 비밀번호라도 솔트가 달라 계정마다 다른 해시를 부여한다(평문 통일·해시는 분산).
    with Session(engine) as session:
        users = list(session.exec(select(User)).all())
        print(f"대상 계정 수: {len(users)}")
        for user in users:
            user.password_hash = hash_password(NEW_PASSWORD)
            session.add(user)
        session.commit()

        # 검증: 갱신 후 다시 읽어 verify_password 가 새 비번을 통과하는지 표본 확인.
        refreshed = list(session.exec(select(User)).all())
        ok = sum(
            1 for u in refreshed if verify_password(NEW_PASSWORD, u.password_hash)
        )
        print(f"검증: {ok}/{len(refreshed)} 계정이 새 비밀번호로 verify 통과")
        roles: dict[str, int] = {}
        for u in refreshed:
            roles[u.role] = roles.get(u.role, 0) + 1
        print(f"역할별 분포: {roles}")
        admin = next((u for u in refreshed if u.role == "admin"), None)
        if admin is not None:
            print(
                f"admin({admin.email}) verify: "
                f"{verify_password(NEW_PASSWORD, admin.password_hash)}"
            )


if __name__ == "__main__":
    main()
