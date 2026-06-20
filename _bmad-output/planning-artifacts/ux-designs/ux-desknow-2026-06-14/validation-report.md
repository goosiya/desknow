# DeskNow — UX Design Validation Report

- **DESIGN:** ./DESIGN.md
- **EXPERIENCE:** ./EXPERIENCE.md
- **Run-at:** 2026-06-14
- **Reviewers:** review-rubric.md · review-accessibility.md

> 전체 등급(letter grade) 없음 — 카테고리별 verdict + 심각도 집계가 사실을 말한다.

---

## Overall verdict

DeskNow 스파인 페어는 본질적으로 **strong-to-adequate**이며 소비자 출시 수준의 실체를 갖췄다: 모든 PRD UJ가 주인공이 등장하는 Key Flow(클라이맥스 + 실패 경로)로 실현돼 있고, 상태 매트릭스는 N/A 사유를 명시한 채 빠짐없이 채워졌으며, 모든 DESIGN 토큰과 prose의 `{token}` 참조가 해석되고, 제품 특화 계약(동시성·타임존·챗봇)이 전용 섹션에 커밋돼 다운스트림 아키텍처/스토리 개발이 그대로 source-extract할 수 있다. 완벽하게 깨끗한 source-extraction을 막는 실제 결함은 둘이다: EXPERIENCE.md가 참조하는 `{elevation.sheet}` / `{elevation.fab}`가 DESIGN frontmatter의 어떤 토큰으로도 **해석되지 않으며**(elevation은 prose + 리터럴 컴포넌트 문자열로만 존재), 비주얼 레퍼런스 계약이 **공허하다** — 두 스파인 모두 존재하지 않는 `mockups/` HTML을 가리키고, 작동하는 유일한 파일은 화면 목업이 전혀 아닌 컬러 팔레트 HTML뿐이다.

추가 리뷰어(접근성)가 그림을 바꾼다. 스파인의 a11y *의도*는 동급 최고 수준이지만 — 색-단독 신호 금지를 토큰 노트와 Accessibility Floor에 명문화했고 키보드 대안·포커스 트랩·`aria-live`·핀 SR 라벨까지 행동 정본에 적었다 — 실제로 **결정된 hex를 계산하면 핵심 상태/포커스 색 네 곳이 WCAG 2.2 AA를 통과하지 못한다**: success 배지 흰 텍스트(3.16:1), destructive 흰 텍스트(4.36:1), pin-full 회색 인디케이터(2.25:1), primary 만다린 포커스 링(2.30:1). 본문·버튼 텍스트는 15:1+로 모두 통과하므로, 이 네 hex만 조정하면 스파인은 AA를 충족한다. **참고: 본 검증 시점에 후속 편집 패스가 같은 세션에서 진행 중이다** — 목업은 이미 `mockups/`로 승격됐고, 팔레트 hex는 결정 로그 D-13/D-14/D-15에 따라 보정 중이다. 따라서 rubric의 high 2건(elevation 토큰, 비주얼 레퍼런스)과 접근성 대비 실패 전부는 **확인됨 → 해소 진행 중**으로 표시한다(원문 finding은 보존).

---

## Category verdicts

- **1. Flow coverage** — strong
- **2. Token completeness** — adequate
- **3. Component coverage** — adequate
- **4. State coverage** — strong
- **5. Visual reference coverage** — broken
- **6. Bloat & overspecification** — low / strong
- **7. Inheritance discipline** — strong
- **8. Shape fit** — strong

---

## Findings by severity

### Critical

- **[Accessibility] pin-full 인디케이터 대비 2.25–2.30:1 (비텍스트 3:1 미달)** — *확인됨 → 해소 진행 중*
  - **위치:** DESIGN.md `colors.pin-full` · Components 맵 핀
  - **노트:** pin-full `#B2AA9C`가 배경/카드 대비 2.25–2.30:1로 비텍스트 3:1 기준 미달. 저시력 사용자는 "마감" 핀을 배경과 구분하기 어렵다. 색-단독 금지 원칙 덕에 X 아이콘이 동반되지만, 아이콘 자체도 같은 회색이면 같이 안 보인다 — 형태 식별의 전제인 충분한 대비가 없다.
  - **Fix:** pin-full을 `#7E7466`(4.47:1)로 어둡게; 아이콘은 흰색 글리프 + 회색 채움으로 분리해 대비 확보.

