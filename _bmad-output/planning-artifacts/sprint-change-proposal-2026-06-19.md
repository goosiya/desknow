---
date: 2026-06-19
author: KTH (via Correct Course 워크플로우)
mode: Batch
scope_classification: Moderate (백로그 재구성 + 경량 아키텍처 결정 동반)
---

# Sprint Change Proposal — 모바일 화면 패리티 (Epic 9 신설)

## 변경 네비게이션 체크리스트 (요약)

| ID | 항목 | 상태 | 핵심 결론 |
|----|------|------|-----------|
| 1.1 | 트리거 스토리 식별 | ✅ Done | 단일 스토리 아님 — Epic 1·3·4·5·7의 "모바일 분량"이 매번 "모바일 dev-build 푸시" 버킷으로 deferral되며 한 번도 실행되지 않음 |
| 1.2 | 핵심 문제 정의 | ✅ Done | 유형 = **계획된 deferral의 미회수** + **추적 누락**(에픽 done이 모바일 미완을 가림) |
| 1.3 | 증거 수집 | ✅ Done | `apps/mobile/src/app/*` 3화면 전부 placeholder 텍스트 셸 / 웹 10라우트 구현 / `e2e-followups-2026-06-18.md`가 모순 지적 |
| 2.1~2.5 | 에픽 영향 | ✅ Done | 기존 1~8 재오픈 대신 **신규 Epic 9 신설**(아래 4.x 근거) |
| 3.1 | PRD 충돌 | ✅ Done | 충돌 없음 — FR-18/NFR-4(웹·앱 동일)가 오히려 Epic 9를 **요구**. MVP 정의에 모바일 포함이 원래 전제 |
| 3.2 | 아키텍처 충돌 | ⚠️ Action-needed | 3개 신규 결정 필요: ①모바일 인증 토큰 배선(secure-store+Bearer) ②지도 SDK 선택 ③E2E 세션주입 계층(선례 없음) |
| 3.3 | UX 충돌 | ✅ Done | 신규 UX 아님 — 웹 화면을 RN 터치 우선으로 **동등 재현**(디자인 토큰 공유 `@desknow/ui`) |
| 3.4 | 기타 산출물 | ⚠️ Action-needed | 환경변수 게이팅 E2E 하니스 신규 / `EXPO_PUBLIC_*`+`__DEV__` 표준 패턴 재사용 |
| 4.1~4.4 | 경로 평가 | ✅ Done | **Option 1(Direct Adjustment) = 신규 에픽 추가** 채택 |
| 5.1~5.5 | 제안 구성 | ✅ Done | 본 문서 |
| 6.1~6.5 | 최종 검토·핸드오프 | ✅ Done | KTH 승인(2026-06-19)·`sprint-status.yaml`+`epics.md`에 Epic 9 등록 완료·create-story 핸드오프 |

---

## Section 1 — 이슈 요약

**문제 진술:** 8개 에픽이 전부 `done`으로 닫혔으나, 모든 개발이 **웹·백엔드·admin에만** 이뤄졌고 **모바일 앱(`apps/mobile`, Expo/RN)은 실제 기능 화면이 0개**다. 현재 모바일은 셸/슬롯 골격(탭 네비, 챗봇 FAB no-op, 인앱배너 빈 슬롯, 온보딩 오버레이, 라이트 테마, SDK baseUrl 배선)만 존재한다.

**발견 경위:** 기획상 모바일은 "각 기능 스토리 안에 '웹/앱 동일'로 암묵 포함"되어 있었고(FR-18·NFR-4), 구현 시 매 스토리에서 "모바일(RN)은 E7/모바일 dev-build 푸시로 라우팅"하며 deferral되었다. 그러나 이 버킷이 한 번도 회수되지 않은 채 에픽이 전부 done 처리되어, **`sprint-status.yaml`의 "MVP 스토리단계 종료→배포 단계"가 모바일 미완 현실과 모순**된 상태가 되었다(`e2e-followups-2026-06-18.md`가 이미 지적).

