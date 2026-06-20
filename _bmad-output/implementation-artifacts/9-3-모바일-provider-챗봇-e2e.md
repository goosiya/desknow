---
baseline_commit: NO_VCS
---

# Story 9.3: 모바일 provider + 챗봇 + E2E 통합검증

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 제공자/예약자,
I want 제공자 화면(예약자현황·예약 거절·후기 답글·룸 등록/수정)과 플로팅 챗봇 "룸메이트"를 모바일에서 쓰고, 9.1~9.3 전 화면이 실검증되길,
so that 제공자 운영과 챗봇까지 포함해 모바일 MVP가 완성된다 (FR-18 / Epic 6·7 표면).

> **이 스토리는 9.1·9.2 파운데이션 위에 모바일 패리티의 마지막 두 도메인(provider·챗봇)을 얹고 Epic 9 전체를 통합검증으로 마감한다.** 9.1이 ① secure-store Bearer 인증 스택(`useSession`·`useAuth`·`SessionKeeper`·`refreshSession`)·`pendingSignup` ② WebView 카카오맵 패턴(`buildMapHtml`·`MapWebView`) ③ E2E 세션주입 하니스(`window.__DESKNOW_E2E__.injectSession`)를, 9.2가 룸 상세·예약·후기 **표시**(`ReviewSection`은 제공자 답글을 read-only로 이미 렌더)·`StarRating`·`useRoomReviews`·`errors.ts`를 세웠다. 현재 모바일에서 **`apps/mobile/src/app/provider/room.tsx`는 9.1이 만든 9.3 소유 스텁**("스터디룸 등록은 곧 제공돼요")이고, **`ChatbotFabSlot`은 `onPress={() => {}}` no-op 스텁**이며, **`apps/mobile/src/features/chatbot/`는 존재하지 않는다.** 9.3은 이 세 seam을 웹과 기능 동등(parity)으로 채운다. 핵심 통찰: provider 데이터 로직·룸폼 검증·에러분류·챗봇 transcript 관리·SSE 프레임 파서는 **거의 전부 프레임워크 무관 순수 함수·React Query 훅**(SDK+키만)이라 **복사·미러로 재사용**하고, 포팅이 필요한 건 ① JSX(provider 화면·룸폼·챗봇 패널) ② **두 진짜 갭** — 웹 카카오 JS Geocoder(가입 전 지오코딩)와 웹 `fetch` ReadableStream SSE(쿠키 인증)다. 후자는 **9.1이 이미 react-native-sse를 설치**해 두었고 인증은 Bearer로 갈아끼우면 된다. **백엔드·SDK·웹·admin은 무변경**(diff 0) — 9.1·9.2와 동일한 순수 클라이언트(모바일) 작업이다.

## 범위 결정 (KTH 확정 2026-06-19 — create-story)

이 스토리가 닿는 경계와 두 진짜 갭의 처리 방향을 다음과 같이 확정한다. 결정 2건(가입 전 지오코딩·provider 네비)은 **KTH 확정 완료**(2026-06-19 — 둘 다 권장안 채택·Change Log).

1. **9.3 = 모바일 패리티 완결 + Epic 9 통합검증.** provider 4화면(예약자현황·예약 거절·후기 답글 **작성**·룸 등록/수정)·`ProviderGuard`·역할 네비게이션·플로팅 챗봇(SSE 스트리밍·세션 유지·RAG/예약검색/범위밖 거절)·9.1~9.3 전화면 Playwright 통합검증을 9.3이 완결한다. 9.1(인증·탐색)·9.2(예약·예약후경험)가 만든 화면·자산은 **재사용**(중복 복사·재발명 금지).

2. **[갭①·KTH 확정] 룸폼 지오코딩 = 로그인 후=백엔드 geocode / 가입 전(pendingSignup)=WebView 카카오 Geocoder.** 웹은 두 경로다 — 로그인 provider는 백엔드 `roomsGeocodeAddress`(provider 전용 게이트), 가입 전 `pendingSignup`은 백엔드 geocode를 못 써서 **카카오 JS Geocoder 직접 호출**(`geocodeViaKakaoJs`). RN엔 `window`/`document`가 없어 카카오 JS를 직접 못 돌린다. **권장 = 9.1 WebView 카카오맵 패턴 재사용** — 가입 전 경로는 `services` 라이브러리를 로드한 작은 WebView에서 `kakao.maps.services.Geocoder.addressSearch`를 돌리고 결과를 `postMessage`로 RN에 회신한다(맵 미니지도와 동형). 이는 **KTH 기존 결정([[provider-signup-deferred-and-geocode]]: "가입폼 주소검색=카카오 JS Geocoder, 백엔드 geocode는 provider 전용 유지")을 그대로 보존**하고 **백엔드 무변경**을 지킨다. **단 Expo Web은 react-native-webview 미지원이라 가입 전 지오코딩은 Playwright로 검증 불가**(맵 degrade와 동형) → AC9 검증은 **로그인 provider 경로(백엔드 geocode·Expo Web 동작)**로 룸등록을 실검증한다. (대안 = 백엔드 geocode 게이트를 가입 전에도 허용 = 백엔드 변경·보안자세 변동 → 비권장. §결정.)

3. **[갭②·결정 불요·prescribed] 챗봇 전송 = `react-native-sse`(POST+body+Bearer) + 401→`refreshSession` 1회 재시도.** 웹 `streamMessage.ts`는 레포 유일의 raw `fetch`+ReadableStream+`credentials:"include"`(쿠키)다. RN(Hermes)엔 ReadableStream 스트리밍이 없거나 불안정하므로 **9.1이 이미 설치한 `react-native-sse@^1.2.1`**로 대체한다(`POST` + JSON body + `Authorization: Bearer` 헤더 지원). **`react-native-sse`의 `EventSource`는 별도 import라 eslint 직접-fetch 가드에 안 걸린다**(allowlist 불요 — 단 raw fetch 방식을 택하면 웹처럼 chatbot 1파일 allowlist 추가 필요). 401 회복은 SDK 인터셉터가 SSE 경로를 안 타므로 **수동**: `getAccessToken()`로 헤더 세팅 → 401/error 시 9.1 `refreshSession()` 호출 후 새 토큰으로 1회 재연결(무한루프 가드). **`react-native-sse`는 web에서 XHR 폴백으로 동작**하므로 챗봇 스트리밍은 **맵/지오코더와 달리 Expo Web에서 Playwright 검증 가능**(AC9 강한 검증 대상).

4. **[KTH 확정] provider 네비게이션 = 역할조건부.** 웹 `AppNav`는 `session.role==="provider"`면 `PROVIDER_NAV`(내 스터디룸·예약자 현황·후기)로 `BOOKER_NAV`(찾기·예약현황·즐겨찾기)를 **통째 교체**한다. **권장 = 모바일도 역할조건부 네비** — 로그인 역할이 provider면 `(tabs)`가 provider 탭 3개를 렌더(예약자 현황·후기·내 스터디룸), booker면 기존 3탭. 이게 가장 충실한 패리티다. (대안 = booker 탭 유지 + provider 화면을 Stack 라우트 + provider 랜딩 진입 → 단순하나 패리티 약함. §결정.) `/provider/room` 스텁(9.1)은 룸폼으로 교체하고, `/provider/reservations`·`/provider/reviews` 라우트를 신설한다.

5. **후기 답글 = 9.2 `ReviewSection` 위에 작성 훅·폼만 추가.** 9.2가 룸 상세 `ReviewSection`에 제공자 답글을 **read-only로 이미 렌더**(`ReviewListItem['reply']`)했다. 9.3 provider 후기 화면은 내 룸 후기 목록에 **답글 작성 폼**(`useReplyToReview`·`reviewsCreateReply`)을 더한다. 후기 목록 키는 룸 상세와 **동일**(`["rooms",roomId,"reviews"]` = `roomReviewsKey`) — 캐시 공유·작성 후 정확 invalidate. `StarRating`(9.2)·`useRoomReviews`(9.2) 재사용.

6. **단위 테스트 러너 미도입(9.1·9.2 패리티).** 모바일은 `test` 스크립트·러너 부재. 9.3 검증도 **typecheck(`pnpm --filter mobile check-types`)+lint(`expo lint`)+Playwright(MCP) Expo Web 실검증**을 1차로 한다. 신규 테스트 인프라 도입 금지.

## Acceptance Criteria

**AC1 — provider 예약자현황이 익명 라벨로 조회되고 무한스크롤된다 (FR / 6.1 표면)**
**Given** provider 계정으로 `/provider/reservations` 진입
**When** 목록이 마운트되면
**Then** `useProviderReservations`(`useInfiniteQuery`·`PROVIDER_RESERVATIONS_QUERY_KEY=["provider","reservations"]`·SDK `reservationsListProviderReservations({query:{cursor}})`·`getNextCursorParam`/`flattenPages`)로 내 룸의 확정 예약이 받아져, 각 행에 **익명 라벨**(`item.booker_label` = 백엔드 sha256 파생 `"예약자 #a3f9c1"` — 클라 해시 금지·이메일/raw UUID 비노출, [[anonymous-booker-label-no-display-name]])·상태 배지(확정/거부됨/취소됨)·시간범위(`formatSlots(slot_starts)` KST)가 표시되고, `FlatList onEndReached` 무한스크롤된다. 5상태 매트릭스(로딩 "불러오는 중…"/에러 "예약을 불러오지 못했어요. 잠시 후 다시 시도해 주세요."/빈 "아직 들어온 예약이 없어요."/네트워크단절/미로그인)가 일관 처리된다. 화면 헤더="예약자 현황", 설명="내 스터디룸의 확정 예약이에요. 예외 상황이면 예약을 거부할 수 있어요(해당 시간이 다시 열려요).".

**AC2 — 예약 거절이 2단 확인으로 동작하고 슬롯이 재활성된다 (FR / 6.2 표면)**
**Given** 예약자현황 행
**When** "예약 거부"→확인("이 예약을 거부하면 해당 시간이 다시 열리고 예약자에게 통지돼요. 거부할까요?")→"거부"를 누르면
**Then** `useRejectReservation`(`reservationsRejectReservation({path:{reservation_id}})`·**옵티미스틱 없음**·onSuccess `["provider","reservations"]` invalidate)가 호출되어 거절되고(서버가 슬롯 DELETE 재활성·예약자 status_change 통지를 **동일 트랜잭션 원자** 처리), 행 배지가 "거부됨"으로 갱신된다. 진행 중 "처리 중…", 취소 버튼으로 확인 철회. 실패="거부에 실패했어요. 잠시 후 다시 시도해 주세요."(웹 verbatim — 웹은 409 `REJECT_WINDOW_PASSED`를 분기하지 않음·**패리티 유지**, 409 친절 분기는 §deferred 웹+모바일 동시 후보). 거절 버튼은 `status==="confirmed"` 행에만 노출.

**AC3 — provider 후기 답글 작성이 내 룸 후기에 동작한다 (FR / 5.6 표면 · [[web-mobile-parity-on-changes]] 회수)**
**Given** provider 계정으로 `/provider/reviews` 진입
**When** 내 룸 후기 목록에서 답글 미작성 후기에 텍스트(최대 500자)를 입력해 "답글 등록"하면
**Then** `useProviderReviews`(내 룸=`useMyRoom`→`roomReviewsKey(roomId)=["rooms",roomId,"reviews"]`·SDK `reviewsListRoomReviews`·`enabled:roomId!==""`)로 목록을 받고, `useReplyToReview(roomId)`(`reviewsCreateReply({path:{review_id},body:{text}})`·**옵티미스틱 없음**·onSuccess `["rooms",roomId,"reviews"]` invalidate)로 답글이 등록되며, 작성됨이면 "사장님 답글" read-only 표시(9.2 `ReviewSection`의 답글 렌더와 일관). 별점 표시는 9.2 `StarRating` 재사용. placeholder="답글을 남겨보세요(최대 500자)", 진행 중 "등록 중…", 실패="등록에 실패했어요."(웹 verbatim). 룸 없음="먼저 스터디룸을 등록하면 후기를 받을 수 있어요.", 빈="아직 후기가 없어요.". 헤더="후기"·설명="내 스터디룸에 달린 후기를 보고 답글을 남길 수 있어요.".