- **[Accessibility] 포커스 링 primary 대비 2.30:1 (비텍스트 3:1 미달)** — *확인됨 → 해소 진행 중*
  - **위치:** DESIGN.md `colors.ring`
  - **노트:** 포커스 링을 primary `#FF8A1E`로 지정했으나 크림 배경 대비 2.30:1로 미달. 키보드/스위치 사용자가 현재 포커스 위치를 못 본다 — WCAG 2.4.11(Focus Appearance, 2.2 신규) 및 2.4.7 위반 위험.
  - **Fix:** 링 색을 `#D86E0A`(3.33:1)로 어둡게 하거나, 2px 두께 + 흰색 1px 오프셋(이중 링)으로 인접 대비 보장. shadcn `ring`은 RN에서 자동 적용 안 되므로 RN 포커스/하이라이트 스타일을 별도 토큰으로 명시 필요.

### High

- **[Visual reference] 비주얼 레퍼런스 계약이 아무것도 가리키지 않음** — *확인됨 → 해소 진행 중*
  - **위치:** EXPERIENCE.md:80
  - **노트:** EXPERIENCE.md:80이 존재하지 않는 `mockups/` HTML을 링크하고, 나중에 승격할 `key-*.html` 목업이 `.working/`에도 없었다 — 유일한 HTML은 화면 구성이 아닌 컬러-팔레트 도구. 링크를 따라간 소비자는 dead path를 만난다. (검증 시점 상태. 후속 패스에서 목업이 `mockups/`로 승격되며 해소 진행 중.)
  - **Fix:** 화면 목업(지도/바텀시트/상세-예약전개/슬롯피커/챗봇이 로드베어링) 생성 후 섹션별 링크, 또는 MVP에 목업이 없다면 EXPERIENCE.md:80 포인터를 제거/완화해 dangling 방지.

- **[Mechanical / Token] elevation 토큰 broken cross-ref** — *확인됨 → 해소 진행 중*
  - **위치:** EXPERIENCE.md:111 `{elevation.sheet}` · EXPERIENCE.md:116 `{elevation.fab}`
  - **노트:** 두 참조가 해석되지 않음 — DESIGN.md에 `elevation` frontmatter 토큰 그룹이 없다(elevation은 prose `## Elevation & Depth` + 리터럴 값 `elevation: floating` / `elevation: flat`로만 존재). resolver가 EXPERIENCE 참조를 DESIGN frontmatter에 flatten하면 이 둘에서 실패. 두 파일이 elevation을 토큰으로 볼지에 대해 불일치.
  - **Fix:** DESIGN frontmatter에 `elevation` 토큰 그룹 추가 후 컴포넌트가 `{elevation.sheet}` 참조, 또는 EXPERIENCE를 prose("그림자 — DESIGN.Elevation 참조")로 바꾸고 토큰 구문 제거. 둘 중 하나로 통일.

- **[Accessibility] success 위 흰 텍스트 배지 3.16:1 (본문 4.5:1 미달)** — *확인됨 → 해소 진행 중*
  - **위치:** DESIGN.md `badge-available` · Components 배지
  - **노트:** success `#19A65A` 위 흰 텍스트가 3.16:1로 본문 텍스트 4.5:1 미달. "예약 가능" 배지 글자가 흐리게 읽힌다.
  - **Fix:** success를 `#157F45`(흰 텍스트 5.06:1, 크림 대비 4.93)로 통일 — 핀-가용 색까지 함께 끌어올려 두 마리 토끼.

- **[Accessibility] destructive 위 흰 텍스트 4.36:1 (일반 텍스트 4.5:1 미달)** — *확인됨 → 해소 진행 중*
  - **위치:** DESIGN.md `destructive` / `destructive-foreground`
  - **노트:** destructive `#E03A2E` 위 흰 텍스트가 4.36:1로 일반 텍스트 4.5:1 미달. 취소·삭제 버튼/토스트 텍스트가 큰 글자가 아니면 미달.
  - **Fix:** destructive를 `#CC3328`(5.16:1)로 살짝 어둡게. 또는 해당 텍스트를 항상 label(14px/500) 이상·굵게 유지(그래도 14px는 "큰 텍스트" 아님 — 색 조정 권장).