**증거:**
- `apps/mobile/src/app/index.tsx·favorites.tsx·reservations.tsx` — 전부 `ThemedText` 안내 문구 + 주석에 "placeholder — 셸 자리" 명시.
- 웹은 10개 라우트 기능 구현: 홈(지도탐색)·룸상세·즐겨찾기·예약현황·로그인·가입·provider(대시보드/예약/후기/룸등록).
- 모바일 인증 토큰 배선(secure-store + Bearer 헤더) **전무**, 지도 SDK 의존성 **부재**.
- 추가 트리거: 포스트-MVP 수정(provider 웹 표면·지역 용어 통일·커서 페이징 등)이 BMad 밖에서 진행되어 **문서↔현실 드리프트** 발생.

---

## Section 2 — 영향 분석

### 2.1 에픽 영향
- **기존 Epic 1~8:** 웹·백엔드 기준으로는 완료 유효. 재오픈하지 않는다. (모바일 분량을 각 에픽에 되돌려 흩뿌리면 추적 불가·중복 노동.)
- **신규 Epic 9 필요:** 모바일 미구현분 전체를 단일 에픽으로 묶어 추적. 원래 epics.md에 모바일 전용 에픽/스토리가 없으므로(횡단 암묵 포함뿐) 신설이 정합적.
- **순서/우선순위:** Epic 9는 배포(E7/E8 후속) 전 마지막 MVP 완성 단위. 웹·백엔드가 안정화된 지금이 "한 번에 개발"(KTH 결정) 적기.

### 2.2 아티팩트 충돌
- **PRD:** 충돌 없음. FR-18("웹/앱 동일 기능")·NFR-4("웹/앱·화면 간 이질감 제로")가 Epic 9의 **근거**. MVP 범위 축소 아님 — 오히려 누락분 회수.
- **아키텍처(`architecture.md`):** 3개 **신규 결정** 동반(선례 없음):
  1. **모바일 인증 = expo-secure-store + Bearer 헤더** — 계획(L165)은 있으나 미배선. `expo-secure-store` 미설치, `_layout.tsx`에 세션 프로바이더 없음, SDK `client` 인스턴스에 토큰 주입점 미구현.
  2. **지도 = WebView + 카카오맵 JS SDK 재사용 (확정 2026-06-19)** — 웹은 카카오맵 JS SDK(`<script>` 주입)라 RN 직접 이식 불가. `react-native-webview`에 웹 카카오맵을 그대로 띄워 웹과 동일 시각·핀을 재현하고, 핀 탭↔바텀시트는 `postMessage` 브릿지로 연결한다. 카카오 JS 키 재사용(WebView origin 화이트리스트 추가). `react-native-maps`는 한국 Google지도 규제로 패리티 깨짐, 카카오 RN 네이티브 래퍼는 비공식이라 둘 다 기각.
  3. **E2E 세션주입 계층** — 프로젝트에 자동화 E2E 계층이 **아예 없음**("E2E"=Playwright MCP 수동 검증). 환경변수 게이팅 주입 하니스는 신규 아키텍처 결정.
- **UX(`ux-...`):** 신규 화면 설계 아님. 웹 화면을 RN 터치 우선으로 동등 재현(디자인 토큰 `@desknow/ui` 공유, 라이트 단일 테마).
- **기타:** `react-native-sse`(챗봇 SSE 대비) 이미 의존성 존재 → 재사용. 카카오 공유=네이티브 모듈(EAS dev build). 무한스크롤=`FlatList onEndReached`로 대체.

### 2.3 기술 이식 리스크 (웹 종속 → RN 재구현)
| 영역 | 웹 구현 | 모바일 대체 |
|------|---------|-------------|
| 인증 | httpOnly 쿠키 `credentials:include` | secure-store 토큰 저장 + Bearer 헤더(SDK `client` 인터셉터) |
| 지도 | 카카오맵 JS SDK `<script>` | 지도 SDK 결정(2.2-②) |
| 챗봇 | `fetch` ReadableStream SSE + vaul | `react-native-sse` + RN 모달/시트 |
| 공유 | `window.Kakao.Share` JS SDK | RN 카카오 SDK 또는 `Share` API |
| 저장소 | localStorage | AsyncStorage(온보딩 이미 적용) |
| 무한스크롤 | IntersectionObserver + 센티넬 | FlatList `onEndReached` |
| 지오코딩 | 카카오 JS Geocoder | WebView 또는 네이티브 Geocoder |

