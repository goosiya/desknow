# Accessibility Review — desknow

> Reviewer: 접근성 렌즈 (a11y). 기준: WCAG 2.2 AA + 모바일(RN/iOS·Android) · 웹 a11y 베스트 프랙티스.
> 대상: `DESIGN.md` · `EXPERIENCE.md` · `.decision-log.md` (ux-desknow-2026-06-14)
> 대비비는 sRGB 상대휘도 기준으로 직접 계산(근사치).

## Overall verdict

스파인의 a11y "의도"는 동급 최고 수준이다 — 색-단독 신호 금지를 토큰 노트(`badge-available.note`, `pin-*.note`)와 EXPERIENCE의 Accessibility Floor에 **명문화**했고, 슬롯 드래그의 키보드 대안·포커스 트랩·`aria-live`·핀 SR 라벨까지 행동 정본에 적어 두었다. 다만 실제로 **결정된 hex를 계산해 보면 핵심 상태색 네 곳이 WCAG를 통과하지 못한다**: success 배지의 흰 텍스트(3.16:1), destructive 흰 텍스트(4.36:1, 일반 텍스트 미달), pin-full 회색 인디케이터(2.25:1), 그리고 포커스 링으로 쓰겠다고 선언한 primary 만다린(2.30:1 vs 크림)이다. "친근함을 위해 저대비와 맞바꾸지 않는다"는 Do/Don't 원칙이 본문 텍스트에선 지켜졌으나(15:1+) 상태색·포커스 가시성에선 무너졌다 — 이 네 hex만 조정하면 스파인은 AA를 통과한다. 결정의 방향은 옳고, 수치 검증이 누락됐을 뿐이다.

## Contrast checks

본문/버튼 텍스트는 ≥4.5:1, 큰 텍스트(18.66px+700 또는 24px+)와 UI/그래픽 요소는 ≥3:1 기준.

| 조합 | 비율 | 판정 | 비고 / 수정안 |
|---|---|---|---|
| foreground `#28200F` on bg `#FFFCF4` (본문) | 15.71:1 | ✅ Pass | 우수 |
| foreground `#28200F` on card `#FFFFFF` (본문) | 16.11:1 | ✅ Pass | 우수 |
| primary-fg `#3A2400` on primary `#FF8A1E` (버튼 텍스트) | 6.22:1 | ✅ Pass | 흰 텍스트 대신 웜 브라운 선택이 옳았음(흰색이면 ~2.3:1로 실패했을 것) |
| white `#FFFFFF` on success `#19A65A` (배지 텍스트) | 3.16:1 | ❌ **Fail** (일반 텍스트 4.5 미달; 큰 텍스트 3.0은 겨우 통과) | success를 **`#157F45`**(흰 텍스트 5.06:1)로 어둡게. pin/success 공유색이면 핀에도 이득 |
| white `#FFFFFF` on destructive `#E03A2E` | 4.36:1 | ❌ **Fail** (일반 텍스트 4.5 미달; 큰 텍스트/그래픽 3.0은 통과) | 버튼/토스트 텍스트로 쓰면 미달. **`#CC3328`**(5.16:1) 권장 |
| muted-fg `#7A6E55` on bg `#FFFCF4` (보조 텍스트) | 4.89:1 | ✅ Pass | 마진 작음 — 더 옅게 만들지 말 것 |
| muted-fg `#7A6E55` on card `#FFFFFF` | 5.01:1 | ✅ Pass | |
| pin-available `#19A65A` on bg `#FFFCF4` (UI 인디케이터 ≥3) | 3.08:1 | ⚠️ 경계 Pass | 지도 타일 위(크림 아님)에선 미달 가능 — 핀에 흰 외곽선/하이라이트 필요 |
| pin-available `#19A65A` on white card | 3.16:1 | ⚠️ 경계 Pass | success를 `#157F45`로 통일하면 4.9로 여유 확보 |
| pin-full `#B2AA9C` on bg `#FFFCF4` (UI 인디케이터 ≥3) | 2.25:1 | ❌ **Fail** | **`#7E7466`**(4.47:1) 또는 최소 `#847A6B`(4.12:1)로 채도/명도 낮춤 |
| pin-full `#B2AA9C` on white card | 2.30:1 | ❌ **Fail** | 동상 |
| primary `#FF8A1E` 포커스 링 on bg `#FFFCF4` (비텍스트 ≥3) | 2.30:1 | ❌ **Fail** | 포커스 표시가 안 보임. 링을 **`#D86E0A`**(3.33:1) 톤으로 쓰거나 2px+ 외곽 + 1px 오프셋(흰)으로 가시성 보강 |
| destructive heart `#E03A2E` on bg `#FFFCF4` (아이콘 ≥3) | 4.25:1 | ✅ Pass | 하트 아이콘 자체는 OK |
| (참고) secondary-fg on secondary `#FFF0D6` | 13.05:1 | ✅ Pass | |
| (참고) accent-fg on accent `#FFC24D` | 9.13:1 | ✅ Pass | |
| (참고) muted-fg `#7A6E55` on muted `#F4EDDF` (마감 슬롯 텍스트) | 4.30:1 | ⚠️ **경계 Fail** | 비활성 슬롯 텍스트가 본문 크기면 4.5 미달. 비활성 UI는 WCAG 1.4.3 면제지만, "마감"이 정보 전달이면 `#6E6248`로 살짝 어둡게 권장 |
| (참고) border `#F4E2C2` on bg `#FFFCF4` (카드 경계) | 1.24:1 | ℹ️ 비요구 | 경계선은 1.4.11 비적용(인접 색 구분 필수 아님)이나, 그림자 없는 플랫 카드에서 **카드 식별을 경계선만으로 한다면** 너무 약함 — 면색 대비(크림↔흰)로 보강됨, 그래도 약함 |