**AC4 — 룸 등록·수정이 영업시간·지오코딩과 함께 동작하고 provider 원자 가입이 완결된다 (FR-4·6 / 2.2·2.3 표면)**
**Given** `/provider/room`(9.1 스텁 교체) — `getPendingSignup()` 있으면 가입 전 신규, 없으면 `useMyRoom`으로 prefill(수정) 또는 신규
**When** 이름·주소검색·수용·시간당 금액·룸 형태·부대시설·영업시간(요일별 on/open/close)을 입력해 제출하면
**Then** 웹 `RoomForm` 미러로 — 검증 순서(이름 빈값/주소 미선택/수용≥1 정수/금액≥0 정수/룸형태/영업요일≥1/`close_time>open_time`)·`business_hours` 변환(`on`인 요일만 `{weekday(월0~일6),open_time:"HH:MM:00",close_time}`)·페이로드(`RoomCreateRequest`)가 그대로 적용되고, `useSaveRoom`(존재 룸=`roomsUpdateRoom` PATCH / 신규=`roomsCreateRoom` POST·**옵티미스틱 없음**·onSuccess `["rooms","mine"]` invalidate)로 저장된다. **지오코딩**(§범위 2)=로그인 시 `roomsGeocodeAddress`(SDK·백엔드 provider 전용·**Expo Web 동작**), 가입 전 `pendingSignup`은 WebView 카카오 Geocoder(degrade 시 검증 불가). `admin_dong_code`(b_code) 없는 결과는 거름("번지까지 포함한 구체적인 주소로 검색해 주세요…"). **provider 원자 가입**=pendingSignup 모드면 `register.mutate({email,password,role:"provider"})` 성공 후에만 `save.mutate(payload)` 순차→성공 시 `clearPendingSignup()`+provider 홈(register 선실패 시 룸 미생성=떠도는 계정 방지). **1룸 초과 409 `ROOM_LIMIT_REACHED`**=`saveRoomErrorCopy(room_limit)`("이미 등록한 스터디룸이 있어요. 새로고침하면 기존 스터디룸을 수정할 수 있어요."), 422=서버 message. 제출 라벨: pending="가입하고 등록하기"/수정="수정 저장"/신규="등록하기". 용어 "지역"(주소·동 표기에 "행정동/법정동" 금지, [[region-code-legal-not-admin-dong]]).

**AC5 — ProviderGuard와 역할 네비게이션이 웹과 동일하게 동작한다 (FR-3 RBAC / post_epic provider-역할-가드)**
**Given** `/provider/*` 진입
**When** 세션·역할이 확정되면
**Then** `ProviderGuard` 미러로 — 미로그인=`/login?next=<원경로>` 리다이렉트(복귀 경로 보존)·잘못된 역할(booker/admin)=홈(`/`) 리다이렉트·**pendingSignup 보류 중(provider 신규)은 미로그인이라도 통과**(원자 가입 흐름)·판별 중 스켈레톤·판별실패="로그인 상태를 확인하지 못했어요."+재시도·네트워크단절=`NetworkNotice`. **역할 네비게이션**(§범위 4)=로그인 역할이 provider면 네비가 provider 메뉴(예약자 현황·후기·내 스터디룸)로 교체된다(웹 `PROVIDER_NAV`↔`BOOKER_NAV` 스왑 동형). 1룸 초과 409 처리는 가드가 아니라 룸 저장 시점(`useSaveRoom`).

**AC6 — 플로팅 챗봇 FAB·패널이 열리고 세션 대화가 유지된다 (FR / 7.3 표면)**
**Given** 로그인 상태의 어느 화면
**When** 우하단 챗봇 FAB(`ChatbotFabSlot` no-op 교체)를 누르면
**Then** `@gorhom/bottom-sheet` 패널(웹 vaul 드로어 미러·~80% 스냅)이 열려 — 첫 진입 인사("안녕하세요, 룸메이트예요. 무엇을 도와드릴까요?")·제안 칩("환불 규정?"/"강남 오후 3시 빈 방")·메시지 목록(자동 하단 스크롤)·입력창("메시지를 입력하세요")·전송 버튼이 RN으로 표시되고, **`deviceId`**(웹 `deviceId.ts` 미러·`localStorage`→`AsyncStorage` 키 `desknow.deviceId`·`crypto.randomUUID` 부재→Math.random v4 폴백)로 **세션·대화가 유지**된다(`useChatbot` 미러·transcript 키 `["chatbot","messages",deviceId]`·`chatbotGetTranscript`로 재수화·`refetchOnMount:false`로 스트리밍 캐시 보존). FAB·패널은 `_layout.tsx` 루트 마운트라 **탭 네비 가로질러 상태 보존**(웹 AppShell 영속 마운트 동형). **미로그인**="로그인하면 룸메이트와 대화할 수 있어요."+"로그인하기"(입력 대신 안내·401 위장 차단). **로그아웃 전이**(session→null)=스트림 abort+`removeQueries(["chatbot"])`+패널 닫기+best-effort `chatbotResetSession`(deviceId 유지).

**AC7 — 챗봇 응답이 SSE로 스트리밍되고 401·절단·에러가 우아하게 처리된다 (FR / 7.4 표면 · §범위 3)**
**Given** 챗봇 패널에서 메시지 전송
**When** `send(text)`하면
**Then** **`react-native-sse`로 `POST ${EXPO_PUBLIC_API_BASE_URL}/api/v1/chatbot/stream`**(body `{message, device_id}`·헤더 `Authorization: Bearer <access>`+`Content-Type:application/json`·쿠키 아님)을 호출해 토큰이 누적 스트리밍되고, 사용자 버블 옵티미스틱 append·첫 델타까지 타이핑 인디케이터("답변을 준비하고 있어요"·`···`)·전송 중 입력 비활성이 동작한다. **SSE 프레이밍**(웹 `parseFrame` 동형·`data: {"delta":"..."}` JSON / `event: done` / `event: error` 인밴드)을 파싱하고, **`done` 없이 종료했거나 assistant 토큰 0개면 graceful error로 강등**(절단을 완성본으로 오인 방지), 에러 시 부분 assistant 제거(`dropPartialAssistant`)+user 버블 유지+`lastFailedText` 보관→"다시 보내기"(`retry`). **401**=`refreshSession()`(9.1 단일-flight) 후 새 토큰으로 **1회만** 재연결(무한루프 가드)·실패 시 세션 무효화. 시작 불가/네트워크단절=`STREAM_FAILED`→`ERROR_COPY`("잠깐 답이 막혔어요. 다시 물어봐 주실래요?"). **LangGraph 실패 turn은 서버가 thread 롤백**([[langgraph-failed-turn-input-rollback]])이므로 클라는 부분 assistant만 정리(재전송 중복 방지·웹 동형). 언마운트/abort 시 연결 정리(`reader.cancel` 등가·캐시/에러 불변).

**AC8 — 챗봇이 RAG 안내·자연어 예약검색·범위밖 거절을 하고 내부 링크만 화이트리스트로 연다 (FR / 7.5·7.6·7.7 표면)**
**Given** 챗봇 대화
**When** 서비스 안내(RAG)·자연어 예약 검색·범위 밖 질문을 보내면
**Then** 서버 react 툴콜(RAG grade·예약 DB 검색·범위밖 거절)의 **최종 assistant 텍스트만** 스트리밍받아 버블로 렌더하고(툴콜 자체는 클라 비노출), **assistant 본문의 마크다운 링크 `[라벨](/경로)`는 화이트리스트 정규식**(`INTERNAL_HREF_RE` 등 웹 verbatim 복사: `/rooms/{uuid}`·`/`·`/?view=list&sigungu=&dong=`만)만 라벨로 링크화해 `expo-router` 라우팅으로 매핑한다(비-내부 URL 비링크·오픈리다이렉트/XSS 방지). 출처·룸 후보 전용 UI는 없음(모델이 자연어에 녹임). 범위 밖 거절 안내("그건 제가 도와드리기 어려운 주제예요…")는 LLM 응답이라 클라는 일반 텍스트로 렌더. 멀티 LLM·RAG grade·예약 툴은 **백엔드 무변경 재사용**(BE는 웹·모바일 공용 `POST /chatbot/stream`·`GET /chatbot/messages`·`DELETE /chatbot/session`).

**AC9 — 9.1~9.3 전 화면이 Playwright로 실검증되고 프로덕션 빌드에 주입 코드가 없으며 무회귀다 (NFR-4 / 전 AC · 통합검증)**
**Given** 9.1 E2E 세션주입 하니스(`window.__DESKNOW_E2E__.injectSession(access,refresh)`)
**When** Playwright(MCP)로 Expo Web 빌드(:3000·`EXPO_PUBLIC_API_BASE_URL=localhost:8000`·CORS 허용 origin·시드 계정 `Test1234!`)를 구동해 9.1(로그인·탐색·검색·즐겨찾기)·9.2(룸상세·예약·예약현황·후기·배너·공유)·9.3(provider 예약자현황·거절·후기답글·룸등록[로그인 provider=백엔드 geocode 경로]·챗봇 스트리밍/RAG/예약검색/범위밖) 전 화면을 검증하면
**Then** 핵심 플로우가 통과하고(provider 검증은 **시드 provider 세션 주입**·챗봇 스트리밍은 **react-native-sse가 Expo Web XHR로 동작**해 실검증 가능), **5상태 매트릭스**(로딩 스켈레톤/에러 재시도/빈/네트워크단절"오프라인" 단어 금지/미로그인)가 일관하고, **`pnpm --filter mobile check-types`·`pnpm --filter mobile lint`(직접 fetch 가드 위반 0)** 클린하며, **프로덕션 web export(`expo export -p web`) 번들에 `__DESKNOW_E2E__`/`injectSession` 심볼 부재**(`__DEV__` dead-code 제거 재확인)이고, **백엔드/SDK/웹/admin diff 0**(음성 grep 방증). 검증 불가 항목(가입 전 WebView 지오코더·네이티브 카카오)은 명시 한계로 기록.

## Tasks / Subtasks

### A. provider 데이터 훅·순수 함수 포팅 (AC1~5 토대 — 재발명 금지)

