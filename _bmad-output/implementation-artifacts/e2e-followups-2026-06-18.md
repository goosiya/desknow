# E2E 완성도 점검 — 미완 항목 핸드오프 (2026-06-18)

브라우저 직접 구동으로 사용자·관리자 전 영역을 점검하며 수정한 뒤 **남은 작업**을 정리한 문서.
다음 세션에서 이 문서로 이어받는다. 테스트 계정·시드·세션주입 패턴은 메모리 [[e2e-seed-accounts-and-data]] 참조.

## 이번 세션에서 완료된 것 (참고)
- 백엔드 `create_room` FK 순서 버그 수정(`app/rooms/service.py` `session.flush()`), 웹 로그인/회원가입 UI 신규 구축,
  채팅 로그아웃 게이팅, FAB 위치, 하이드레이션 경고, admin stale 문구, 모바일 localhost 폴백 `__DEV__` 게이팅·console.log 제거.
- 검증 완료: 가입→로그인→로그아웃, 예약 POST 201, 채팅 RAG, admin 로그인·목록 페이지.
- 임시 드라이버: `D:\dev\tmp\pw-drive\` (playwright-core + 시스템 Chrome). 재사용 가능.

---

## 이어받은 세션 진행 (2026-06-18 후속) — 브라우저 직접 구동(Playwright MCP)

**검증·구동 방식 전환:** 이 세션부터 **Playwright MCP**(`.mcp.json`에 `npx @playwright/mcp@latest --browser chrome` 등록, 승인 필요)로 브라우저를 직접 클릭/입력/캡처하며 검증한다. pw-drive 스크립트는 보조.

### ✅ 완료 (C·B 전부 + UX 수정 다수)
- **C① create_room FK 회귀** — 게이트 통합테스트 추가(`tests/integration/test_rooms_migration.py::test_create_room_service_fk_ordering_roundtrip`) + dev Supabase throwaway provider로 라이브 검증(자가정리).
- **C② 채팅 401 mid-session refresh 재시도** — `streamMessage.ts`에 401→`authRefresh`→스트림 1회 재시도. 브라우저 검증(쿠키 삭제→회복). 단위 3건.
- **C③ 채팅 로그아웃 게이팅 유닛 테스트** — `ChatbotPanel.test.tsx` 미로그인 분기 2건.
- **B 전부 브라우저 검증** — 챗봇 자연어 예약검색 / 후기 작성(→"후기 완료"·상세 반영) / booker 예약 취소(+슬롯 재오픈) / 카카오 공유(graceful 폴백) / 행정동 콤보 목록 진입.
- **UX 수정(브라우저 검증 완료):**
  - 상세 중복 "예약하기" → 상단 토글을 **"예약 가능 시간 보기"**로(확정 버튼만 "예약하기").
  - 예약현황 **종료(이용 완료) 예약 공유 버튼 제거**(다가오는 확정만 공유).
  - **예약 취소 시 도래 알림 배너 제거** — `useCancelReservation`이 `["notifications"]` 미무효화하던 것 추가.
  - **"마감" → "오늘 마감"**(상세·시트·목록·즐겨찾기·핀 라벨 일관).
  - **세션 슬라이딩 연장 + 만료 안내/리다이렉트** — `SessionKeeper`(활동 10분 주기 `authRefresh`, capture 단계라 챗봇 등 오버레이 인터랙션도 연장) + 만료 시 `/login?expired=1&next=` + 안내, 수동 로그아웃 제외(`sessionExpiry`).
  - **챗봇 자동 스크롤** — 스트리밍 하단 추적 + 오픈 시 하단(`onOpenAutoFocus` preventDefault + 입력 포커스).
  - **챗봇 룸 링크** — `[상세보기](/rooms/…)`/`[더보기](/)` 를 **라벨만 링크, URL 숨김**(마크다운 링크 파싱, 화이트리스트 유지).
  - **챗봇 반말 → 해요체**(프롬프트 강화) · **현재 KST 날짜 주입**(`build_system_prompt` — "내일/19일" 정확 환산: LLM이 오늘 날짜를 몰라 과거로 추측 → 빈결과 버그였음).
  - **챗봇 "더보기" 딥링크** — 툴이 `/?view=list&sigungu={코드}` 반환 → 프롬프트가 그대로 사용 → `ExploreView`가 URL 파라미터로 목록 뷰 + 지역 콤보 선필터(useState 초기화 + searchParams 변화 effect). 화이트리스트·`page.tsx` Suspense 동반.
  - **스켈레톤 오렌지 깜빡임 2건** — (1) `Skeleton`이 `bg-accent`(만다린 오렌지 #FFC24D) 쓰던 것 `bg-muted`로(앱 전역), (2) 새로고침마다 5행 깜빡 → `useDeferredFlag`로 **지연 표시**(빠른 로딩엔 스켈레톤 0).
- **모바일 일괄 개발 결정** 기록 — [[mobile-build-all-at-once-after-web]].

### ⏳ 남음 (다음 세션 인계)
- **A. admin 변이 검증**(아래 A 섹션) — throwaway 계정 필요.
- **E. 경미**(아래 E 섹션).
- **F. 목록 페이징/무한스크롤**(신규 — 아래 F 섹션).

### 🧪 테스트 데이터 (보존 — KTH 지시)
- dev Supabase에 **강남(역삼 1168010100) throwaway 룸 12개 + provider 12명** 등록(이메일 프리픽스 `_disptest_`, 룸명 "강남 테스트룸 1~12"). **정리하지 말 것**(KTH가 계속 테스트). 시드/정리 스크립트: `D:\dev\tmp\seed_gangnam_rooms.py`(인자 `clean`으로 일괄 삭제 — 지금은 실행 금지).
- **모든 테스트 provider/룸 비밀번호 = `Test1234!`** (시드 계정도 동일 — [[e2e-seed-accounts-and-data]]). 다음 세션에서도 이 비번으로 활용.

---

## 미완 항목 (우선순위순)

### A. admin 변이 액션 실클릭 검증 (데이터 훼손 우려로 보류)
- [ ] **계정 비활성(캐스케이드)**: `/accounts`에서 한 제공자 "비활성" 클릭 → 그 제공자 룸·예약이 함께 정리되는지(8.2 캐스케이드) 확인. ⚠️ booker/주력 provider는 피하고 별도 throwaway 계정으로.
- [ ] **예약 임의취소**: `/reservations`에서 "취소" 클릭 → 슬롯 재오픈 + 예약자 취소 통지 생성 확인. (취소 후 재예약으로 복구 가능)
- [ ] **챗봇 인제스트 실행**: `/ingest`에서 "인제스트 실행" → 결과 리포트·`document_chunks` 갱신 확인(멱등).

### B. booker 잔여 플로우 검증 — ✅ 완료 (이어받은 세션에서 전부 브라우저 검증, 위 참조)
- [x] **후기 작성**: 완료(과거)된 예약에 후기 작성 → `/reservations` 또는 상세 `ReviewForm`. 현재 예약은 미래(19:00)라 "완료" 상태 아님 → 과거 슬롯 예약을 시드하거나 시간 경과 필요.
- [ ] **booker측 예약 취소**: `/reservations`에서 본인 예약 취소 → 슬롯 재오픈.
- [ ] **카카오 공유 버튼 실제 동작**(예약 성공 후 `KakaoShareButton`) — JS SDK 호출 확인.
- [ ] **챗봇 자연어 예약검색 툴**: "강남에 지금 예약 가능한 방?" → 예약 DB 툴콜 답변. (스트림 200은 확인, 답변 텍스트 미캡처 — 응답 지연으로 폴링 타임아웃 가능, 대기 시간 늘려 재확인)
- [ ] 행정동 콤보로 목록 진입 → 룸 행 → 상세(목록 경로는 행정동 선택 게이트라 별도 확인 필요).

### C. 회귀 테스트 / 코드 보강 — ✅ 완료 (이어받은 세션, 위 참조)
- [x] **`create_room` FK 순서 회귀 테스트** (게이트 통합테스트 + 라이브 검증)
- [x] **채팅 401 mid-session 처리** (`streamMessage` refresh 재시도)
- [x] 채팅 로그아웃 게이팅 **유닛 테스트 추가**

### D. 모바일 — ⚠️ 거의 전체 미구현 (가장 큰 완성도 갭)
**실태(검증됨):** 모바일에 실제 구현된 기능은 **온보딩 오버레이(3.9) 하나뿐**. 나머지는 Story 1.6 placeholder 껍데기.
화면 3개(index/favorites/reservations) + 셸(탭·배너슬롯·FAB슬롯·온보딩)뿐, SDK 배선(`api-client.ts`)만 있고 호출 화면 없음.
**원인:** "Epic done" = 웹+백엔드+API 완료였고 모바일은 매 스토리마다 "모바일 dev-build 푸시" 버킷으로 deferral([[web-mobile-parity-on-changes]]).
placeholder가 한 번도 교체되지 않음.
**범위 확정(논쟁 종결):** `docs/idea.md`(프로젝트 시작 이래 미수정)가 모바일을 **MVP로 명시** — L58 "사용자용 모바일 앱: React Native", L63 배포 "모바일 빌드(EAS)", L66/L25 "웹/앱". 즉 모바일은 후속이 아니라 **MVP 미완**이며, 이는 라벨링 문제가 아니라 **범위 누락 → correct-course(에픽 1·3·4·5·7의 모바일 분량 재오픈) 대상**이다.

미구현(=신규 RN 구현 필요, 웹 로직/SDK/백엔드는 재사용):
- [ ] 인증: 로그인/회원가입/세션/로그아웃 (웹 1.7/1.8 대응)
- [ ] 탐색: 지도(카카오 RN 네이티브 지도)·목록·반경·행정동·즐겨찾기 (Epic 3)
- [ ] 예약: 상세·달력·슬롯·연속선택·즉시예약·취소·예약현황 (Epic 4)
- [ ] 알림/공유/후기: 인앱 배너·카카오 공유(네이티브 키)·후기 (Epic 5)
- [ ] 챗봇: FAB·패널·SSE 스트리밍(RN — react-native-sse 후보)·RAG·예약검색 (Epic 7)
- [ ] spike 잔재(`react-native-sse`, `EXPO_PUBLIC_SPIKE_BASE`) 제거 vs E7 재사용 — KTH 결정.

→ **작은 수정 아님. 별도 빌드 캠페인**(사실상 Epic 1·3·4·5·7의 모바일 버전 재구현). 다음 세션에서 모바일 갭 백로그를 먼저 산정 권장.

**★개발 접근 결정(KTH, 2026-06-18):** 모바일은 매 스토리마다 웹과 짝맞춰 점진 개발하지 않고, **웹/백엔드가 안정화된 뒤 한 번에(일괄) 개발**한다 — 그게 비용이 덜 든다(매 변경 짝맞춤 오버헤드·중간 재작업 회피). 따라서 모바일 MVP 갭은 correct-course로 정렬하되, 착수 시점은 "웹 잔여(C·B·A·E) + 배포 선결이 끝난 뒤"로 둔다. [[web-mobile-parity-on-changes]]의 "변경 시점 짝 점검"은 이 일괄 전략과 충돌하지 않는다 — 변경마다 모바일 짝을 **확인은 하되**, 반영은 "모바일 일괄 캠페인" 버킷으로 라우팅한다(확인 안 함 ≠ 일괄로 미룸).

### E. 경미 / 관찰됨
- [x] **온보딩 a11y aria-hidden 경고 해결** — `OnboardingOverlay`를 다중 페이지 **스와이프 캐러셀**(수동 드래그/화살표/점 + 자동 넘김, 사용·예약 안내 4페이지, lucide 아이콘·만다린 토큰, "다시 보지 않기"/"시작하기")로 전면 개편하면서, `Dialog.Content`에 `onOpenAutoFocus`로 포커스를 모달 내부로 명시 이동 → FAB 포커스 잔존(`Blocked aria-hidden … retained focus`) 경고 제거(브라우저 콘솔 warnings 0 확인). 슬라이드 트랙은 `aria-hidden`(SR은 현재 슬라이드 Dialog.Title/Description으로 안내). 단위 5건 + Playwright 전 인터랙션(렌더·다음/이전·점·실제 드래그 스와이프·시작하기 영속·재방문 무노출) 검증.
- [ ] 임시 시드 데이터·드라이버 정리 시점 결정(배포 전 dev DB 정리). **단 현재 강남 테스트룸 12개는 KTH 지시로 보존 중**(위 🧪 참조) — 정리는 배포 직전에.

### 신규 — 지도 화면 반경 UX 개편 (KTH 요청, 2026-06-18 후속)
- [x] **위치 권한 선확인**: `useGeolocation`이 마운트 즉시 무조건 `getCurrentPosition`(=프롬프트)하지 않고 **Permissions API로 상태 먼저 확인** → `granted`만 자동 측정(내 위치로 이동), `prompt`/`denied`는 자동 측정 안 함(기본=서울). Permissions API 없는 환경은 레거시 자동측정 폴백. `permission`/`locate()` 노출.
- [x] **'내 반경' 버튼**: 지도 화면 + 권한 granted 시 지도/목록 토글과 **같은 줄 오른쪽 끝**에 생성. 클릭 시 지도가 어디 있든 현 위치로 재중심(MapView `recenterNonce`). 위치도 갱신.
- [x] **안내 문구(지도 상단 오버레이)**: 권한 없을 때 안내를 일반 흐름이 아니라 **지도 위 오버레이**(absolute top, pointer-events 분리)로 띄운다 — 모바일에서 지도(60vh)를 영역 밖으로 밀어내던 문제 해결. `prompt`=누르면 측정요청 버튼, `denied`/미지원=눌러서 다시 시도 버튼.
- [x] **OS 권한 변경 즉시 반영**: Permissions `change` 는 브라우저 권한 변경에만 발생(OS 위치 토글은 미발생). 그래서 (1) **탭 복귀(focus/visibilitychange) 시 자동 재확인**(브라우저 granted인데 좌표 없으면 조용히 재측정), (2) 안내 칩 **수동 "다시 시도"** 버튼 — 둘로 즉시 반영을 보강. `useGeolocation`에 `refresh()` 추가.
- [x] **자동 우회 제거**: 위치 거부 시 행정동 목록으로 자동 우회하던 3.6 동작 제거 — 지도는 기본 위치 유지 + 안내. MapView 인맵 위치 배너도 중복이라 미사용(안내는 토글 하단 1곳).
- 검증: 단위(useGeolocation/ExploreView/MapView) + 웹 전체 354 통과, lint·타입 클린. 브라우저로 granted(내 반경)·prompt(자동측정 0회·안내→클릭 측정→granted 전환) 실증. **목록(반경) 검색 UX는 다음 차례**(KTH) — 현재는 반경 모드 진입 시 prompt면 측정 요청하도록만 연결.

### 신규 — 관리자 인제스트 문서 목록 (KTH 요청, 2026-06-18 후속)
- [x] 인제스트 화면에 **지식 문서 목록** 표현: `GET /admin/ingest/documents`(읽기 전용 — 디스크 corpus 스캔 + 단일 GROUP BY 집계 + content_hash 대조). 4상태 **ingested(최신)/stale(변경됨·재인제스트 필요)/pending(미적재 신규)/orphan(파일 사라짐·정리 예정)** 배지. store `summarize_loaded_documents`·schema·service·router → OpenAPI export → SDK 재생성 → 프론트 `useIngestDocuments` + 목록 UI(인제스트 성공 시 invalidate). 확인 문단 잘림(`leading-[1.6]`)·조기 줄바꿈(`max-w-prose` 제거) 수정. 백엔드 5 + 프론트 5 테스트, lint·타입·드리프트 클린, 브라우저로 3상태 실재현 검증.

### F. 목록 페이징 / 무한스크롤 — ⏳ 남음 (신규, 2026-06-18 식별)
**현황(확인됨):** 페이징·무한스크롤 **없음**. 백엔드 `search_rooms`(행정동·반경)·`list_active_rooms`(지도 핀)이 매칭 룸을 **limit/offset/cursor 없이 전부 반환**하고, 프론트 `RoomList`가 전부 렌더한다(rooms/service.py Dev Notes에 "공개 무제한 스캔 페이지네이션 부재 = deferred"로 명시). MVP 스케일(제공자당 1룸)에선 동작하나 대량 데이터에선 페이로드·DOM·서버 슬롯계산 부하.
**구현 범위(하면):**
- 백엔드: `search_rooms`/`list_active_rooms`에 cursor(or offset)+limit, 응답에 `next_cursor`. 행정동·반경·지도·**챗봇 `search_available_rooms`** 네 경로가 같은 reader 계열이라 일관 적용.
- 프론트: `useRoomSearch` → `useInfiniteQuery` + IntersectionObserver 무한스크롤 + 로딩 푸터.
- 테스트: 페이지 경계·중복 방지·빈 다음페이지.
→ KTH 결정 대기: 지금 구현 vs MVP 유지.

---

## 정리되지 않은 큰 질문
- 이 모든 완성도 작업을 **배포 단계(MVP 스토리단계 종료)** 맥락에서 어떻게 트래킹할지(스토리화 vs deferred-work 회수 vs 직접 수정 기록).
- **모바일 MVP 미완 정식 처리**: idea.md로 범위는 확정됐으므로 결정할 것은 "어떻게"뿐 —
  correct-course(에픽 1·3·4·5·7 모바일 분량 done 되돌림 + 모바일 스토리 신설) vs 별도 "모바일 에픽" 신설.
  "MVP 스토리단계 종료→배포"라는 현재 sprint-status 전제 자체가 idea.md와 모순(모바일 미완)이므로 배포 전 재정렬 필요.