**요약: 검사 17건(핵심) 중 — Pass 9, 경계/조건부 3, Fail 4 (success 배지텍스트, destructive 텍스트, pin-full, 포커스 링).**

## Findings

- **[critical]** pin-full `#B2AA9C` 인디케이터가 배경/카드 대비 2.25–2.30:1로 비텍스트 3:1 기준 미달 (DESIGN.md `colors.pin-full`, Components 맵 핀). 저시력 사용자는 "마감" 핀을 배경과 구분하기 어렵다. 색-단독 금지 원칙 덕에 X 아이콘이 동반되지만, **아이콘 자체도 같은 회색이면 같이 안 보인다** — 형태 식별의 전제인 충분한 대비가 없다. *Fix:* pin-full을 **`#7E7466`**(4.47:1)로 어둡게; 아이콘은 흰색 글리프 + 회색 채움으로 분리해 대비 확보.

- **[critical]** 포커스 링을 primary `#FF8A1E`로 지정했으나 크림 배경 대비 2.30:1로 비텍스트 3:1 미달 (DESIGN.md `colors.ring`). 키보드/스위치 사용자가 **현재 포커스 위치를 못 본다** — WCAG 2.4.11(Focus Appearance, 2.2 신규) 및 2.4.7 위반 위험. *Fix:* 링 색을 **`#D86E0A`**(3.33:1)로 어둡게 하거나, 2px 두께 + 흰색 1px 오프셋(이중 링)으로 인접 대비를 보장. shadcn `ring`은 RN에서 자동 적용 안 되므로 RN 포커스/하이라이트 스타일을 별도 토큰으로 명시 필요.

- **[high]** success `#19A65A` 위 흰 텍스트 배지가 3.16:1로 본문 텍스트 4.5:1 미달 (DESIGN.md `badge-available`, Components 배지). "예약 가능" 배지 글자가 흐리게 읽힌다. *Fix:* success를 **`#157F45`**(흰 텍스트 5.06:1, 크림 대비 4.93)로 통일 — 핀-가용 색까지 함께 끌어올려 두 마리 토끼.

- **[high]** destructive `#E03A2E` 위 흰 텍스트가 4.36:1로 일반 텍스트 4.5:1 미달 (DESIGN.md `destructive`/`destructive-foreground`). 취소·삭제 버튼/토스트 텍스트가 큰 글자가 아니면 미달. *Fix:* destructive를 **`#CC3328`**(5.16:1)로 살짝 어둡게. 또는 해당 텍스트를 항상 label(14px/500) 이상·굵게 유지(그래도 14px는 "큰 텍스트" 아님 — 색 조정 권장).

- **[high]** 모션 섹션이 `[ASSUMPTION]`으로만 존재하고 **`prefers-reduced-motion` 대응이 어디에도 없다** (DESIGN.md 모션 [ASSUMPTION], EXPERIENCE Interaction Primitives). 스프링감·바텀시트 상승·하트 토글 등 마이크로모션이 전정장애(vestibular)·ADHD 사용자에게 불편/유발 가능. WCAG 2.3.3(AAA지만 권장). *Fix:* "모든 마이크로모션은 `prefers-reduced-motion: reduce`(웹) / `AccessibilityInfo.isReduceMotionEnabled`(RN)에서 0ms 또는 페이드로 대체"를 모션 섹션에 명문화. Finalize 검토 항목에 추가.

- **[medium]** 터치 타깃 최소 크기(44×44px / 48dp) 규정이 **스파인 어디에도 없다**. 지도 핀, 슬롯 셀(1시간 단위 그리드는 좁아지기 쉬움), 하트 토글, 지도/목록 토글, 그래버는 모두 작아질 위험. WCAG 2.5.8(Target Size, 2.2 AA = 24px 최소, iOS HIG 44 / Android 48 권장). *Fix:* "모든 인터랙티브 타깃 ≥44×44px(시각 크기가 작아도 히트영역 확장), 슬롯 셀 최소 높이 44px"를 Layout & Spacing 또는 Accessibility Floor에 추가. 핀 밀집 시 클러스터링으로 24px 최소 간격 확보.