- [x] **Task 1 — provider 순수 함수·상수 복사/추출** (AC1·2·3·4) — `apps/mobile/src/features/provider/`(신규 도메인)
  - [x] 웹 `ProviderReservations.tsx`의 `formatSlots(slotStarts:string[])`(KST "M월 D일 HH:MM–HH:MM"·`Intl` 기반 RN 호환·모듈 내부라 추출)와 `ProviderReviews.tsx`의 `formatDate(iso)`(KST "YYYY년 M월 D일")를 `provider/format.ts`(신규)로 추출 복사.
  - [x] 웹 `RoomForm.tsx`의 룸폼 순수 함수·상수 복사: `toHHMM`·`initialHours(room)`·`WEEKDAYS=["월"…"일"](월0~일6 규약)`·`AMENITY_CODES`·`ROOM_TYPES`·`type DayHours`(`{on,open,close}`). 검증 로직(`submit` 분기)도 RN 포팅 시 동일 순서.
  - [x] 웹 `useProviderRoom.ts`의 에러 분류 복사: `SaveRoomFailure`(room_limit/validation/network/unknown)·`SaveRoomError`·`classifySaveError`(409→room_limit·422→detail.message)·`toSaveRoomError`·`saveRoomErrorCopy`(카피 매핑·**프레임워크 무관 그대로**).
  - [x] **재사용(중복 복사 금지)**: 라벨·포맷은 9.1이 이미 둔 `@/features/map/roomSummary`(`AMENITY_LABELS`·`ROOM_TYPE_LABELS`·`formatPrice`·`formatHours`·`todayBusinessHours`)·커서 페이징 `@/lib/pagination`(`flattenPages`/`getNextCursorParam`)·인증 `@/features/auth/{authCopy(validateSignupCredentials·registerErrorCopy),pendingSignup,useAuth(useRegister·AuthError·classifyHttpError)}` import. provider 에러 분기는 9.2 `@/features/reservation/errors`(`errorDetailCode`) 패턴 재사용.
- [x] **Task 2 — provider React Query 훅 미러** (AC1·2·3·4·5) — `apps/mobile/src/features/provider/`
  - [x] `useProviderReservations.ts`(웹 미러 — `useInfiniteQuery`·`PROVIDER_RESERVATIONS_QUERY_KEY=["provider","reservations"]`·`reservationsListProviderReservations({query:{cursor}})`·`select:flattenPages`)+`useRejectReservation`(`reservationsRejectReservation({path:{reservation_id}})`·옵티미스틱 없음·onSuccess `["provider","reservations"]` invalidate).
  - [x] `useProviderRoom.ts`(웹 미러 — `useMyRoom`:`MY_ROOM_QUERY_KEY=["rooms","mine"]`·`roomsGetMyRoom`·**404→null 정규화**(미등록=생성 모드)·`useGeocode`:`roomsGeocodeAddress`·`useSaveRoom(existingRoomId)`:존재 시 `roomsUpdateRoom` PATCH/신규 `roomsCreateRoom` POST·옵티미스틱 없음·onSuccess `["rooms","mine"]` invalidate).
  - [x] `useProviderReviews.ts`(웹 미러 — `useMyRoom`에서 roomId 획득·`useInfiniteQuery`·`roomReviewsKey(roomId)=["rooms",roomId,"reviews"]`(9.2 `@/features/detail/useRoomReviews`와 **동일 키·캐시 공유**)·`reviewsListRoomReviews({path:{room_id},query:{cursor}})`·`enabled:roomId!==""`)+`useReplyToReview(roomId)`(`reviewsCreateReply({path:{review_id},body:{text}})`·옵티미스틱 없음·onSuccess `["rooms",roomId,"reviews"]` invalidate).
  - [x] **키 정합 필수**: provider 예약현황 `["provider","reservations"]`·내 룸 `["rooms","mine"]`·후기 `["rooms",roomId,"reviews"]`를 웹과 동일 컨벤션으로(architecture.md L275 키 규약·`["rooms"]` 광역 invalidate 금지).

### B. provider 예약자현황 + 예약 거절 화면 (AC1·2)

- [x] **Task 3 — 예약자현황 라우트·화면** (AC1) — `apps/mobile/src/app/provider/reservations.tsx`(신규·ProviderGuard 적용) + `apps/mobile/src/features/provider/ProviderReservations.tsx`(신규)
  - [x] 웹 `ProviderReservations` 미러: `useProviderReservations`→`FlatList`(`onEndReached`+`ListFooterComponent`). 행=익명 라벨(`booker_label`)·상태 배지(확정/거부됨/취소됨·색+텍스트)·시간범위(`formatSlots`). 5상태=`@/features/list/ListStates`(`InfoCard`/`RetryCard`)·`@/components/NetworkNotice`(9.1)·미로그인 가드. 헤더/설명 카피 verbatim.
- [x] **Task 4 — 예약 거절(2단 확인) 행** (AC2) — `ProviderReservations.tsx` 내 `ReservationRow`(웹 동형)
  - [x] 웹 `ReservationRow` 2단 확인 미러: "예약 거부"→확인 카피("이 예약을 거부하면…거부할까요?")→"거부"/"취소". `useRejectReservation.mutate(reservationId)`·진행 "처리 중…"·실패 "거부에 실패했어요…". 거절 버튼=`status==="confirmed"`에만. **에러코드 화면 노출 금지**(409 분기는 §deferred·웹 패리티로 단일 카피 유지).

### C. provider 후기 답글 화면 (AC3)

- [x] **Task 5 — 후기 답글 라우트·화면·폼** (AC3) — `apps/mobile/src/app/provider/reviews.tsx`(신규·ProviderGuard) + `apps/mobile/src/features/provider/ProviderReviews.tsx`·`ReviewReplyForm.tsx`(신규)
  - [x] 웹 `ProviderReviews`/`ReviewCard` 미러: `useProviderReviews`→후기 목록(`FlatList`). 카드=별점(**9.2 `@/features/detail/StarRating` 재사용**)·텍스트·`formatDate`·답글 있으면 "사장님 답글" read-only(9.2 `ReviewSection` 답글 렌더와 일관)/없으면 `ReviewReplyForm`.
  - [x] `ReviewReplyForm`(RN `TextInput multiline`·웹 `textarea` 대체·`maxLength=500`): `useReplyToReview(roomId).mutate({reviewId,text})`·placeholder "답글을 남겨보세요(최대 500자)"·"답글 등록"/"등록 중…"·실패 "등록에 실패했어요."(웹 verbatim). 룸 없음/빈/로딩/에러 카피 verbatim.

### D. provider 룸 등록·수정 + 지오코딩 + 원자 가입 (AC4)

- [x] **Task 6 — 룸폼 본체** (AC4) — `apps/mobile/src/app/provider/room.tsx`(9.1 스텁 교체·ProviderGuard) + `apps/mobile/src/features/provider/RoomForm.tsx`(신규)
  - [x] 웹 `RoomForm`/`RoomFormInner`/`ExistingRoomForm` 미러: mount 1회 `getPendingSignup()` 캡처→pending 모드(가입 전 신규)/없으면 `useMyRoom` prefill(수정) 또는 신규. 필드=이름·주소검색(Task7)·수용(숫자)·시간당 금액(숫자)·룸형태(`SegmentedControl`/`ComboSelect`)·부대시설(체크 토글)·영업시간(Task8)·제출. HTML 폼 컨트롤(`input[number/time/checkbox]`·`textarea`)을 RN(`TextInput`/`Pressable`/커스텀 시간 선택)으로 포팅. 검증 순서·카피 verbatim(이름/주소/수용/금액/룸형태/영업요일/종료>시작). `next/navigation`→`expo-router`. `lucide-react`(MapPin/Search)→RN 아이콘/텍스트.
  - [x] 저장=`useSaveRoom`→성공 시 provider 홈·`["rooms","mine"]` invalidate. 1룸 409=`saveRoomErrorCopy(room_limit)`·422=서버 message·network 카피. 제출 라벨 pending/수정/신규 분기.
- [x] **Task 7 — 주소 검색·지오코딩(2경로)** (AC4·§범위 2) — `apps/mobile/src/features/provider/{useGeocodeAddress.ts,GeocoderWebView.tsx}`(신규)
  - [x] **로그인 경로**: `useGeocode`(Task2)→`roomsGeocodeAddress`(SDK·Bearer·Expo Web 동작). 결과 필터 `admin_dong_code` 있는 것만(`usable`)·`noResults`/`noUsable` 구분·카피 verbatim("검색 결과가 없어요…"/"번지까지 포함한…도로명만으로는 등록할 수 없어요."/"주소 검색에 실패했어요…").
  - [x] **가입 전(pendingSignup) 경로**: `GeocoderWebView`(9.1 `buildMapHtml`/`MapWebView` WebView 패턴 재사용·신규 lean 래퍼) — `services` 라이브러리 로드 카카오 SDK HTML에서 `kakao.maps.services.Geocoder().addressSearch(query, cb)`→결과를 백엔드 `GeocodeResult` 형상(`address`/`lat`(y)/`lng`(x)/`admin_dong_code`(b_code))으로 통일해 `postMessage`로 RN 회신. 키=`EXPO_PUBLIC_KAKAO_JS_KEY`·baseUrl origin 화이트리스트(9.1 `KAKAO_WEBVIEW_ORIGIN` 동형). **Expo Web degrade**(맵 동형·"주소 검색을 불러오지 못했어요" graceful)→AC9 가입 전 경로 검증 불가 인지. 분기=`pendingSignup ? GeocoderWebView : useGeocode`(웹 `runGeocode` 동형).
  - [x] 선택 주소 미리보기는 9.2 `@/features/detail/RoomLocationMap`(단일 핀 미니지도) 재사용 가능(선택).
- [x] **Task 8 — 영업시간 입력 + 원자 가입** (AC4) — `RoomForm.tsx` 내 영업시간 섹션 + 제출 분기
  - [x] 영업시간=`DayHours[]`(7요일·월0~일6)·요일별 on 토글+open/close 시간 선택(RN — `<input type=time>` 대체: 시간 휠/모달/텍스트 마스크 중 택1·탭타겟≥44)·휴무 표시. 제출 시 `on` 요일만 `{weekday,open_time:"${open}:00",close_time}` 변환·0개="영업하는 요일을 하나 이상 선택해 주세요."·역전="영업 종료 시각은 시작 시각보다 늦어야 해요."(자정넘김 거부=백엔드 CHECK 미러).
  - [x] **원자 가입**(pendingSignup 모드): `register.mutate({email,password,role:"provider"},{onSuccess:()=>save.mutate(payload,{onSuccess:()=>{clearPendingSignup();goProvider();}})})` 순차(register→자동 login→룸 생성). register 실패(409 `이미 가입된 이메일이에요.`·`registerErrorCopy`) 시 룸 미생성. pending 안내 "이 정보를 등록하면 회원가입이 함께 완료돼요."·경고("등록 전에 나가면 가입되지 않아요" 동형).

### E. ProviderGuard + 역할 네비게이션 (AC5)

- [x] **Task 9 — ProviderGuard 포팅** (AC5·§범위 4) — `apps/mobile/src/features/provider/ProviderGuard.tsx`(신규)
  - [x] 웹 `ProviderGuard` 미러: `useSession`(역할)·`useOnlineStatus`·mount 1회 `getPendingSignup()` 캡처. 판정 `settled = !pending && !sessionLoading && !sessionError && isOnline`·미로그인→`/login?next=<encodeURIComponent(pathname)>`(expo-router)·잘못된 역할→`/`·**pendingSignup 통과**(provider 신규 미로그인 허용). 로딩 스켈레톤·판별실패 "로그인 상태를 확인하지 못했어요."+재시도·콜드 단절 `NetworkNotice`. `/provider/{reservations,reviews,room}` 라우트를 가드로 감쌈(공통 래퍼 또는 각 화면 진입 가드).
- [x] **Task 10 — 역할조건부 네비게이션** (AC5·§범위 4) — `apps/mobile/src/app/(tabs)/_layout.tsx`·`apps/mobile/src/components/app-tabs.tsx`(수정) 또는 신규 provider 탭/진입
  - [x] 웹 `AppNav`/`useNavItems` 미러: `session?.role==="provider"`면 provider 메뉴(예약자 현황 `/provider/reservations`·후기 `/provider/reviews`·내 스터디룸 `/provider/room`), booker면 기존 3탭(찾기·예약현황·즐겨찾기). NativeTabs 역할조건부 렌더. **KTH 확정=역할조건부 탭 스왑**(2026-06-19).

