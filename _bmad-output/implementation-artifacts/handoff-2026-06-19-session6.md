# 세션 인계 — 모바일 인터랙션·admin UI 수정 + 운영 시드 정비 (2026-06-19 세션6)

`handoff-2026-06-19-session5.md`(F 목록 커서 페이징/무한스크롤)에서 이어진 세션. 이번 세션은
**브라우저(Playwright, 모바일 터치 에뮬레이션)로 직접 검증**하며 모바일/admin UI 버그를 잡고, dev
운영 데이터(비번 통일·서울 분산 시드)를 정비했다. 모두 BMad 미경유(폴리시·버그수정·운영데이터).

---

## 이 세션에서 완료

### 1. 모바일 인터랙션 수정 (사용자 웹 — PC 무영향)
- **★하단 내비가 화면 최상단에 박혀 헤더 링크를 덮던 버그(전 모바일 페이지 영향).** `fixed bottom-0`
  하단바가 **헤더 안**에 있었는데 헤더의 `backdrop-blur`(=backdrop-filter)가 fixed 자식의 컨테이닝
  블록이 되어 `bottom-0`이 56px 헤더 기준→화면 맨 위에 붙음(DeskNow·로그인 탭 불가). **하단바를
  헤더 밖(AppShell 루트)으로 분리**(`AppNav`=상단/`AppBottomNav`=하단). 측정: 수정 전 aside y=7 → 후 y=795.
- **온보딩 소개 X(닫기) 버튼이 안 눌림.** 스와이프 트랙 내부 div의 `transform: translateX`가 스택킹
  컨텍스트를 만들어 z-index 없는 absolute X 위에 그려져 클릭/탭 가로챔(마우스·터치 공통). X에 `z-10`.
- **지도 relayout 보강.** 컨테이너 크기 변경(모바일 주소창 접힘·회전) 후 `map.relayout()` 누락 시
  Kakao 타일/좌표 stale로 "멈춘 듯" 보임 → MapView에 ResizeObserver→relayout(중심 보존). PC는 크기
  불변이라 사실상 no-op. (`types/kakao-maps.d.ts`에 relayout/getCenter 타입 보강.)
- **'내 반경' 클릭 시 축척도 초기값 복귀(메인 지도 한정).** 다른 지역으로 이동·줌 변경 후 '내 반경'을
  누르면 중심뿐 아니라 축척까지 초기(level 5=`INITIAL_MAP_LEVEL`)로 — recenterNonce effect에
  `setLevel` 추가. 검증: 초기 250m→줌아웃 1km→내반경 250m 복귀.
- **위치 권한 안내 칩 깜빡임 제거.** `useGeolocation` 초기 permission="prompt"라 권한 확인 *전부터*
  칩이 떴다 granted resolve 시 사라지던 깜빡임을, ExploreView에서 `geoPermissionResolved` 게이트로
  해소(확인 후에만 분기 렌더). 검증: granted+새로고침 시 MutationObserver로 칩 1프레임도 미출현.

### 2. admin 앱 수정
- **하이드레이션 경고**(GA opt-out 확장이 `<html>`에 `data-*` 주입). web 선례대로 admin
  `layout.tsx`의 `<html>`에 `suppressHydrationWarning`.
- **좌측 사이드바가 콘텐츠 높이에 맞춰 잘림.** `min-h-full`(100%)이 body 확정높이 부재로 콘텐츠로
  떨어짐 → `AdminShell` 루트를 `min-h-[100dvh]`로(Tailwind v4에서 `min-h-screen`은 CSS 미생성이라
  arbitrary 값 사용). 짧은 콘텐츠=뷰포트 바닥까지·긴 콘텐츠=전체 높이까지 사이드바 stretch 검증.

### 3. 운영 시드 정비 (dev Supabase)
- **전 계정 비번 `Test1234!` 통일**(admin 포함, KTH 방침 [[all-test-passwords-test1234]]). 스크립트
  `apps/api/scripts/reset_all_passwords.py`(앱 동일 해셔로 전 행 UPDATE·재실행 가능). `.env`의
  `SEED_ADMIN_PASSWORD`도 `Test1234!`로 변경(seed_admin 재실행해도 유지).
- **서울 전역 분산 provider+룸 22개 신규.** 룸 없던 provider 2명(`_pweb0`→마포·`_guard_prov_…`→노원)
  + 신규 provider 20명(`_seedprov_0~19@test.desknow`)에 룸 등록. 서울 20개 구 실주소를 카카오
  geocode(요청 2초 텀)로 실좌표+b_code 확보 → 핀이 서울 전역에 분산(밀집 없음). 브라우저 검증 OK.
  현 dev DB = 계정 45개·활성 룸 25개. 상세 [[e2e-seed-accounts-and-data]].

### 4. 문서 반영
- `sprint-status.yaml`에 **`post_epic_changes` 섹션** 신설 — 전 에픽 done 이후 수정 항목 정리
  (provider 웹표면·용어통일·역할가드/409·F페이징·모바일·admin·운영시드·RAG문서·admin검증). 본
  인계가 모바일/admin/운영시드/RAG/검증의 포인터.