- **[medium]** `aria-live` 적용 범위가 챗봇 스트리밍에만 명시됨 (EXPERIENCE Accessibility Floor). **인앱 배너**(도래 리마인드·상태변경 통지)와 **동시성 충돌/슬롯 재표시**, **토스트**(예약 완료 등)는 SR에 자동 안내되지 않으면 놓친다. *Fix:* 인앱 배너·토스트 = `role="status"`(politeness=polite), 슬롯 충돌·에러 = `role="alert"`(assertive)로 명시. RN은 `AccessibilityInfo.announceForAccessibility`로 등가 처리.

- **[medium]** 아이콘 단독 컨트롤의 접근 가능한 이름(accessible name)이 핀 외에는 미명세 (EXPERIENCE Accessibility Floor는 핀만 예시). 하트 토글(채움/외곽선만으로 상태 구분), FAB "룸메이트", 지도/목록 토글, 바텀시트 그래버는 **상태까지 읽혀야** 한다. *Fix:* 하트 = `aria-pressed` + "즐겨찾기 추가됨/해제됨"; FAB = "룸메이트 챗봇 열기"; 토글 = "지도 보기/목록 보기" + 현재 상태; 그래버 = "정보 시트 펼치기/접기". RN은 `accessibilityRole`+`accessibilityState`.

- **[medium]** 슬롯 피커 키보드 대안은 정의됨(방향키+Enter로 시작/끝) — 좋음. 그러나 **연속 선택 진행 상태가 SR에 어떻게 전달되는지** 미명세. 비연속 불허 제약을 시각적으로만 막으면 SR 사용자는 "왜 선택이 안 되는지" 모른다. *Fix:* 슬롯 셀에 `aria-disabled`+사유 라벨("이미 예약됨"/"지난 시간"), 선택 진행 시 "14시 시작 선택됨, 종료 시각을 고르세요" 같은 live 안내.

- **[medium]** 다이얼로그/바텀시트 포커스 관리는 명시됨(진입·Esc·트랩·복귀) — 잘 됨. 다만 **RN에는 `Esc`도 DOM 포커스 트랩도 없다**. *Fix:* RN 바텀시트/모달은 `accessibilityViewIsModal`(iOS) + Android `importantForAccessibility="no-hide-descendants"`로 배경 격리, 닫기는 백 제스처/명시적 닫기 버튼. 플랫폼 델타로 분리 명시.

- **[low]** caption 12px는 한국어 본문 하한으로 받아들일 만하나(메타 한정), **동적 타입/텍스트 스케일링에 대한 규정이 없다**. 고정 높이 슬롯 셀·배지·탭바가 200% 확대(WCAG 1.4.4) 또는 iOS Dynamic Type에서 깨질 수 있다. *Fix:* "고정 px 높이 컴포넌트는 텍스트 확대 시 줄바꿈/높이 증가 허용, 잘림 금지"를 Typography에 추가. line-height 1.6은 한글 가독성에 적절(통과).

- **[low]** 폼(제공자 등록·후기) a11y가 스파인에 없음 — 라벨 연결, 에러-필드 association(`aria-describedby`), 필수 표시 방법 미정 (EXPERIENCE 제공자 등록 상태만 존재). 색만으로 에러 표시 위험(destructive 빨강). *Fix:* "폼 필드 = 가시 라벨 + `for/id` 연결, 에러는 색+아이콘+텍스트 & 필드에 association, 필수는 별표+텍스트('필수')"를 추가. 후기 별점은 키보드/SR 입력 가능해야.

- **[low]** "색-단독 금지"가 핀·배지엔 명문화됐으나 **인앱 배너·마감 슬롯엔 명시 안 됨**. 배너 두 종류(리마인드/상태변경)가 색으로만 구분되면 안 된다. *Fix:* 배너·슬롯 상태 모두 아이콘+텍스트 라벨 동반을 Do/Don't 또는 Accessibility Floor에 일반 규칙으로 끌어올림(현재는 핀 예시에 국한).

---

### 권장 토큰 패치 (요약)

| 토큰 | 현재 | 권장 | 근거 |
|---|---|---|---|
| `success` / `pin-available` | `#19A65A` | `#157F45` | 흰 텍스트 5.06:1, 인디케이터 4.9:1 |
| `destructive` | `#E03A2E` | `#CC3328` | 흰 텍스트 5.16:1 |
| `pin-full` | `#B2AA9C` | `#7E7466` | 인디케이터 4.47:1 |
| `ring` (포커스) | `#FF8A1E` | `#D86E0A` (또는 이중 링) | 비텍스트 3.33:1 |

본문·버튼·secondary·accent 텍스트 대비는 전부 통과이므로 위 4개 상태/포커스 토큰만 조정하면 스파인은 WCAG 2.2 AA를 충족한다.