### F. 챗봇 — deviceId·SSE 클라이언트·useChatbot 훅 (AC6·7)

- [x] **Task 11 — deviceId** (AC6) — `apps/mobile/src/features/chatbot/deviceId.ts`(신규·웹 미러)
  - [x] 웹 `deviceId.ts` 미러: `getOrCreateDeviceId`/`useDeviceId`. **`localStorage`→`@react-native-async-storage/async-storage`**(설치됨·온보딩과 동형) 키 `desknow.deviceId`. `crypto.randomUUID` 부재→**Math.random v4 폴백**(웹의 비-secure-context 폴백 복사·deviceId는 비민감). `useSyncExternalStore`(SSR 안전) 불요→`useState`+effect로 단순화. snake_case 와이어 `device_id`(서버 `thread_id=${user_id}:${device_id}`).
- [x] **Task 12 — SSE 스트리밍 클라이언트(react-native-sse)** (AC7·§범위 3) — `apps/mobile/src/features/chatbot/streamMessage.ts`(신규)
  - [x] 웹 `streamMessage.ts` 미러를 **`react-native-sse`로**: `import EventSource from "react-native-sse"`(전역 fetch 아님→eslint 가드 무관). `new EventSource(`${EXPO_PUBLIC_API_BASE_URL}/api/v1/chatbot/stream`, { method:"POST", headers:{ "Content-Type":"application/json", Authorization:`Bearer ${getAccessToken()}` }, body: JSON.stringify({message, device_id}) })`. 이벤트 리스너: `message`(`data:{"delta":...}`→`{type:"delta",text}`)·`done`(`{type:"done"}`)·`error`(`JSON.parse(data)`→`{type:"error",code,message}`)·`open`/`close`. **`StreamEvent` 타입·`parseFrame` 로직(JSON delta 추출·`event:done`/`event:error` 분기)은 웹 verbatim 복사**(react-native-sse가 프레임 분해는 하나 data JSON 파싱·done/error 의미부여는 동일 로직).
  - [x] **401 재시도**(SDK 인터셉터 SSE 미적용→수동): error/`xhrStatus===401` 시 9.1 `refreshSession()`(`@/lib/api-client`·단일-flight) 호출→성공 시 새 `getAccessToken()`로 **1회만** EventSource 재생성(무한루프 가드)·실패 시 `clearTokens`+세션 무효화. 시작 불가/단절=`STREAM_FAILED`("스트림을 시작할 수 없습니다." 내부코드→패널 `ERROR_COPY` 표시). abort=언마운트/로그아웃 시 `es.close()`. **`credentials:"include"` 절대 금지**(웹 전용·RN 무존재).
- [x] **Task 13 — useChatbot 훅** (AC6·7) — `apps/mobile/src/features/chatbot/useChatbot.ts`(신규·웹 미러)
  - [x] 웹 `useChatbot` 미러: transcript 단일출처=React Query 캐시 키 `["chatbot","messages",deviceId]`(`transcriptKey`)·`CHATBOT_KEY=["chatbot"]`·재수화 `chatbotGetTranscript({query:{device_id}})`·`enabled:isReady && !!user`·`refetchOnMount:false`/`refetchOnWindowFocus:false`(스트리밍 옵티미스틱 보존). `appendDelta`/`dropPartialAssistant`(`setQueryData` 직접 변형)·상태 플래그 `isSending`/`isStreaming`/`isError`(useMutation 미사용)·재진입 가드 `streamingRef`·`lastFailedText`. `runStream(text,isRetry)`=비-retry면 user 버블 옵티미스틱→`for await (ev of streamMessage(...))` 소비·`receivedDone`/토큰0 강등·에러 시 `dropPartialAssistant`+user 유지. `send`/`retry` 가드(미인증/스트리밍 중 no-op). **로그아웃 초기화**(`useSession` 로그인→null 전이·`wasAuthenticated` ref)=abort+`removeQueries(["chatbot"])`+`onSessionEnd`+best-effort `chatbotResetSession({query:{device_id}})`·deviceId 유지. **인증=Bearer**(웹 쿠키 `credentials:"include"` 제거)·미인증 패널 로그인 안내.

### G. 챗봇 — 패널 UI·FAB 연결·RAG/예약검색/범위밖 (AC6·8)

- [x] **Task 14 — 챗봇 패널 UI** (AC6·8) — `apps/mobile/src/features/chatbot/ChatbotPanel.tsx`·`ChatBubble.tsx`(신규)
  - [x] 웹 `ChatbotPanel` 미러를 **`@gorhom/bottom-sheet`**(웹 vaul 대체·9.1 `RoomSheet`에서 이미 사용)로: 제목 "룸메이트"·닫기(a11y "챗봇 닫기")·메시지 목록(`FlatList`/`ScrollView` 자동 하단 스크롤=`scrollToEnd`·웹 `scrollTop=scrollHeight` 대체)·입력창(`TextInput`·placeholder 인증 "메시지를 입력하세요"/미인증 "로그인 후 이용할 수 있어요")·전송 버튼(a11y "전송")·제안 칩·타이핑 인디케이터(sr-only "답변을 준비하고 있어요"→`AccessibilityInfo.announceForAccessibility`)·"다시 보내기"(error)·미로그인 안내("로그인하면 룸메이트와 대화할 수 있어요."+"로그인하기"→`/login?next=/`). `aria-live`/`role=alert`→RN a11y props. `lucide-react`(MessageCircle)→RN 아이콘/이모지·`next/link`→`expo-router`.
  - [x] **내부 링크 화이트리스트**: 웹 `renderAssistantContent`/`linkifyBarePaths`의 **정규식 상수 `INTERNAL_HREF_RE`·`MD_LINK_RE`·`BARE_PATH_RE` verbatim 복사**(`/rooms/{uuid}`·`/`·`/?view=list&sigungu=&dong=`만 허용). assistant content를 노드 분해해 화이트리스트 링크만 `Pressable`→`router.push`로 렌더(비-내부 비링크). 첫 진입 인사·`ERROR_COPY`("잠깐 답이 막혔어요…")·`SUGGESTION_CHIPS`("환불 규정?"/"강남 오후 3시 빈 방") verbatim.
- [x] **Task 15 — FAB 슬롯 연결** (AC6) — `apps/mobile/src/components/ChatbotFabSlot.tsx`(no-op 스텁 교체)
  - [x] `onPress={() => {}}`(현 no-op)을 **패널 오픈**으로 교체: 로컬 `open` state→`ChatbotPanel` 마운트·`deviceId`·`onSessionEnd:()=>setOpen(false)`. FAB 위치/zIndex/그림자(`elevation.fab`)·a11y "룸메이트 챗봇 열기" 보존(`_layout.tsx:62` 루트 마운트=네비 가로질러 상태 보존). 운영 빌드 디버그 로그 금지(스텁 주석 준수).

### H. 게이트 & E2E 통합검증 & 무회귀 (AC9)

- [x] **Task 16 — eslint/타입/lint 게이트** (AC9) — `apps/mobile/`
  - [x] `pnpm --filter mobile check-types`(tsc --noEmit)·`pnpm --filter mobile lint`(expo lint·직접 fetch 가드 위반 0) 클린. 백엔드 호출 전부 `@/lib/api-client` SDK 경유(provider·후기답글·룸·geocode)·챗봇 SSE는 `react-native-sse EventSource`(전역 fetch 아님→가드 무관·raw fetch 택 시 chatbot 1파일 allowlist 추가). 신규 라우트 typed-routes 캐스트(`as Href`) 9.1 패턴.
- [x] **Task 17 — Playwright(MCP) 9.1~9.3 전화면 통합검증** (AC9·전 AC) — Expo Web 빌드
  - [x] 9.1 E2E 하니스 재사용(`window.__DESKNOW_E2E__.injectSession(access,refresh)`)·Expo Web :3000·`EXPO_PUBLIC_API_BASE_URL=localhost:8000`·CORS 허용 origin(9.2 검증 구성 재사용)·시드 계정 `Test1234!`([[e2e-seed-accounts-and-data]]).
  - [x] **provider 검증**=시드 **provider 세션 주입**으로 예약자현황(익명 라벨·무한스크롤)·예약 거절(2단 확인→배지 갱신)·후기 답글 작성→read-only 전환·룸 등록/수정(**로그인 provider=백엔드 geocode 경로**·영업시간·1룸 409)·ProviderGuard(미로그인/잘못된 역할 리다이렉트)·역할 네비 스왑.
  - [x] **챗봇 검증**(react-native-sse Expo Web XHR 동작): FAB→패널·메시지 전송→SSE 스트리밍(타이핑 인디케이터·토큰 누적)·RAG 안내·자연어 예약검색(룸 링크 화이트리스트)·범위밖 거절·미로그인 안내·세션 대화 유지·로그아웃 초기화.
  - [x] **9.1·9.2 무회귀 스팟체크**(전화면 통합) + 검증 불가 항목(가입 전 WebView 지오코더·네이티브 카카오) 명시 기록.
- [x] **Task 18 — 프로덕션 번들·무변경 확인** (AC9) — `apps/mobile/`·무변경 grep
  - [x] `expo export -p web` 프로덕션 번들 grep으로 `__DESKNOW_E2E__`/`injectSession`/e2e-session 심볼 **부재** 재확인(`__DEV__` dead-code 제거·9.1 AC7 회귀).
  - [x] **무변경 확인**: `apps/api`·`packages/api-client/src/generated`·`apps/web`·`apps/admin` diff 0(NO_VCS→음성 grep: web/admin 소스에 9.3 누출 0). **신규 의존성 0**(react-native-sse·@gorhom/bottom-sheet·async-storage·webview 전부 9.1 설치필·재설치 금지); 부득이 추가 시 §library 실측.

## Dev Notes

### 이 스토리의 본질

9.3은 **9.1·9.2 파운데이션 위에 모바일 패리티의 마지막 두 도메인(provider·챗봇)을 얹고 Epic 9를 통합검증으로 닫는** 스토리다. 9.1이 인증 스택·WebView 지도·E2E 하니스·`pendingSignup`·`refreshSession`을, 9.2가 후기 표시(`ReviewSection`·`StarRating`·`useRoomReviews`)·`errors.ts`·`pagination`·`ListStates`/`NetworkNotice`를 세웠으므로 9.3은 **순수 클라이언트 작업**이고 **백엔드/SDK/웹/admin 변경 0**이다. 가장 큰 통찰: **provider 데이터 로직(예약현황·거절·답글·룸저장)·룸폼 검증·에러분류·챗봇 transcript 관리·SSE 프레임 의미부여가 거의 전부 프레임워크 무관 순수 함수·React Query 훅(SDK+키)**이라 복사·미러로 재사용하고, 포팅이 필요한 건 ① JSX(provider 화면·룸폼·챗봇 패널) ② **두 진짜 갭**뿐이다 — (a) 가입 전 카카오 JS Geocoder(`window` 부재→WebView), (b) `fetch` ReadableStream SSE+쿠키(→`react-native-sse`+Bearer). (b)는 **9.1이 이미 `react-native-sse`를 설치**해 두었고 인증은 Bearer로 갈아끼우면 끝이다. **provider 후기 답글·모바일 챗봇은 deferred 의무 회수 트리거**(아래 §deferred)다.

### ★재사용 자산 인벤토리 (재발명 금지 — 웹 미러/순수함수 복사 / 9.1·9.2 기존 재사용)

**그대로 복사/추출(프레임워크 무관 순수 함수·상수 — `apps/web/src/features/provider|chatbot/` → `apps/mobile/src/features/provider|chatbot/`):**