- **[Accessibility] prefers-reduced-motion 대응이 어디에도 없음**
  - **위치:** DESIGN.md 모션 [ASSUMPTION] · EXPERIENCE Interaction Primitives
  - **노트:** 모션 섹션이 `[ASSUMPTION]`으로만 존재하고 reduced-motion 대응이 없다. 스프링감·바텀시트 상승·하트 토글 등 마이크로모션이 전정장애·ADHD 사용자에게 불편/유발 가능. WCAG 2.3.3(AAA지만 권장).
  - **Fix:** "모든 마이크로모션은 `prefers-reduced-motion: reduce`(웹) / `AccessibilityInfo.isReduceMotionEnabled`(RN)에서 0ms 또는 페이드로 대체"를 모션 섹션에 명문화. Finalize 검토 항목에 추가.

### Medium

- **[Token] 로드베어링 조합의 측정 대비 비율 부재** — *접근성 리뷰어 실측 완료 → 해소 진행 중*
  - **위치:** DESIGN.md:173, 263
  - **노트:** Cream `#FFFCF4` + foreground `#28200F`, success `#19A65A` 배지 위 흰 텍스트, 맵 타일 위 핀 색이 수치 없이 "AA"로 단정된다. warm-brown `primary-foreground #3A2400` on `primary #FF8A1E`가 가장 위험(둘 다 중간톤)하며 미검증.
  - **Fix:** bg+fg, 배지 텍스트, primary-fg-on-primary에 대한 비율 목표/측정값 추가. EXPERIENCE.md:155의 "브랜드 오버라이드는 비율 유지로 검증됨" 주장을 뒷받침하는 수치를 커밋. (접근성 리뷰어 실측: primary-fg-on-primary 6.22:1 통과; 나머지는 접근성 contrast finding 참조.)

- **[Visual reference] DESIGN.md가 비주얼 레퍼런스/팔레트 소스를 인용 안 함**
  - **위치:** DESIGN.md (Colors)
  - **노트:** DESIGN.md는 비주얼 레퍼런스 링크가 전혀 없고 D-05가 선택한 팔레트 소스 `.working/color-themes-1.html`도 인용하지 않는다.
  - **Fix:** 팔레트-소스 레퍼런스(및 생성 시 컴포넌트별 비주얼 목업)를 추가해 비주얼 스파인이 선택된 아티팩트로 추적되게 함.

- **[Accessibility] 터치 타깃 최소 크기 규정 부재 (44×44 / 48dp)**
  - **위치:** EXPERIENCE Layout / Accessibility Floor
  - **노트:** 터치 타깃 최소 크기 규정이 스파인 어디에도 없다. 지도 핀, 슬롯 셀, 하트 토글, 지도/목록 토글, 그래버가 작아질 위험. WCAG 2.5.8(Target Size, 2.2 AA = 24px 최소, iOS HIG 44 / Android 48 권장).
  - **Fix:** "모든 인터랙티브 타깃 ≥44×44px(시각 크기가 작아도 히트영역 확장), 슬롯 셀 최소 높이 44px"를 Layout & Spacing 또는 Accessibility Floor에 추가. 핀 밀집 시 클러스터링으로 24px 최소 간격 확보.

- **[Accessibility] aria-live 적용 범위가 챗봇 스트리밍에만 한정**
  - **위치:** EXPERIENCE Accessibility Floor
  - **노트:** 인앱 배너(도래 리마인드·상태변경 통지), 동시성 충돌/슬롯 재표시, 토스트(예약 완료 등)가 SR에 자동 안내되지 않으면 놓친다.
  - **Fix:** 인앱 배너·토스트 = `role="status"`(polite), 슬롯 충돌·에러 = `role="alert"`(assertive)로 명시. RN은 `AccessibilityInfo.announceForAccessibility`로 등가 처리.

- **[Accessibility] 아이콘 단독 컨트롤의 accessible name 미명세 (핀 외)**
  - **위치:** EXPERIENCE Accessibility Floor
  - **노트:** 하트 토글(채움/외곽선만으로 상태 구분), FAB "룸메이트", 지도/목록 토글, 바텀시트 그래버는 상태까지 읽혀야 한다.
  - **Fix:** 하트 = `aria-pressed` + "즐겨찾기 추가됨/해제됨"; FAB = "룸메이트 챗봇 열기"; 토글 = "지도 보기/목록 보기" + 현재 상태; 그래버 = "정보 시트 펼치기/접기". RN은 `accessibilityRole`+`accessibilityState`.