### 2.4 재사용 자산 (이식 부담 경감)
타입 안전 SDK(`@desknow/api-client`, 웹·admin과 동일), 디자인 토큰(`@desknow/ui`, 핀 색 포함), 라이트 테마 시스템, 온보딩(`useOnboarding`/AsyncStorage 실동작), 크로스컷 슬롯 골격(FAB/배너/온보딩), 플랫폼 분기(`.web.tsx`), safe-area·gesture-handler·reanimated 의존성 이미 존재.

---

## Section 3 — 권장 경로

**선택: Option 1 — Direct Adjustment (신규 Epic 9 추가)** + 문서 현실 동기화.

| 옵션 | 평가 | 노력 | 리스크 | 채택 |
|------|------|------|--------|------|
| 1. Direct Adjustment (신규 에픽) | 미구현분을 단일 에픽 3스토리로 추적·실행 | Medium | Low | **✅** |
| 2. Rollback | 되돌릴 잘못된 산출물 없음(웹은 정상) — 무의미 | — | — | ❌ Not viable |
| 3. MVP 축소 | 모바일은 MVP 핵심(FR-18) — 축소 불가·KTH 의도 반대 | — | — | ❌ Not viable |

**근거:** 웹·백엔드가 정상 완료된 상태라 롤백 대상이 없고, 모바일은 MVP 필수 표면이라 축소도 불가. 누락분을 신규 에픽으로 묶어 빠르게(3스토리) 실행하는 것이 추적성·속도·팀 모멘텀 모두에 최적. KTH의 "웹/백엔드 안정화 후 모바일 일괄 개발" 결정과도 일치.

---

## Section 4 — 상세 변경 제안 (Batch)

### 4.1 신규 Epic 9 (epics.md 추가)

> **## Epic 9: 모바일 앱 화면 패리티**
>
> 웹에 구현된 전 화면(탐색·예약·예약후경험·provider·챗봇)을 Expo/React Native 모바일 앱에 **기능 동등(parity)** 으로 구현한다. 디자인·구조·인터랙션은 웹과 동일하게 재현하되, 모바일앱/RN 특성(네이티브 네비·제스처·세이프에어리어·secure-store Bearer 인증·지도 SDK·SSE)을 반영한다. 화면 기준 통합검증(Playwright, 환경변수 게이팅 세션주입)으로 마감. (FR-18, NFR-4 / UX 토큰 공유 / 모바일 일괄 개발 결정 2026-06-19)
>
> **FRs covered:** FR-18(웹/앱 동일) 외 Epic 3·4·5·7 기능 FR의 모바일 표면
> **의존:** Epic 1~8(웹/백엔드·SDK·토큰 완료) / **핵심:** 신규 결정 3건(secure-store 인증·지도 SDK·E2E 주입)

**Story 9.1 — 모바일 인증 + 탐색·검색**
As a 예약자,
I want 모바일 앱에서 로그인/가입하고 지도·목록으로 스터디룸을 탐색·검색·즐겨찾기 할 수 있기를,
So that 웹과 동일한 첫 진입 경험을 모바일에서도 누린다.
- 범위: secure-store+Bearer 인증 배선(세션 프로바이더·토큰 저장·SDK 헤더 주입), login/signup(역할 선택), 홈 지도탐색(지도 SDK 결정·핀 가용성 색), 지도/목록 토글, 바텀시트 요약, 지역(2단)·반경 검색, 즐겨찾기, 온보딩 연결, 위치 권한, 막다른화면 5상태 매트릭스.
- **포함(파운데이션):** E2E 세션주입 하니스(`EXPO_PUBLIC_*`+`__DEV__` 게이팅, 프로덕션 빌드 제외) — 9.2/9.3가 재사용.

**Story 9.2 — 모바일 예약 + 예약 후 경험**
As a 예약자,
I want 룸 상세에서 슬롯을 골라 즉시 예약하고, 예약현황 확인·취소·공유·후기까지 할 수 있기를,
So that 예약 전 과정을 모바일에서 완결한다.
- 범위: 룸 상세(3단 위계·미니지도), 날짜·슬롯 가용성, 연속 슬롯 선택, 즉시 예약(결제 없음), 예약현황(다가오는/지난·취소 리드타임 게이팅), 인앱 배너 연결(접속 시 GET), 카카오 예약 공유, 후기 작성.