| 자산 | 웹 경로 | 핵심 export/내용 |
|------|---------|------------------|
| 룸 저장 에러 분류 | `provider/useProviderRoom.ts` | `SaveRoomFailure`·`classifySaveError`(409→room_limit·422→detail.message)·`toSaveRoomError`·`saveRoomErrorCopy`(1룸 409 카피) |
| 룸폼 상수·변환 | `provider/RoomForm.tsx`(추출) | `WEEKDAYS`(월0~일6)·`AMENITY_CODES`·`ROOM_TYPES`·`DayHours`·`toHHMM`·`initialHours`·검증 순서 |
| provider 포맷터 | `ProviderReservations.tsx`·`ProviderReviews.tsx`(추출) | `formatSlots`(KST 시간범위)·`formatDate`(KST 날짜) |
| 챗봇 SSE 파서 | `chatbot/streamMessage.ts` | `StreamEvent` 타입·`parseFrame`(data JSON delta·`event:done`/`error` 분기·`STREAM_FAILED`) |
| 챗봇 transcript 키 | `chatbot/useChatbot.ts` | `transcriptKey(deviceId)=["chatbot","messages",deviceId]`·`CHATBOT_KEY=["chatbot"]` |
| 챗봇 deviceId | `chatbot/deviceId.ts` | `getOrCreateDeviceId`·UUID v4 폴백(localStorage→AsyncStorage 교체) |
| 링크 화이트리스트 | `chatbot/ChatbotPanel.tsx`(상수) | `INTERNAL_HREF_RE`·`MD_LINK_RE`·`BARE_PATH_RE`(룸 링크 화이트리스트) |
| 카피 상수 | `ChatbotPanel.tsx` | `SUGGESTION_CHIPS`·`ERROR_COPY`·인사·placeholder verbatim |

**거의 그대로 미러(React Query 훅 — SDK+키만·UI 무관, 웹→모바일 신규):**

| 훅 | 웹 경로 | SDK·키 |
|----|---------|--------|
| `useProviderReservations`/`useRejectReservation` | `provider/useProviderReservations.ts` | `reservationsListProviderReservations`/`reservationsRejectReservation`·`["provider","reservations"]` |
| `useMyRoom`/`useGeocode`/`useSaveRoom` | `provider/useProviderRoom.ts` | `roomsGetMyRoom`(404→null)·`roomsGeocodeAddress`·`roomsCreateRoom`/`roomsUpdateRoom`·`["rooms","mine"]` |
| `useProviderReviews`/`useReplyToReview` | `provider/useProviderReviews.ts` | `reviewsListRoomReviews`/`reviewsCreateReply`·`["rooms",roomId,"reviews"]`(룸상세와 공유) |
| `useChatbot`(+`streamMessage`) | `chatbot/useChatbot.ts` | `chatbotGetTranscript`/`chatbotResetSession`+SSE·`["chatbot","messages",deviceId]` |

**9.1·9.2가 이미 모바일에 둠 — 재사용(중복 복사·재발명 금지):**

| 자산 | 모바일 경로 | 9.3 용도 |
|------|-------------|----------|
| SDK 단일진입+Bearer 인터셉터+`refreshSession` | `@/lib/api-client`(`refreshSession` export·401 재시도) | provider SDK 호출·챗봇 SSE 401 수동 재시도 |
| 토큰 저장소 | `@/lib/session-store`(`getAccessToken`) | 챗봇 SSE Bearer 헤더 |
| 세션 단일출처·역할 | `@/features/auth/useSession`(`["auth","me"]`·`UserPublic.role`) | ProviderGuard·역할 네비·챗봇 `enabled:!!user`·로그아웃 초기화 |
| 인증 카피·검증·pendingSignup·register | `@/features/auth/{authCopy,pendingSignup,useAuth}` | provider 원자 가입(`validateSignupCredentials`·`registerErrorCopy`·`useRegister`) |
| E2E 하니스 | `@/lib/e2e-session`(`window.__DESKNOW_E2E__.injectSession`) | AC9 provider 세션 주입 검증 |
| WebView 카카오 패턴 | `@/features/map/{mapHtml(buildMapHtml),MapWebView}`(`KAKAO_WEBVIEW_ORIGIN`) | 가입 전 지오코더 WebView(lean 신규) |
| 후기 표시·별점·훅 | `@/features/detail/{StarRating,ReviewSection,useRoomReviews(roomReviewsKey)}` | provider 후기 화면 별점·답글 read-only·동일 키 |
| 에러 판별 | `@/features/reservation/errors`(`errorDetailCode`) | provider 에러 detail.code 분기 헬퍼 |
| 커서 페이징 | `@/lib/pagination`(`flattenPages`/`getNextCursorParam`) | provider 예약현황·후기 무한스크롤 |
| 5상태·단절·온라인 | `@/features/list/ListStates`·`@/components/NetworkNotice`·`@/lib/useOnlineStatus` | 전 화면 상태 매트릭스·ProviderGuard |
| 토글·콤보·미니지도 | `@/components/{SegmentedControl,ComboSelect}`·`@/features/detail/RoomLocationMap` | 룸폼 룸형태·주소 미리보기 |
| 디자인 토큰·테마 | `@/constants/theme`(`Colors.light`/`Spacing`/`Radius`)·`ThemedText`/`ThemedView` | 라이트 단일 테마 |

**폐기·교체(웹 전용·RN 무존재):**

| 웹 자산 | 이유 | 모바일 대체 |
|---------|------|-------------|
| `streamMessage.ts`(`fetch`+ReadableStream+`getReader`+`TextDecoder`+`credentials:"include"`) | RN 스트리밍/쿠키 무존재 | **`react-native-sse` EventSource**(POST+body+Bearer)·`refreshSession` 401 수동 재시도 |
| `ChatbotFabSlot.tsx`·`ChatbotPanel.tsx`(vaul drawer·`lucide-react`·`next/link`·Tailwind·DOM `form.elements`·`scrollTop`) | 웹 UI | **`@gorhom/bottom-sheet`**(9.1 RoomSheet 동형)·RN `TextInput`/`FlatList scrollToEnd`/`Pressable`·a11y props |
| `deviceId.ts`(`window.localStorage`·`crypto.randomUUID`·`useSyncExternalStore`) | RN 무존재 | `AsyncStorage`·Math.random v4 폴백·`useState`+effect |
| `RoomForm.tsx geocodeViaKakaoJs`/`lib/kakao-map.ts`(`window.kakao` JS Geocoder·`<script>`) | `window`/`document` 무존재 | WebView 카카오 Geocoder(가입 전)·백엔드 geocode(로그인) |
| `RoomLocationMap`(웹 카카오 JS Map)·`StarRating`(웹 `lucide Star`)·`InfiniteScrollSentinel`(IntersectionObserver) | 웹 플랫폼 | 9.2 RN `RoomLocationMap`/`StarRating`·`FlatList onEndReached` |
| `ProviderGuard`/`AppNav`(`next/navigation`·Tailwind) | 웹 라우팅 | `expo-router`·RN 네비 |
| SDK `credentials:"include"`(쿠키) | RN 무존재 | Bearer 헤더(9.1 인터셉터·챗봇은 수동) |

### 두 진짜 갭 — 결정과 처리

**갭① 가입 전 지오코딩(§범위 2·KTH 확정).** 웹은 로그인 provider=백엔드 `roomsGeocodeAddress`(provider 전용), 가입 전 `pendingSignup`=카카오 JS Geocoder 직접(백엔드 geocode를 못 써서). RN엔 `window.kakao`가 없다. **권장=9.1 WebView 패턴 재사용**(가입 전만 `services` 라이브러리 WebView Geocoder·결과 postMessage 회신)으로 **KTH 기존 결정([[provider-signup-deferred-and-geocode]])과 백엔드 무변경을 동시 보존**. 트레이드오프: Expo Web은 webview 미지원이라 **가입 전 지오코딩은 Playwright 검증 불가**(맵 degrade와 동형)→AC9는 로그인 provider 경로(백엔드 geocode·Expo Web 동작)로 룸등록 실검증. 대안=백엔드 geocode 게이트를 가입 전에도 허용(백엔드 변경·보안자세 변동)=비권장. → **KTH 확정**(2026-06-19·권장안 채택·Change Log).

**갭② 챗봇 SSE 전송(§범위 3·prescribed).** 웹 `streamMessage.ts`는 레포 유일 raw `fetch`+ReadableStream+`credentials:"include"`(쿠키). RN(Hermes)은 스트리밍 ReadableStream이 불안정→**9.1이 이미 설치한 `react-native-sse@^1.2.1`**(POST+body+Bearer 지원)로 대체. **인증=쿠키→Bearer**(`getAccessToken` 헤더)·**401 수동 재시도**(`refreshSession` 1회·SDK 인터셉터가 SSE 경로를 안 타므로). `react-native-sse EventSource`는 **별도 import라 eslint 직접-fetch 가드 무관**(allowlist 불요·raw fetch 택 시 chatbot 1파일 allowlist). **`react-native-sse`는 web에서 XHR로 동작**→챗봇 스트리밍은 **맵/지오코더와 달리 Expo Web Playwright 검증 가능**(AC9 강한 검증 대상). 이건 권장이 충분히 명확해 prescribed.

### 신선도·상태·동시성·키 계약 (반드시 준수)

- **invalidate 정확 키만**(architecture.md L275-276): provider 예약현황 `["provider","reservations"]`·내 룸 `["rooms","mine"]`·후기 `["rooms",roomId,"reviews"]`(룸상세 `useRoomReviews`와 **동일 키·캐시 공유**·답글 작성 후 정확 invalidate). `["rooms"]` 광역 invalidate 금지. 챗봇 `["chatbot","messages",deviceId]`·로그아웃 시 `["chatbot"]` 프리픽스 제거.
- **옵티미스틱 경계**(architecture.md L277): provider 거절·후기 답글·룸 저장·**예약 거절은 전부 옵티미스틱 없음**(서버 확인 후). 챗봇은 **user 버블만 옵티미스틱**(전송 즉시 표시)·assistant는 스트리밍 누적(setQueryData 직접 변형이나 서버 토큰 그대로).
- **익명 라벨**([[anonymous-booker-label-no-display-name]]): provider 예약현황의 예약자는 백엔드 sha256 파생 `booker_label`("예약자 #a3f9c1")만. **클라 해시 금지**·이메일/raw UUID 비노출. 와이어 `booker_label` 그대로.
- **거절 원자성**(6.2): 서버가 `confirmed→rejected` 전이+슬롯 DELETE 재활성+예약자 통지를 동일 트랜잭션 처리. 클라는 결과만. 시작 후 거절 409 `REJECT_WINDOW_PASSED`(웹 미분기·패리티 유지).
- **챗봇 LangGraph 롤백**([[langgraph-failed-turn-input-rollback]]): 노드 실패 시 서버가 thread 입력을 RemoveMessage로 롤백→클라는 **부분 assistant만 정리·user 버블 유지**(재전송 중복 방지). `done` 없는 종료·토큰0=절단으로 강등.
- **신선도**([[availability-freshness-policy]]): 룸 prefill `useMyRoom`·후기 목록은 표준 React Query. 챗봇 transcript는 `refetchOnMount:false`(스트리밍 옵티미스틱 캐시를 재수화가 덮지 않게).

### 반복 함정 프리플라이트 ([[dev-workflow-policy-deferred-and-repeat-mistakes]])

