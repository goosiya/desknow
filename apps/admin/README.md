# desknow-admin

DeskNow **운영(시드 관리자) 웹 콘솔** (Next.js, App Router). 사용자 웹(`apps/web`)과 **분리된
별도 환경**으로 공격 표면을 격리합니다. 관리자 권한은 백엔드(`require_role("admin")`)가 최종
강제하며, 프론트의 역할 게이트는 보조입니다.

## 로컬 실행

```bash
pnpm --filter admin dev      # http://localhost:3001
```

- `NEXT_PUBLIC_API_BASE_URL` (`.env.local`): 백엔드 **origin만**(기본 `http://localhost:8000`).
  경로 `/api/v1/...`는 생성 SDK(`@desknow/api-client`)에 포함되므로 붙이지 않습니다.
- 인증은 httpOnly 쿠키(`desknow_access`)로 유지되며, SDK 클라이언트가 크로스오리진
  (3001→8000) 쿠키를 동봉하도록 `credentials:"include"`로 설정돼 있습니다.

## 로그인

**시드 관리자 계정**으로만 로그인합니다(가입·계정 생성 UI 없음 — admin은 시드 전용). 시드 계정은
백엔드 `apps/api/scripts/seed_admin.py`로 부트스트랩합니다(`SEED_ADMIN_EMAIL`/`SEED_ADMIN_PASSWORD`).
booker/provider 계정으로 로그인하면 "관리자 권한이 없습니다" 안내 후 즉시 로그아웃됩니다.

## 운영 화면

- **`/accounts` — 계정 관리**: 예약자·제공자 계정 목록(실데이터, 페이지네이션). *Story 8.1.*
- **`/reservations` — 예약 임의취소**: 준비 중. *Story 8.3.*
- **`/ingest` — 챗봇 인제스트**: 준비 중. *Story 8.4.*

## 테스트 / 검사

```bash
pnpm --filter admin test          # vitest
pnpm --filter admin lint
pnpm --filter admin check-types
pnpm --filter admin build
```