### 5. RAG 운영 문서 보강 + admin 변이 실검증 (세션 후반)
- **docs_corpus 문서 보강·리네임**: `sample-service-guide.txt` → **`service_guide.txt`**, 내용을 실제
  운영 기준 서비스 가이드로 보강(서비스 소개·검색·슬롯·예약·취소6h/환불·알림·후기·공유·챗봇·제공자
  안내·문의). **재인제스트**(admin UI 인제스트 실행): service_guide 3청크 적재·구 sample 청크 정리·
  README 스킵. **챗봇 RAG 검증**: 새 문서에서 정확 응답("6시간 전까지 취소"·"제공자 1개"=신규 문서
  전용 사실이라 새 적재분 검색 입증).
- **admin 변이 액션 실클릭 검증**(KTH 승인, **일회용 전용 데이터로만**): 검증용 throwaway
  provider(`_admchk_prov`)+룸("관리자검증 일회용룸")+booker(`_admchk_book`)+확정예약 2건 생성 후 —
  ①예약 임의취소(확정목록 4→3·슬롯 재개방·통지) ②계정 비활성 캐스케이드(provider 비활성→룸 노출
  중단=활성룸 26→25·검색·핀 제외·신규예약 차단·기존예약 유지) 둘 다 end-to-end 동작 확인. (인제스트
  실행도 변이 검증에 포함.) ⚠️ 예약 임의취소 확정 클릭이 처음 안전분류기에 차단→우회 없이 KTH 승인
  후 일회용 데이터로 진행. **일회용 `_admchk_*` 데이터는 KTH 지시로 존치**(provider/룸 비활성=화면
  미노출).

## 검증
- 웹: `pnpm check-types`·`pnpm lint` 클린, 웹 테스트 **390 통과**. admin: typecheck·lint 클린.
- 브라우저(Playwright 터치 에뮬레이션): 모바일 가로채기 0건(홈/목록/상세/로그인/예약현황 + 챗봇·룸시트
  오버레이), 온보딩 X 터치 닫힘, '내 반경' 축척 복귀, 위치칩 무깜빡, admin 사이드바 풀하이트, PC 무회귀.
- 라이브: 비번 통일 25→갱신 후 admin·booker·_pweb0 login 200, 룸 25개 지역검색·핀 분산 확인.
- RAG: 재인제스트 후 챗봇이 새 문서 내용으로 정답. admin 변이 3종(인제스트·임의취소·비활성 캐스케이드)
  일회용 데이터로 end-to-end 검증.

## DB / 마이그레이션
- 모델 변경 0 — 전부 UI/읽기/데이터 경로. 마이그레이션 불요(head 불변). 운영 데이터는 dev Supabase
  직접 반영(비번 UPDATE·provider/룸 INSERT).

## 다음 세션 남음 (우선순위)
1. **모바일 일괄** [[mobile-build-all-at-once-after-web]] — ★이번 모바일 수정(하단네비·온보딩·지도·
   위치칩)은 사용자 웹 기준. RN 모바일은 별도 dev-build 버킷에서 일괄(웹 안정화 후).
2. **스토리 정식 반영(correct-course)** — `post_epic_changes`의 폴리시/수정들을 스토리 단위로 정규화
   (현재는 sprint-status 요약 + handoff 포인터). [[e2e-completeness-followups]].
3. **배포 준비** — 운영 비밀 교체(SEED_ADMIN 새 강비번 — 테스트 Test1234! 규약은 배포 예외)·DB 전환
   ([[deployment-first-time-checklist]]).

## 변경 파일
- 웹: `features/map/MapView.tsx`·`types/kakao-maps.d.ts`(relayout/getCenter+내반경 축척)·
  `components/OnboardingOverlay.tsx`(X z-10)·`components/shell/AppNav.tsx`(AppBottomNav 분리)·
  `components/shell/AppShell.tsx`(하단네비 헤더밖)·`features/list/ExploreView.tsx`(위치칩 게이트).
- admin: `src/app/layout.tsx`(suppressHydrationWarning)·`src/components/shell/AdminShell.tsx`(min-h-[100dvh]).
- api: `scripts/reset_all_passwords.py`(신규)·`.env`(SEED_ADMIN_PASSWORD)·
  `docs_corpus/service_guide.txt`(sample-service-guide.txt 리네임+운영 보강).
- 문서: `sprint-status.yaml`(post_epic_changes 섹션).

## 상태 메모
- web(3000)·admin(3001)·API(8000) 기동 중. admin은 CSS 재빌드 위해 이번에 1회 재시작.
- API .env DATABASE_URL=dev Supabase(`idbvpqtdekeqxqdzpizf` 풀러). 전 테스트 계정 비번=`Test1234!`.
- 현 dev DB: 계정 47개(45 + 일회용 `_admchk_prov`/`_admchk_book` 2)·활성 룸 25개(일회용 룸 1개는
  비활성). 일회용 `_admchk_*`·잔여 예약 1건 존치(KTH 지시). RAG corpus=README.md+service_guide.txt.