**Story 9.3 — 모바일 provider + 챗봇 + E2E 통합검증**
As a 제공자/예약자,
I want 제공자 화면(예약자현황·거절·후기답글·룸등록)과 플로팅 챗봇을 모바일에서 쓰고, 전 화면이 실검증되기를,
So that 제공자 운영과 챗봇까지 포함해 모바일 MVP가 완성된다.
- 범위: provider 대시보드/예약자현황/예약거절/후기답글, 룸 등록·수정(지오코딩·영업시간), 플로팅 챗봇(`react-native-sse` SSE 스트리밍·세션 유지·RAG/예약검색·범위밖 거절), **Playwright 통합테스트**(9.1 주입 하니스로 9.1~9.3 전 화면 실검증).

### 4.2 문서↔현실 동기화 (현실=정본)
- **`epics.md`:** ① Epic List에 Epic 9 요약 추가 ② Epic 9 상세 섹션 추가 ③ Overview에 "포스트-MVP 보강(provider 웹 표면·지역 용어 통일·커서 페이징 등)은 BMad 밖에서 구현되었으며 구현 소스를 정본으로 수용" 1줄 주석. (기존 Epic 1~8 스토리 본문은 재작성하지 않음.)
- **`sprint-status.yaml`:** `epic-9: backlog` + `9-1/9-2/9-3` 키를 `backlog`로 추가. epic-8의 "MVP 스토리단계 종료→배포" 주석에 "단, 모바일 패리티=Epic 9로 분리·배포 전 선결" 보정 1줄.
- **스토리 파일:** 승인 후 `create-story`로 `9-1-…md`/`9-2-…md`/`9-3-…md` 생성(기존 4-2 포맷 준수). 신규 아키텍처 결정 3건은 각 스토리 Dev Notes에 ADR 형식으로 기록(별도 architecture.md 전면 개정 없이 경량 처리).

### 4.3 신규 아키텍처 결정 (Epic 9 동반, 경량 ADR)
1. 모바일 인증 = expo-secure-store + Bearer(SDK `client` 인터셉터 주입), `_layout.tsx` 세션 부트스트랩.
2. 지도 = WebView + 카카오맵 JS SDK 재사용(확정). `react-native-webview` + `postMessage` 브릿지(핀 탭→시트), 카카오 JS 키 재사용. 9.1 착수 시 브릿지 왕복 1건만 빠르게 검증.
3. E2E 세션주입 = `EXPO_PUBLIC_E2E_*`/`__DEV__` 게이팅, 프로덕션 빌드 미포함, Expo Web 빌드를 Playwright로 구동.

---

## Section 5 — 구현 핸드오프

- **분류: Moderate** — 백로그 재구성(에픽/스토리 신설) + 경량 아키텍처 결정. 전면 replan(Major) 불필요.
- **핸드오프:**
  1. **PO/DEV** — `sprint-status.yaml`·`epics.md`에 Epic 9 등록(본 제안 승인 직후, 6.4).
  2. **create-story (DEV)** — 9.1→9.2→9.3 순차 스토리 파일 생성(이전 스토리 학습 반영).
  3. **dev-story (DEV)** — 9.1에 인증·지도 SDK·E2E 하니스 파운데이션 포함, 이후 9.2/9.3.
  4. **통합검증 (DEV+Playwright MCP)** — 각 스토리 말미 Expo Web 빌드 화면 실검증.
- **성공 기준:** 웹 10라우트에 대응하는 모바일 화면이 동등 동작 + Playwright로 9.1~9.3 전 화면 실검증 통과 + 프로덕션 빌드에 E2E 주입 코드 미포함.

---

## 승인 결과 (2026-06-19)
**KTH 승인 완료.** 후속 결정 확정: 지도 = WebView+카카오맵 JS(앱 전체 아님, 지도 캔버스만) · 패리티 = 네이티브 재현(계획 원안).
조치 완료: ① `epics.md` — Epic List 요약 + Epic 9 상세(9.1~9.3) + Overview 포스트-MVP 수용 주석 추가 ② `sprint-status.yaml` — `epic-9` + 3 스토리 `backlog` 등록.
다음: `create-story`로 9.1 → 9.2 → 9.3 순차 생성(DEV).