- **[Accessibility] 슬롯 연속 선택 진행 상태의 SR 전달 미명세**
  - **위치:** EXPERIENCE Interaction Primitives (슬롯 피커)
  - **노트:** 슬롯 피커 키보드 대안은 정의됨(방향키+Enter) — 좋음. 그러나 연속 선택 진행 상태가 SR에 어떻게 전달되는지 미명세. 비연속 불허를 시각적으로만 막으면 SR 사용자는 "왜 선택이 안 되는지" 모른다.
  - **Fix:** 슬롯 셀에 `aria-disabled`+사유 라벨("이미 예약됨"/"지난 시간"), 선택 진행 시 "14시 시작 선택됨, 종료 시각을 고르세요" 같은 live 안내.

- **[Accessibility] RN에는 Esc도 DOM 포커스 트랩도 없음**
  - **위치:** EXPERIENCE (다이얼로그/바텀시트 포커스 관리)
  - **노트:** 다이얼로그/바텀시트 포커스 관리는 명시됨(진입·Esc·트랩·복귀) — 잘 됨. 다만 RN에는 Esc도 DOM 포커스 트랩도 없다.
  - **Fix:** RN 바텀시트/모달은 `accessibilityViewIsModal`(iOS) + Android `importantForAccessibility="no-hide-descendants"`로 배경 격리, 닫기는 백 제스처/명시적 닫기 버튼. 플랫폼 델타로 분리 명시.

### Low

- **[Flow] UJ-3에 실패/edge 경로 부재 (UJ-1·UJ-2는 있음)**
  - **위치:** EXPERIENCE.md:235-242
  - **노트:** 제공자 등록에는 그럴듯한 실패 모드(주소 검색 미스, 저장 실패)가 있다. State 매트릭스 "제공자 등록" 행이 이를 커버하나 flow 자체에는 edge 비트가 없다.
  - **Fix:** UJ-3에 한 줄짜리 Edge 추가(예: 주소 검색 실패 → 입력 보존 + 재시도)로 패리티를 맞추거나, State 행이 이를 담당함을 명기.

- **[Token] 타입 램프가 정의됐으나 대부분 미참조 (정상)**
  - **위치:** DESIGN.md:188
  - **노트:** `{typography.body}`만 prose에서 line-height 1.6 인용으로 참조되며 정상 해석된다. 나머지 타입 램프는 정의-but-미참조(램프로서 수용 가능). 이슈 아님 — 기록만.
  - **Fix:** 조치 불필요.

- **[Component] 섹션 간 명명 표류 (캘린더 vs 달력)**
  - **위치:** DESIGN.Components / EXPERIENCE.Component Patterns
  - **노트:** 깨진 건 아니나 소비자 매핑 비용. DESIGN은 "스터디룸 상세 레이아웃" + "캘린더 + 슬롯 피커", EXPERIENCE는 "상세 내 예약 전개" + "달력 + 슬롯 피커"(달력 vs 캘린더). 같은 컴포넌트, 두 표기.
  - **Fix:** 한 용어(캘린더/슬롯 피커)를 골라 양쪽 파일에서 동일하게 사용.

- **[Component] "지도+핀"이 DESIGN "맵 핀"에 암묵 매핑**
  - **위치:** EXPERIENCE 행동 행 / DESIGN 비주얼 행
  - **노트:** 맵 표면 자체는 DESIGN 비주얼 행이 없고 핀만 있다. 맵이 3rd-party 카카오맵 표면이라 수용 가능하나 이름 페어링이 암묵적.
  - **Fix:** 선택 사항 — "맵 핀 / 지도+핀"으로 정렬하거나 맵이 벤더 소유임을 명기.