1. **재발명 금지** — provider/챗봇 로직은 웹 순수함수·훅을 **복사/미러**. 9.1·9.2가 둔 `useSession`/`pendingSignup`/`useRegister`/`refreshSession`/`StarRating`/`useRoomReviews(roomReviewsKey)`/`ReviewSection`/`errors`/`pagination`/`ListStates`/`NetworkNotice`/`buildMapHtml`/`SegmentedControl`/`ComboSelect`/`RoomLocationMap`/테마는 **재사용**(중복 복사 금지).
2. **직접 fetch 금지** — provider 백엔드 호출 전부 `@/lib/api-client` SDK(`reservations*`/`reviews*`/`rooms*`/`roomsGeocodeAddress`). **챗봇 SSE만 예외** — `react-native-sse EventSource`(전역 fetch 아님→가드 무관)·raw fetch 택 시 chatbot 1파일 allowlist(웹 `eslint.config.mjs` `streamMessage.ts` off 패턴 동형). WebView 지오코더는 RN 주입 데이터만(직접 호출 안 함).
3. **에러코드 화면 노출 금지** — 거절 409·답글 409/403·룸 409/422는 코드를 분기에만, 화면엔 친절 카피. (웹은 거절/답글 409를 단일 카피로만 처리→**패리티 유지**, 친절 분기는 §deferred 웹+모바일 동시.)
4. **네트워크 단절 카피** — "오프라인" 금지·"네트워크 연결이 끊겼어요…"([[terminology-network-disconnect-not-offline]]). 단절>에러 우선.
5. **용어 "지역"** — 룸폼 주소·동 표기에 "행정동/법정동" 금지·"지역"만([[region-code-legal-not-admin-dong]]). 데이터 식별자 `admin_dong_code`/`b_code`는 영문만.
6. **snake_case 와이어 보존** — `room_id`/`reservation_id`/`review_id`/`booker_label`/`slot_starts`/`admin_dong_code`/`price_per_hour`/`room_type`/`business_hours`/`open_time`/`close_time`/`weekday`(월0~일6)/`next_cursor`/`device_id`/`thread_id`/`access_token`/`refresh_token`/`delta` 그대로(camelCase 변환 금지).
7. **옵티미스틱 경계** — 거절·답글·룸저장=옵티미스틱 없음. 챗봇 user 버블만 옵티미스틱.
8. **invalidate 정확 키·후기 키 공유** — `["rooms",roomId,"reviews"]`는 룸상세와 공유(답글 작성 후 양쪽 갱신). 챗봇 `["chatbot"]` 프리픽스 독립.
9. **지도/WebView origin·degrade**(9.1 함정 상속) — 지오코더 WebView 키=`EXPO_PUBLIC_KAKAO_JS_KEY`·baseUrl 화이트리스트. Expo Web degrade 정상(검증 시 인지).
10. **provider 원자 가입** — register 선성공 후에만 룸 생성(떠도는 계정 방지). register 실패 시 룸 미생성·`registerErrorCopy`.
11. **library 실측** — **신규 의존 0**(react-native-sse·@gorhom/bottom-sheet·async-storage·webview·react-query 전부 9.1 설치필·재설치 금지). 부득이 추가 시 실제 패키지/버전 확인(환각 금지).
12. **챗봇 인증=Bearer(쿠키 아님)** — `credentials:"include"` 절대 금지(RN 무존재). `getAccessToken` 헤더·`refreshSession` 401.
13. **python(=python3 아님)·uv --no-sync**(API 재기동 필요 시) — 9.3은 백엔드 무변경이라 대개 무관([[python-command-use-python-not-python3]]·[[uv-run-no-sync-when-api-running]]).

### deferred 후보·회수 (회수 트리거)

- **[회수 트리거·의무] 모바일 챗봇(FAB 실동작·대화 패널·세션)** — 7.3 forward note(deferred-work.md:59)가 "모바일 인증 스택 부재+화면 placeholder"로 "모바일 dev-build 푸시" 버킷 보류한 항목. **9.1이 인증 스택(useSession·QueryClientProvider·secure-store Bearer)을, 9.2가 화면을 세워 전제 충족 → 회수 트리거 발동**([[dev-workflow-policy-deferred-and-repeat-mistakes]] 의무 회수). 9.3이 RN 챗봇 UI(deviceId·useChatbot·ChatbotPanel·SSE) 구현으로 **전량 회수**. BE는 웹·모바일 공용이라 재구현 불요.
- **[회수 트리거·의무] 모바일 후기 답글(provider)** — 5.6/5.5 forward note(deferred-work.md:72)가 "모바일 예약/상세 화면 미구현"으로 보류. 9.2가 룸상세 `ReviewSection`(답글 read-only)을 세워 전제 충족 → 9.3이 **답글 작성**(`useReplyToReview`)으로 회수.
- **[패리티 동시 후보] 거절/답글 409 친절 분기** — 웹 `useRejectReservation`/`useReplyToReview`가 409(`REJECT_WINDOW_PASSED`·`REVIEW_REPLY_ALREADY_EXISTS`)·403을 단일 카피로만 처리(detail.code 미분기). 9.3은 **웹 패리티로 단일 카피 유지**·친절 분기 도입 시 [[web-mobile-parity-on-changes]]로 웹+모바일 동시 적용(현 스토리 범위 밖).
- **[9.1 상속·결정 대기] WebView 카카오 origin 하드코딩·SDK 로드 워치독 부재** — 지오코더 WebView가 `buildMapHtml` 패턴 재사용 시 동일 갭 상속(deferred-work.md WebView origin 항목). 네이티브 하드닝 시 origin env화(`EXPO_PUBLIC_KAKAO_WEBVIEW_ORIGIN`)+로드 타임아웃 워치독 함께 회수.
- **[모바일 dev-build 버킷·보류 유지] 네이티브 카카오 공유(`@react-native-kakao/share`)·가입 전 WebView 지오코더 네이티브 렌더** — EAS dev-build+네이티브 키 필요·Expo Web/Playwright 검증 불가. 9.2가 RN `Share`로 공유 진입점은 회수했고, 정확 템플릿 카카오 모듈만 보류 유지(재-defer 아님·검증 불가 인프라 의존).
- **[배포 의존] 카카오 콘솔 WebView origin 프로드 등록·후기 공개조회 페이지네이션/레이트리밋·챗봇 MemorySaver 영속화** — 배포/스케일 스토리 소유(deferred-work.md:73,367·[[deployment-first-time-checklist]]). 9.3 무관.
- **E2E 통합 깊이** — 9.3이 9.1~9.3 전화면 Playwright 통합검증을 완결(Epic 9 마지막). 검증 불가 항목(가입 전 WebView 지오코더·네이티브 카카오) 명시 한계.

### 스코프 경계 (인접 스토리·도메인 — 침범 금지)

| 9.3 소유 | 인접 소유(건드리지 말 것) |
|----------|---------------------------|
| provider 4화면(예약자현황·거절·후기답글 **작성**·룸등록/수정)·ProviderGuard·역할 네비·플로팅 챗봇(SSE·세션·RAG/예약검색/범위밖)·9.1~9.3 통합 Playwright | 9.1(인증·탐색·검색·즐겨찾기·WebView 지도·E2E 하니스)·9.2(룸상세·예약·예약현황·후기 **표시/작성**·배너·공유) = **재사용**(무수정) |
| `provider/{room,reservations,reviews}` 라우트·`ChatbotFabSlot` 내부·`features/{provider,chatbot}` | 9.2 `features/{reservation,detail,notifications}`·9.1 `features/{auth,map,list,favorites}` = 재사용 |
| 챗봇 SSE 클라(react-native-sse·Bearer)·deviceId(AsyncStorage)·링크 화이트리스트 | BE 챗봇(graph·prompts·service·router)·SSE 엔드포인트·멀티 LLM = **무변경**(웹·모바일 공용) |
| 가입 전 WebView 지오코더(degrade)·로그인 백엔드 geocode | 네이티브 카카오 공유·WebView origin env화 = **모바일 dev-build 버킷** |
| 클라이언트(모바일)만 | 백엔드·SDK·웹·admin = **무변경**(diff 0) |

## References

- [Source: _bmad-output/planning-artifacts/epics.md L242-246(Epic 9 개요)·L1303-1322(Story 9.3 AC)] — provider·챗봇·E2E 통합검증
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-06-19.md L112-117(9.3 범위)·L51-56·L123-126(신규 아키텍처 결정 3건)] — Epic 9 신설·secure-store/지도/E2E
- [Source: _bmad-output/implementation-artifacts/9-1-모바일-인증-탐색-검색.md] — 파운데이션(인증 스택·`refreshSession`·`pendingSignup`·WebView 카카오 패턴·E2E 하니스 `injectSession`)·재사용 자산·provider/room 스텁 seam·9.1 defer 상속
- [Source: _bmad-output/implementation-artifacts/9-2-모바일-예약-예약후경험.md] — `ReviewSection`(답글 read-only)·`StarRating`·`useRoomReviews(roomReviewsKey)`·`errors.ts`·`RoomLocationMap`·검증 환경(Expo Web :3000·CORS·시드)·의도 편차
- [Source: _bmad-output/planning-artifacts/architecture.md L165(토큰 이원화)·L175-180(에러 표준·409)·L274-277(TanStack 키·옵티미스틱 경계)·L290(직접 fetch 금지)·L316-317·L324-326(모바일 features 구조)] — 키·동시성·인증 계약
- [Source: apps/web/src/features/provider/{ProviderReservations.tsx,useProviderReservations.ts,ProviderReviews.tsx,useProviderReviews.ts,RoomForm.tsx,useProviderRoom.ts,ProviderGuard.tsx}] — provider 4화면 미러/복사 대상(formatSlots·formatDate·classifySaveError·saveRoomErrorCopy·WEEKDAYS·initialHours·검증 순서·geocodeViaKakaoJs)
- [Source: apps/web/src/components/shell/{AppNav.tsx(PROVIDER_NAV/BOOKER_NAV/useNavItems),ChatbotFabSlot.tsx}·apps/web/src/app/provider/{layout.tsx,page.tsx,reservations/page.tsx,reviews/page.tsx,room/page.tsx}] — 역할 네비·provider 라우트·FAB
- [Source: apps/web/src/features/chatbot/{streamMessage.ts(parseFrame·StreamEvent·STREAM_FAILED·401 재시도),useChatbot.ts(transcriptKey·옵티미스틱·로그아웃 초기화),deviceId.ts(getOrCreateDeviceId·UUID 폴백),ChatbotPanel.tsx(SUGGESTION_CHIPS·ERROR_COPY·링크 화이트리스트 INTERNAL_HREF_RE/MD_LINK_RE/BARE_PATH_RE·카피)}] — 챗봇 미러/복사·SSE 갭
- [Source: apps/web/src/features/auth/{pendingSignup.ts,authCopy.ts(validateSignupCredentials),useAuth.ts(useRegister·classifyHttpError·AuthFailure),SignupView.tsx(provider 분기)}] — provider 원자 가입
- [Source: apps/web/src/lib/kakao-map.ts(loadKakaoMaps·services Geocoder)·apps/web/src/types/kakao-maps.d.ts(addressSearch·b_code)] — 가입 전 지오코더(WebView 대체 원본)
- [Source: apps/api/app/reservations/router.py(list_provider_reservations·reject_reservation·booker_display_label sha256)·reviews/router.py(create_reply·REVIEW_REPLY_*)·rooms/router.py(create_room·update_room·get_my_room·geocode_address provider 전용·ROOM_LIMIT_REACHED)·chatbot/router.py(stream_message SSE event_gen·schemas device_id 패턴)·core/errors.py(REJECT_WINDOW_PASSED·REVIEW_REPLY_ALREADY_EXISTS·ROOM_LIMIT_REACHED·EMAIL_TAKEN)] — 백엔드 계약(무변경 근거)
- [Source: @desknow/api-client(packages/api-client/src/generated) — reservationsListProviderReservations·reservationsRejectReservation·reviewsListRoomReviews·reviewsCreateReply·roomsGetMyRoom·roomsCreateRoom·roomsUpdateRoom·roomsGeocodeAddress·chatbotGetTranscript·chatbotResetSession·chatbotStreamMessage / 타입 ProviderReservationItem·ReviewListItem·ReviewReplyView·ProviderRoomDetail·RoomCreateRequest·BusinessHoursInput·GeocodeResult·ChatMessage] — SDK(무변경·전량 모바일 re-export)
- [Source: apps/mobile/{package.json(react-native-sse@^1.2.1·@gorhom/bottom-sheet·async-storage·webview 설치필),eslint.config.js(직접 fetch 가드·SSE allowlist 예고),.env(EXPO_PUBLIC_KAKAO_JS_KEY·E2E_ENABLED·API_BASE_URL),app.json(plugins)}·src/app/provider/room.tsx(9.1 스텁)·src/components/ChatbotFabSlot.tsx(no-op 스텁)·src/lib/{api-client(refreshSession),session-store(getAccessToken),e2e-session(injectSession)}] — 9.3 seam·재사용 파운데이션
- [Source: _bmad-output/implementation-artifacts/deferred-work.md L59(7.3 모바일 챗봇 회수 트리거)·L72(5.5/5.6 모바일 후기답글 회수)·L367-372(7.3 챗봇 백엔드 defer)] — 의무 회수/경계
- [Source: 메모리] [[epic9-mobile-parity-correct-course]] [[dev-workflow-policy-deferred-and-repeat-mistakes]] [[web-mobile-parity-on-changes]] [[provider-signup-deferred-and-geocode]] [[anonymous-booker-label-no-display-name]] [[langgraph-failed-turn-input-rollback]] [[chatbot-rag-tool-calling-react]] [[chatbot-rag-relevance-grade]] [[availability-freshness-policy]] [[terminology-network-disconnect-not-offline]] [[region-code-legal-not-admin-dong]] [[all-test-passwords-test1234]] [[e2e-seed-accounts-and-data]] [[decision-relay-use-selection-ui-cs-ds-cr]] [[python-command-use-python-not-python3]] [[uv-run-no-sync-when-api-running]] [[deployment-first-time-checklist]]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Claude Opus 4.8, 1M context) — dev-story 워크플로우

