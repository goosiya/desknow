# 인계 (2026-06-19 session7) — 웹↔모바일 시각 패리티 → Correct Course

## ▶ 다음 액션 (이것부터)
**`bmad-correct-course`(CC) 실행.** 입력 = 아래 audit 인벤토리. 산출 = Epic 9 정정 + 시각 패리티 정정 스토리(**9.4**).

- 입력 문서(먼저 통독): `_bmad-output/implementation-artifacts/parity-audit-web-vs-mobile-2026-06-19.md`
- 증거 스크린샷: `_bmad-output/implementation-artifacts/parity-audit-2026-06-19-shots/` (웹 `w2-*.png` / 모바일 `m1-*.png` 쌍)

## 왜 CC인가 (확정된 결정)
- Epic 9(모바일 웹 패리티)는 9.1~9.3 done 처리됐으나 **실제 웹↔모바일 시각·인터랙션이 어긋남.**
- 근본 원인: **그동안 진짜 웹앱과 대조한 적이 없었다.** :3000·:3001이 둘 다 Expo였고 Next 웹앱은 안 떠 있었음 → 과거 비교가 모바일↔모바일이라 드리프트가 안 잡힘. (이번 세션에 웹을 :3002로 세워 진짜 비교 완료.)
- KTH 승인 경로: **audit → CC**(2026-06-19). audit 단계 완료, 이제 CC.

## CC가 만들 9.4 스토리에 박을 AC
1. **화면별 웹↔모바일 스크린샷 diff 첨부·승인** — audit의 S1·S2·S3 항목을 전부 클리어.
   - S1(차단): 앱 셸 헤더(SYS-1)·인증화면 하단탭(SYS-2)·온보딩 4슬라이드 중 3개+캐러셀+"다시 보지 않기" 누락(ONB)·영업시간 시간입력(웹 네이티브 12h vs 모바일 ComboSelect 24h, ROOM-1).
   - S2: FAB 아이콘·provider 탭 순서/라벨·로그인 정렬/라벨색·룸형태 세그먼트·챗봇 입력바 위치·홈 제목 등.
   - S3: 챗봇 시트 높이·답글박스 틴트·룸상세 "‹ 뒤로".
2. **audit 미검증 인터랙션 전수**: 가입 역할토글·홈 목록/지역/반경/핀탭·룸상세 예약 플로우(진짜 웹)·예약 취소·provider 거부 2단·후기 답글 작성폼·챗봇 전송→스트리밍·즐겨찾기 해제.
3. **실기기(iOS/Android) 네이티브 재검증** — 본 audit은 웹 vs Expo Web이라 부족.

## 하니스 (9.4 구현/검증 때 필요)
- 비교 전 **포트 정체부터 확인**(둘 다 Expo일 수 있음). 방법·재기동법: 메모리 `parity-harness-web-on-3002-port-identity`.
- 웹: `pnpm -C apps/web exec next dev --port 3002` + API CORS에 `http://localhost:3002` 임시 추가(작업 후 되돌림). API 재시작은 **CWD=apps/api**.
- ⚠️ 이번 세션에 **API를 재시작했음**(원래 PID 교체). 이 세션 종료 시 내 API/웹 프로세스가 꺼질 수 있음 → 다음 세션에서 API 다운이면 재기동. CORS 소스 편집은 **이미 되돌려 committed 상태(3000/3001만)**.
- CC(계획) 단계 자체는 서버 불필요.

## 시드 계정
`booker@test.desknow` / `_pweb0@test.desknow`(룸=마포 합정) / admin `admin@desknow.kr` — 전부 `Test1234!`.