- **[State] 관리자-웹 표면에 State 매트릭스 행 없음**
  - **위치:** EXPERIENCE State matrix
  - **노트:** 계정 관리·예약 임의취소·챗봇 문서 인제스트에 State 행이 없고 제공자 등록만 매트릭스에 있다. 관리자는 의도적으로 비-UJ·저충실도라 방어 가능하나, 관리자 앱을 만드는 story-dev는 빈/에러/로딩 가이드를 못 받는다.
  - **Fix:** 단일 coarse 관리자 행 추가, 또는 관리자 상태가 shadcn data-table 기본을 상속하며 experience-matrix 범위 밖임을 한 번 명기.

- **[Visual reference] color-themes-1.html이 스파인 기준 orphan**
  - **위치:** .working/color-themes-1.html
  - **노트:** 결정 로그(D-05)에서 선택됐으나 DESIGN.md에서 미링크. 충돌은 아니고 단지 미추적.
  - **Fix:** DESIGN.Colors에 한 줄 인용.

- **[Mechanical] Section-name ref (DESIGN.md.Motion 앵커 불일치)**
  - **위치:** EXPERIENCE.md:148
  - **노트:** `DESIGN.md.Motion`을 인용하나 DESIGN의 모션은 `### 모션 [ASSUMPTION]`(Do's & Don'ts 하위 중첩)에 있고 top-level `## Motion`이 아님. 의도로는 해석되나 앵커 이름이 다름.
  - **Fix:** `## Motion`으로 승격하거나 실제 헤딩을 인용.

- **[Accessibility] 동적 타입/텍스트 스케일링 규정 부재**
  - **위치:** DESIGN.md Typography
  - **노트:** caption 12px는 메타 한정으로 수용 가능하나, 고정 높이 슬롯 셀·배지·탭바가 200% 확대(WCAG 1.4.4) 또는 iOS Dynamic Type에서 깨질 수 있다.
  - **Fix:** "고정 px 높이 컴포넌트는 텍스트 확대 시 줄바꿈/높이 증가 허용, 잘림 금지"를 Typography에 추가. line-height 1.6은 한글 가독성에 적절(통과).

- **[Accessibility] 폼(제공자 등록·후기) a11y가 스파인에 없음**
  - **위치:** EXPERIENCE (제공자 등록 상태만 존재)
  - **노트:** 라벨 연결, 에러-필드 association(`aria-describedby`), 필수 표시 방법 미정. 색만으로 에러 표시 위험(destructive 빨강).
  - **Fix:** "폼 필드 = 가시 라벨 + `for/id` 연결, 에러는 색+아이콘+텍스트 & 필드에 association, 필수는 별표+텍스트('필수')" 추가. 후기 별점은 키보드/SR 입력 가능해야.

- **[Accessibility] "색-단독 금지"가 인앱 배너·마감 슬롯엔 미명시**
  - **위치:** EXPERIENCE Do/Don't · Accessibility Floor
  - **노트:** 색-단독 금지가 핀·배지엔 명문화됐으나 인앱 배너·마감 슬롯엔 명시 안 됨. 배너 두 종류(리마인드/상태변경)가 색으로만 구분되면 안 된다.
  - **Fix:** 배너·슬롯 상태 모두 아이콘+텍스트 라벨 동반을 Do/Don't 또는 Accessibility Floor에 일반 규칙으로 끌어올림(현재는 핀 예시에 국한).

---

## 권장 토큰 패치 (접근성 리뷰어 요약)

| 토큰 | 현재 | 권장 | 근거 |
|---|---|---|---|
| `success` / `pin-available` | `#19A65A` | `#157F45` | 흰 텍스트 5.06:1, 인디케이터 4.9:1 |
| `destructive` | `#E03A2E` | `#CC3328` | 흰 텍스트 5.16:1 |
| `pin-full` | `#B2AA9C` | `#7E7466` | 인디케이터 4.47:1 |
| `ring` (포커스) | `#FF8A1E` | `#D86E0A` (또는 이중 링) | 비텍스트 3.33:1 |

본문·버튼·secondary·accent 텍스트 대비는 전부 통과 — 위 4개 상태/포커스 토큰만 조정하면 WCAG 2.2 AA 충족. (결정 로그 D-13/D-14/D-15에 따라 해소 진행 중.)

---

## Reviewer files

- review-rubric.md (스파인 페어 rubric 워커 — 8 카테고리)
- review-accessibility.md (접근성 렌즈 · WCAG 2.2 AA + 모바일/웹 a11y)