### Debug Log References

- typecheck(`pnpm --filter mobile check-types`): 초기 2건 → ① Windows 대소문자 충돌(`roomForm.ts` 상수 vs `RoomForm.tsx` 컴포넌트) → 상수 파일을 `roomFields.ts`로 개명 ② 신규 `/provider/*` 라우트가 typed-routes 미생성 → app-tabs.web.tsx href `as Href` 캐스트. 수정 후 **클린**.
- lint(`expo lint`): 1건 → deviceId.ts effect 내 동기 setState(`react-hooks/set-state-in-effect`) → warm-cache는 `useState` 초기값으로 충분하므로 동기 setState 제거. 수정 후 **클린**.
- Playwright(MCP) 실검증: KTH의 :3000 Expo dev 서버가 stale(신규 라우트 미인식·"Unmatched Route")이고 종료가 가드로 거부됨 → 우회 금지, **CORS 허용 포트 :3001에 별도 Expo Web 인스턴스 기동**(`EXPO_PUBLIC_API_BASE_URL=localhost:8000`)해 최신 번들 검증. 시드 provider `_pweb0@test.desknow`(마포 합정 룸 보유) 세션 주입.

### Completion Notes List

**전 9개 AC를 Expo Web(:3001) Playwright로 실검증 완료. 백엔드/SDK/웹/admin diff 0(음성 grep 확인).** 9.1·9.2 파운데이션 위에 provider 4화면·챗봇을 순수함수/훅 미러로 재사용 구현하고 Epic 9를 통합검증으로 마감.

- **AC1 예약자현황** ✓ — 익명 라벨("예약자 #53a41d")·상태 배지(확정/취소됨)·KST 시간범위(`formatSlots`)·확정 행만 거부 버튼·5상태(단절 NetworkNotice 포함). `useProviderReservations`(useInfiniteQuery·`["provider","reservations"]`).
- **AC2 예약 거절 2단 확인** ✓ — "예약 거부"→"이 예약을 거부하면…거부할까요?"+거부/취소 노출 확인(데이터 보존 위해 실 거부 대신 취소로 철회 검증). 옵티미스틱 없음.
- **AC3 후기 답글** ✓ — 답글 작성→"사장님 답글" read-only 전환 풀사이클·폼 소멸. 공유 키(`roomReviewsKey ["rooms",roomId,"reviews"]`)로 **booker 예약현황의 "내 후기"에도 동일 답글 즉시 반영**(교차 표면 캐시 공유 확인).
- **AC4 룸 등록/수정** ✓ — 수정 모드 prefill(이름·주소·수용6·금액12000·룸형태·부대시설·영업시간 월~일 09:00–22:00 ComboSelect)·"수정 저장" 라벨. **로그인 백엔드 geocode 실동작**("서울 강남구 테헤란로 152" 검색→후보+"정확한 주소를 선택해 주세요"). RN엔 `<input type=time>` 부재라 영업시간=30분 단위 ComboSelect(무효입력 방지·분 정밀). 원자 가입·1룸 409는 웹 verbatim 미러(저장은 데이터 보존 위해 미실행).
- **AC5 ProviderGuard + 역할 네비** ✓ — provider 통과·미로그인→`/login?next=%2Fprovider%2Froom`(원경로 보존)·booker→`/`(홈). 역할 네비 양방향 스왑 확인(provider=예약자현황·후기·내 스터디룸 / booker=찾기·예약현황·즐겨찾기). **6개 라우트 항상 등록 + 역할별 숨김** 패턴(pendingSignup 포함 navigable·바만 스왑).
- **AC6 챗봇 FAB·패널·세션** ✓ — FAB→@gorhom/bottom-sheet 패널(인사·제안칩·입력)·`_layout` 루트 마운트(탭 가로질러 보존)·deviceId(AsyncStorage)·로그아웃 전이 시 패널이 "로그인하면 룸메이트와 대화할 수 있어요" 게이트로 전환(transcript 초기화).
- **AC7 SSE 스트리밍** ✓ — `react-native-sse`가 Expo Web XHR로 동작·"환불 규정?"→사용자 버블+토큰 누적 스트리밍 완성. `pollingInterval:0`으로 종료 후 자동 재연결(중복 POST) 차단·401 수동 refresh 1회(무한루프 가드)·인밴드 `event:error`(`.data`) vs 전송오류(`.xhrStatus`) 구분.
- **AC8 RAG·예약검색·범위밖·링크 화이트리스트** ✓ — RAG("6시간 전 취소·결제없는 서비스라 환불 절차 없음"=service_guide grounding)·NL 예약검색(DB 툴로 룸 추천)·범위밖 거절("그건 제가 도와드리기 어려운 주제예요…"). **링크 보안 확인**: LLM이 낸 `https://www.example.com/rooms/{uuid}` 절대 URL은 `INTERNAL_HREF_RE`(상대경로만) 미매칭 → "자세히 보기" 라벨만 평문(비링크·오픈리다이렉트/XSS 차단·웹 동일).
- **AC9 통합검증·무회귀·번들** ✓ — 9.2 booker 예약현황 무회귀(다가오는/지난·6h 취소 차단·공유·후기·답글 반영). **프로덕션 web export 번들에 `__DESKNOW_E2E__`/`injectSession`/`installE2ESessionHarness` 부재**(`__DEV__` dead-code 제거). typecheck·lint 클린. **백엔드/SDK/웹/admin diff 0**(수정 파일 전부 apps/mobile 내부·음성 grep 누출 0).

**검증 불가(명시 한계):** ① 가입 전(pendingSignup) WebView 카카오 Geocoder = Expo Web은 react-native-webview 미지원(맵 degrade 동형) → 네이티브 dev-build 필요. AC9는 로그인 백엔드 geocode 경로로 룸등록 실검증으로 대체. ② RoomLocationMap 미니지도·전체화면 카카오맵 = Expo Web degrade("지도를 못 불러왔어요"). ③ 네이티브 NativeTabs 역할 스왑·네이티브 카카오 = EAS dev-build 필요(웹 expo-router/ui Tabs 경로로 검증). **신규 의존성 0**(react-native-sse·@gorhom/bottom-sheet·async-storage·webview 전부 9.1 설치필 재사용).

### File List

**신규 (apps/mobile/src/):**
- `features/provider/format.ts` — `formatSlots`·`formatDate`(KST 포맷터)
- `features/provider/roomFields.ts` — `WEEKDAYS`·`AMENITY_CODES`·`ROOM_TYPES`·`DayHours`·`toHHMM`·`initialHours`(룸폼 순수 상수·변환)
- `features/provider/useProviderReservations.ts` — `useProviderReservations`·`useRejectReservation`
- `features/provider/useProviderRoom.ts` — `useMyRoom`·`useGeocode`·`useSaveRoom`·`SaveRoomError`·`saveRoomErrorCopy`
- `features/provider/useProviderReviews.ts` — `useProviderReviews`·`useReplyToReview`(roomReviewsKey 공유)
- `features/provider/ProviderReservations.tsx` — 예약자현황 화면 + 2단 확인 거절 행
- `features/provider/ProviderReviews.tsx` — 후기 화면 + 답글 작성 폼
- `features/provider/RoomForm.tsx` — 룸 등록/수정 폼(지오코딩 2경로·영업시간·원자 가입)
- `features/provider/GeocoderWebView.tsx` — 가입 전 카카오 Geocoder WebView(보이지 않는 브릿지)
- `features/provider/ProviderGuard.tsx` — 역할 가드(미로그인/잘못된 역할 리다이렉트·pendingSignup 통과)
- `features/chatbot/deviceId.ts` — `getOrCreateDeviceId`·`useDeviceId`(AsyncStorage·UUID v4 폴백)
- `features/chatbot/streamMessage.ts` — react-native-sse SSE 클라이언트(Bearer·401 재시도·`StreamEvent`)
- `features/chatbot/useChatbot.ts` — 대화 상태 훅(transcript 캐시·옵티미스틱·로그아웃 초기화)
- `features/chatbot/ChatbotPanel.tsx` — @gorhom/bottom-sheet 패널·ChatBubble·링크 화이트리스트
- `app/(tabs)/provider/reservations.tsx`·`app/(tabs)/provider/reviews.tsx`·`app/(tabs)/provider/room.tsx` — provider 라우트(ProviderGuard 래핑·`(tabs)` 그룹이라 URL=/provider/*)

**수정 (apps/mobile/src/):**
- `components/app-tabs.tsx`(native)·`components/app-tabs.web.tsx`(web) — 역할조건부 네비(6 라우트 등록+역할별 숨김)
- `components/ChatbotFabSlot.tsx` — no-op 스텁 → 실제 FAB+패널 연결

**삭제:**
- `app/provider/room.tsx`(9.1 스텁) — `(tabs)/provider/room.tsx`로 대체(라우트 충돌 회피)

**무변경 확인:** apps/api · packages/api-client/src/generated · apps/web · apps/admin = diff 0.

## Change Log

| 날짜 | 변경 | 작성자 |
|------|------|--------|
| 2026-06-19 | create-story — 9.3 컨텍스트 엔진 분석 완료(웹 provider 4화면+챗봇 표면 정밀 인벤토리·순수함수/훅 미러 매핑·9.1·9.2 파운데이션 재사용·두 진짜 갭[가입전 지오코딩·SSE 전송] 결정·deferred 의무 회수 트리거 2건[모바일 챗봇·후기답글]). 9 AC·18 Task. ready-for-dev | KTH (create-story) |
| 2026-06-19 | 결정 2건 확정(둘 다 권장안 채택·스토리 무수정) — ① 가입 전 룸폼 지오코딩=**WebView 카카오 Geocoder**(9.1 WebView 패턴 재사용·기존 결정 보존·백엔드 무변경·Expo Web degrade는 로그인 백엔드 geocode 경로로 검증) ② provider 네비=**역할조건부 탭 스왑**(provider 로그인 시 (tabs) provider 메뉴 교체·웹 PROVIDER_NAV↔BOOKER_NAV 동형). SSE 전송(react-native-sse+Bearer)은 prescribed라 결정 불요 | KTH |
| 2026-06-19 | dev-story 구현 완료(18 Task) — provider 4화면(예약자현황·거절·후기답글·룸폼)·ProviderGuard·역할 네비·플로팅 챗봇(deviceId·react-native-sse·useChatbot·@gorhom 패널·링크 화이트리스트) 웹 미러/순수함수 재사용 구현. 결정사항 구현: 가입전 GeocoderWebView·역할조건부 탭(6라우트 등록+숨김). 영업시간=30분 ComboSelect(`<input type=time>` RN 부재). provider 라우트=`(tabs)/provider/*`(URL `/provider/*` 유지·탭 스왑 navigator 호스팅). typecheck·lint 클린. **Expo Web(:3001) Playwright로 9개 AC 전수 실검증**(provider 4화면·챗봇 RAG/예약검색/범위밖/링크보안·가드 양방향·9.2 무회귀)·프로덕션 번들 E2E 심볼 부재·BE/SDK/web/admin diff 0. → review | dev-story (Opus 4.8) |
| 2026-06-19 | code-review(적대적 3레이어: Blind Hunter·Edge Case Hunter·Acceptance Auditor) — patch 2·defer 4·기각 14(decision 0). 차단성 0. Acceptance Auditor=AC 위반 0(카피 verbatim·키 정합·옵티미스틱 경계·자산 재사용 전부 준수). patch 2건은 모두 신규 챗봇 SSE 클라(streamMessage.ts) 견고성: ①401 재연결 중 abort 누수 ②종료 신호 없는 멈춤(행). 모순 1건(linkifyBarePaths 무한루프)은 코드 검증으로 오탐 확정(BARE_PATH_RE 둘째 분기가 `/` 1글자 소비). → Review Findings | code-review (Opus 4.8) |
| 2026-06-19 | code-review patch 2건 적용(KTH 승인) — ①401 재연결 abort 재확인 가드 ②**idle 워치독**(60초 무활동 graceful 강등). P2 최초 수정안(`close` 리스너)은 라이브러리 소스 검증으로 무효 판정 후 워치독으로 교체. 근본 원인(배포 프록시 SSE 컷오프)은 **사람-확인-필수 배포 항목**(X-Accel-Buffering:no+sse ping+스모크테스트)으로 deferred-work 등록. typecheck·lint exit 0. → **done** | code-review (Opus 4.8) |

## Review Findings (code-review 2026-06-19)

적대적 3레이어 병렬 리뷰(Blind Hunter / Edge Case Hunter / Acceptance Auditor) 후 전 발견을 코드로 직접 검증해 트리아지했다. **차단성(Critical) 0.** Acceptance Auditor는 9개 AC 전부에서 위반을 찾지 못했다(카피 verbatim·React Query 키·옵티미스틱 경계·자산 재사용 집요 대조). 남은 항목은 신규 SSE 클라이언트의 견고성 패치 2건과 패리티·검증게이트 defer 4건뿐이다.

**Patch (2) — 둘 다 적용 완료(KTH 승인 2026-06-19·typecheck+lint exit 0):**

- [x] [Review][Patch] ✅적용 — 챗봇 SSE 401 재연결 중 abort 시 새 EventSource가 취소를 벗어나 중복 POST·연결 누수 [apps/mobile/src/features/chatbot/streamMessage.ts] — (blind+edge) 401 전송오류 → `es.close()` 후 비동기 IIFE에서 `await refreshSession()` 하는 사이 소비처가 abort(언마운트/로그아웃)하면, `onAbort`는 그 시점 `source`(이미 닫힌 옛 ES)만 닫는다. await 종료 후 `source = connect(newToken)`이 만든 새 ES는 abort 신호를 못 받아 살아남아 POST 1회를 더 쏘고 누수된다([[mobile-sse-react-native-sse-polling-trap]]의 "종료 후 중복 POST" 변종·로그아웃 중 스트리밍에서 재현). **적용:** `await refreshSession()`·`getAccessToken()` 직후 각각 `if (signal?.aborted) { finish(); return; }` 재확인 후에만 재연결.
- [x] [Review][Patch] ✅적용(수정안 교체) — 챗봇 SSE 종료 신호 없는 멈춤 시 스트림 영구 행(isStreaming 영구 true·입력 영구 잠금) [apps/mobile/src/features/chatbot/streamMessage.ts] — (blind) react-native-sse는 XHR가 200으로 깨끗이 끝나고 `done`/`error` 프레임이 없으면 어떤 종료 이벤트도 안 보낸다(`close`는 명시 `close()` 호출 시에만 디스패치·`pollingInterval:0`이라 재연결도 없음→`finish()` 미호출→`for await` 무한 대기). 웹(fetch+ReadableStream)은 reader 종료로 graceful 강등하나 **모바일만 행**(패리티 갭). **⚠️ 최초 제안 수정안(`close` 리스너 추가)은 라이브러리 소스 검증 결과 무효 확정** — `close`는 깨끗한 종료엔 발화 안 되고(우리가 부르는 `es.close()`에만 발화) 오히려 401 재연결을 깨뜨림. **실제 적용:** **idle 워치독**(`IDLE_TIMEOUT_MS=60s`·델타/이벤트 없이 60초 무활동이면 `source.close()`+`STREAM_FAILED`+`finish()`로 graceful 강등). 활동(push)마다 리셋·종료/재연결/finally에서 해제(401 refresh 동안 일시정지 후 connect 재가동). 느린 RAG/툴콜 초기지연(10~30s)을 충분히 넘는 값으로 정상 스트림 오절단 방지. **근본 원인(배포 프록시 SSE 컷오프)은 클라 워치독이 안전망이 되었고, 백엔드 하드닝은 아래 배포 항목으로 분리(사람-확인-필수).**

**⚠️ 배포 전 사람-확인-필수 항목(자동으로 안 잡힘 — deferred-work.md 등록):**

- **챗봇 SSE 프록시 버퍼링/컷오프 root-cause 하드닝** — 위 워치독은 모바일 클라의 안전망(60초 후 graceful)일 뿐, **근본 원인은 배포 환경 프록시(Railway/CDN)가 SSE를 버퍼링/컷오프하는 것**. 첫 프로덕션 배포 시 **사람이 직접**: ① 실프록시 뒤에서 챗봇 스트리밍 스모크 테스트(입력창이 매번 다시 풀리는지) ② 백엔드 `X-Accel-Buffering: no` 헤더 + sse-starlette `ping` keepalive 설정 확인. **이 항목은 빌드+푸시로 자동 검증 안 됨 — 배포 체크리스트의 의무 라인으로 사람이 밟아야 함**([[deployment-first-time-checklist]]).

**Defer (4) — 회수 트리거는 deferred-work.md:**

- [x] [Review][Defer] provider 원자 가입 비원자성 — register 성공 후 save 실패 시 떠도는 provider 계정 + 재시도 시 pendingSignup 잔존으로 register 재호출→409 막힘 [apps/mobile/src/features/provider/RoomForm.tsx:222-239] — deferred, 웹 verbatim 패리티(웹 RoomForm L231-249 동일 순차 register→save·clearPendingSignup은 save 성공 시만). 동반: ProviderGuard가 pendingSignup 잔존 시 세션검증 없이 통과(단 백엔드가 provider 역할 강제→데이터 누출 없음·방어심층 유지). 진짜 수정=백엔드 원자 register+room 엔드포인트 또는 클라 재시도 시 이미 인증됐으면 register 스킵 → web+mobile 동시([[web-mobile-parity-on-changes]]).
- [x] [Review][Defer] 네이티브 `NativeTabs.Trigger hidden`으로 pendingSignup→`/provider/room` push 도달성 미검증 [apps/mobile/src/components/app-tabs.tsx:49] — deferred, EAS dev-build 필요(Expo Web `display:none` 경로만 Playwright 확인). 네이티브에서 hidden 트리거가 라우트 등록을 유지 못하면 provider 가입 플로우 전체가 막힐 수 있음 → 첫 네이티브 빌드 시 필수 검증([[mobile-expo-router-new-routes-and-validation-port.md]] 라우트 캐시 함정과 겹침).
- [x] [Review][Defer] ComboSelect 그리드 밖 영업시간값(웹 `<input type=time>`로 만든 09:15 등)이 placeholder로 표시·사용자 재선택 시 30분 그리드값으로 무음 덮어쓰기 [apps/mobile/src/features/provider/RoomForm.tsx:466-485] — deferred, RN `<input type=time>` 부재 트레이드오프(스토리 문서화·저장값 자체는 보존). web↔mobile 교차 편집 엣지·저빈도.
- [x] [Review][Defer] 챗봇 링크 화이트리스트 `INTERNAL_HREF_RE`가 빈 파라미터 딥링크(`/?view=list&sigungu=&dong=`)를 미링크 [apps/mobile/src/features/chatbot/ChatbotPanel.tsx:38-39] — deferred, 웹 verbatim·fail-closed(`\d{1,10}`이 빈 값 거부→평문 렌더·보안상 안전). web+mobile 동시 정리 후보.

**기각(노이즈/오탐) 14건 요약:** ① linkifyBarePaths 0폭 무한루프(Blind Critical) = **오탐**(BARE_PATH_RE 둘째 분기 `\/(?![\p{L}\p{N}/])`가 `/` 1글자 소비→0폭 매치 불가, Edge가 정정) ② getNextCursorParam null 무한fetch(Blind) = **오탐**(`next_cursor ?? undefined`로 정확 종료) ③ ProviderReviews 단절 분기 순서(Blind) = 정상("단절>에러 우선" 정책·웹 패리티) ④ appendDelta 델타 유실(Blind) = 도달불가 방어가드(streamingRef+첫델타 assistant push) ⑤ formatSlots 비연속 슬롯(Blind) = 도달불가(예약=연속 슬롯·4-4 제약) ⑥ 영업시간 문자열비교/자정넘김(Blind+Edge) = 정상(그리드 사전식=시간순·자정넘김 거부는 백엔드 CHECK 미러 의도) ⑦ capacity/price Number()"1e3"(Edge) = 무해(number-pad+서버 int 검증·유효정수로 흡수) ⑧ 네비 항목 순서(Auditor) = 스토리 텍스트와 일치(웹 코드만 상이·기능 동일) ⑨ goProvider 라우트(Auditor) = 정상 적응(모바일 /provider 인덱스 부재) ⑩ RoomForm 에러 폴백(Auditor) = 도달불가 동작동일 ⑪ useMyRoom/reject throwOnError(Blind) = 무해(SDK reject→isError) ⑫ deviceId Math.random(Blind) = 문서화된 비민감 폴백 ⑬ ChatBubble key={i}(Blind) = 경미·웹 패리티 ⑭ noUsable selectResult·로그아웃 no-op setState(Edge) = 자체 도달불가/무해 판정.
