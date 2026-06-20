---
name: DeskNow
description: 근처 빈 스터디룸을 지도에서 찾아 몇 단계 만에 예약하는 서비스. 따뜻하고 친근한 "에너제틱 만다린" 라이트 테마 위에 shadcn/ui를 얹은 멀티 서피스(웹·앱·관리자) 디자인 스파인.
status: final
created: 2026-06-14
updated: 2026-06-14
ui_system: shadcn
document_output_language: korean
sources:
  - ../../prds/prd-desknow-2026-06-14/prd.md
  - ../../briefs/brief-desknow-2026-06-14/brief.md
  - ../../research/technical-desknow-mvp-tech-feasibility-research-2026-06-13.md
  - ../../../../docs/idea.md
colors:
  # "에너제틱 만다린" — 라이트 전용(MVP). 토큰 키는 shadcn 시맨틱 규약을 따르며,
  # 다크는 의도적으로 작성하지 않음(시맨틱 구조만 다크 확장 가능하게 유지).
  primary: '#FF8A1E'
  primary-foreground: '#3A2400'
  secondary: '#FFF0D6'
  secondary-foreground: '#3A2400'
  accent: '#FFC24D'
  accent-foreground: '#3A2400'
  background: '#FFFCF4'
  foreground: '#28200F'
  card: '#FFFFFF'
  card-foreground: '#28200F'
  popover: '#FFFFFF'
  popover-foreground: '#28200F'
  muted: '#F4EDDF'
  muted-foreground: '#7A6E55'
  border: '#F4E2C2'
  input: '#F4E2C2'
  ring: '#D86E0A'
  destructive: '#CC3328'
  destructive-foreground: '#FFFFFF'
  # 의미색(가용성). 브랜드 웜에서 색상환상 충분히 떨어뜨려 핀 상태가 프라이머리와 충돌하지 않게 함.
  # 시맨틱 hex는 WCAG 2.2 AA(배지/텍스트/그래픽 대비)에 맞춰 보정됨.
  success: '#157F45'
  pin-available: '#157F45'
  pin-full: '#7E7466'
typography:
  # Pretendard(한국어 우선). 본문/라벨/캡션은 shadcn 타입 역할을 Pretendard로 치환하고,
  # 한글 가독성을 위해 line-height를 넉넉히 잡음. 스케일은 shadcn 기본 위에 구축.
  display:
    fontFamily: Pretendard
    fontSize: 32px
    fontWeight: '700'
    lineHeight: '1.3'
    letterSpacing: -0.01em
  h1:
    fontFamily: Pretendard
    fontSize: 24px
    fontWeight: '700'
    lineHeight: '1.4'
    letterSpacing: -0.01em
  h2:
    fontFamily: Pretendard
    fontSize: 20px
    fontWeight: '600'
    lineHeight: '1.45'
  h3:
    fontFamily: Pretendard
    fontSize: 18px
    fontWeight: '600'
    lineHeight: '1.5'
  body:
    fontFamily: Pretendard
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
  body-sm:
    fontFamily: Pretendard
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.6'
  label:
    fontFamily: Pretendard
    fontSize: 14px
    fontWeight: '500'
    lineHeight: '1.4'
  caption:
    fontFamily: Pretendard
    fontSize: 12px
    fontWeight: '400'
    lineHeight: '1.45'
rounded:
  # shadcn 기본 라운드 계열(radius 0.5rem 패밀리). 친근하되 절제.
  sm: 0.25rem
  md: 0.375rem
  DEFAULT: 0.5rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  # shadcn / Tailwind 4-기반 스케일 상속.
  '1': 4px
  '2': 8px
  '3': 12px
  '4': 16px
  '5': 20px
  '6': 24px
  '8': 32px
  '10': 40px
  '12': 48px
  '16': 64px
elevation:
  flat: none
  sheet: '0 -4px 24px rgba(40,32,15,0.12)'
  dialog: '0 8px 32px rgba(40,32,15,0.16)'
  toast: '0 4px 16px rgba(40,32,15,0.14)'
  fab: '0 4px 12px rgba(40,32,15,0.18)'
components:
  button-primary:
    background: '{colors.primary}'
    foreground: '{colors.primary-foreground}'
    radius: '{rounded.DEFAULT}'
  badge-available:
    background: '{colors.success}'
    foreground: '#FFFFFF'
    radius: '{rounded.full}'
    note: '아이콘(체크) 동반 필수 — 색 단독 금지'
  pin-available:
    color: '{colors.pin-available}'
    icon: check
    note: '초록 + 체크 아이콘. 색은 절대 단독 신호가 아님'
  pin-full:
    color: '{colors.pin-full}'
    icon: x
    note: '회색 + X 아이콘. 색은 절대 단독 신호가 아님'
  bottom-sheet:
    background: '{colors.card}'
    radius-top: '{rounded.xl}'
    elevation: '{elevation.sheet}'
    note: '지도 위로 떠오르는 유일 면 — 그림자 허용'
  dialog:
    background: '{colors.popover}'
    radius: '{rounded.lg}'
    elevation: '{elevation.dialog}'
  toast:
    background: '{colors.card}'
    radius: '{rounded.lg}'
    elevation: '{elevation.toast}'
  chatbot-fab:
    background: '{colors.primary}'
    foreground: '{colors.primary-foreground}'
    radius: '{rounded.full}'
    elevation: '{elevation.fab}'
  card:
    background: '{colors.card}'
    border: '{colors.border}'
    radius: '{rounded.lg}'
    elevation: '{elevation.flat}'
  favorite-toggle:
    active: '{colors.destructive}'
    inactive: '{colors.muted-foreground}'
    note: '활성 = 채워진 하트, 비활성 = 외곽선 하트'
---

<!-- 시각 정체성 스파인. .decision-log.md 정본으로부터 증류됨. -->

## Brand & Style

DeskNow는 **근처 빈 스터디룸을 지도에서 찾아 몇 단계 만에 예약하는** 서비스다. 브랜드 인격은 한마디로 **활기·친근·경쾌** — 당근·카카오 계열의 따뜻하고 말 걸기 쉬운 톤이다. 차분한 핀테크 블루가 아니라, 따뜻한 결로 의도적으로 차별화한다.

미감의 닻은 셋이며, 각각의 장점만 취한다. **토스**에서는 색·온도가 아니라 *단순함과 단계별 진행감*만 가져온다. **에어비앤비**에서는 *지도 + 카드 예약* 경험을, **카카오맵**에서는 *핀 + 바텀시트* 패턴을 가져온다.

UI 시스템은 **shadcn/ui**다. 이 DESIGN.md는 shadcn 기본값을 정본으로 상속하고, 그 위에 브랜드 레이어 델타(웜 컬러 팔레트, Pretendard 타이포, 가용성 의미색, DeskNow 고유 컴포넌트)만 명시한다. 웹(Next.js)·모바일 앱(React Native/Expo)·관리자 웹이 같은 토큰을 공유해 **화면 간 이질감 제로**를 목표로 한다.

활기는 형태를 과하게 둥글리거나 장식을 더해 내는 것이 아니라 **색·모션·마이크로카피**로 낸다. 형태와 면은 절제하고, 에너지는 만다린 오렌지와 짧은 생기 있는 모션이 책임진다.

**라이트 모드 전용**(MVP)이다. 토큰은 시맨틱 구조로 설계해 다크 확장 여지를 남겨두되, 지금은 다크 값을 작성하지 않는다.

## Colors

팔레트 이름은 **"에너제틱 만다린"** — 경쾌하고 발랄한, 젊고 캐주얼한 결이다.

- **Primary Mandarin (`{colors.primary}` `#FF8A1E`)** — 브랜드 시그니처. 주요 액션(예약하기), 활성 내비, 플로팅 챗봇 버튼에 쓴다(포커스 링은 대비 확보를 위해 아래 `{colors.ring}` 별도 사용). 전경색은 따뜻한 다크 브라운 `{colors.primary-foreground}`(`#3A2400`)로 순백 텍스트보다 톤을 부드럽게 맞춘다. **단, 가용성·상태 의미로는 절대 쓰지 않는다**(아래 의미색 참고).
- **Secondary (`{colors.secondary}` `#FFF0D6`)** / **Accent (`{colors.accent}` `#FFC24D`)** — 만다린의 옅은·밝은 파생. 보조 칩, 강조 배지, 살짝 띄우는 영역에 쓴다.
- **Background Cream (`{colors.background}` `#FFFCF4`)** — 순백이 아닌 **따뜻한 크림**. 친근함을 강화하고 눈의 피로를 줄이는 의도적 선택이다. 카드/팝오버 면(`{colors.card}` `#FFFFFF`)이 이 크림 위에 살짝 떠 보이게 한다.
- **Foreground (`{colors.foreground}` `#28200F`)** — 거의 검정에 가까운 웜 브라운. 크림 배경 위에서 WCAG AA 본문 대비를 확보한다.
- **Muted (`{colors.muted}` `#F4EDDF`)** / **Border (`{colors.border}` `#F4E2C2`)** — 면색·경계선으로 깊이를 만드는 베이스(그림자 대신). 톤은 크림에서 자연스럽게 이어진다.
- **Destructive (`{colors.destructive}` `#CC3328`)** — 파괴적 액션(예약 취소·삭제) 및 즐겨찾기 하트 활성색.

포커스 링은 채움 프라이머리(`#FF8A1E`)보다 진한 `#D86E0A`를 써서 크림 배경 대비 ≥3:1을 확보한다.

의미색(가용성)은 브랜드 웜과 **색상환에서 충분히 떨어뜨려** 핀 상태색이 프라이머리와 절대 충돌하지 않게 한다.

- **Available Green (`{colors.pin-available}` `#157F45`)** — 예약 가능 / success. 만다린 오렌지에서 멀리 떨어진 초록이라 "예약 가능"이 브랜드색과 혼동되지 않는다.
- **Full Gray (`{colors.pin-full}` `#7E7466`)** — 마감 상태. 채도를 낮춘 웜 그레이로 "비활성"임을 즉시 읽게 한다.

위 시맨틱 hex(success·destructive·pin-full·ring)는 WCAG 2.2 AA(배지/텍스트/그래픽 대비)에 맞춰 보정한 값이며, 만다린 채움 프라이머리(`#FF8A1E`)는 불변이다.

피해야 할 것: 프라이머리 만다린을 상태 의미로 쓰는 것, 그라데이션 면, 두 개 넘는 의미색 추가, 색만으로 상태를 표현하는 것(반드시 아이콘/텍스트 동반 — 핀·예약 가능 배지·슬롯 상태·인앱 배너 모두 적용).

참조 목업: [지도+바텀시트](mockups/key-map-bottomsheet.html), [상세+슬롯](mockups/key-detail-slotpicker.html), [챗봇 룸메이트](mockups/key-chatbot-roommate.html), [예약현황](mockups/key-reservation-list.html).

## Typography

**Pretendard** 한 패밀리로 전 역할을 운용한다. 한국어 우선 제품의 사실상 표준 서체로, 깔끔·친근·고가독이며 웹/RN 양쪽에 적용이 쉽다. shadcn의 타입 역할(`body`/`label`/`caption` 등)을 Pretendard로 치환하고, 스케일은 shadcn 기본 위에 구축한다.

핵심 규칙은 **한글을 위한 넉넉한 행간**이다. 본문(`{typography.body}`)은 line-height `1.6`을 기본으로 하여 한글 받침·조밀한 자형에서도 숨 쉴 공간을 준다. 제목은 `1.3`~`1.5`로 좁혀 묶음감을 준다.

램프:

- **display** (32px / 700) — 온보딩·빈 상태 히어로 등 큰 순간에만.
- **h1 / h2 / h3** (24 / 20 / 18px) — 화면 제목, 섹션 제목, 카드 제목.
- **body / body-sm** (16 / 14px) — 본문, 목록 보조 텍스트.
- **label** (14px / 500) — 버튼·폼 라벨·배지.
- **caption** (12px) — 메타(영업시간, 거리, 보조 안내).

올캡스 라벨이나 디스플레이 본문 남용은 피한다. 밀도가 높은 화면(지도/목록)에서도 `body-sm` 아래로 본문을 줄이지 않는다.

## Layout & Spacing

shadcn / Tailwind의 **4-기반 스페이싱 스케일**(`{spacing.1}`=4px … `{spacing.16}`=64px)을 상속한다. 별도 오버라이드 없이 그대로 쓴다.

밀도는 **균형형**으로, 화면 성격에 따라 조절한다.

- **지도 / 목록** — 정보 밀도 우선. 핀·카드·리스트 로우를 촘촘히 배치(작은~중간 갭, `{spacing.2}`~`{spacing.4}`).
- **예약 / 상세** — 여백 우선. 단계별 진행감을 위해 충분한 수직 리듬(`{spacing.6}`~`{spacing.8}`).

탐색 → 상세는 **같은 페이지 내 예약 전개** 패턴이다. 상세 진입 후 예약 확정까지 ≤3스텝을 시각적으로도 짧게 느끼도록, 슬롯 선택·확정 영역에 여백을 더 준다.

반응형: 모바일 앱은 단일 컬럼 + 하단 탭(1급 진입 3개: 스터디룸 찾기 / 예약현황 / 즐겨찾기). 웹은 동일 IA를 반응형으로 확장하되, 지도/목록 전환을 명시적으로 둔다. 플로팅 챗봇과 인앱 배너는 모든 주요 화면의 전역 레이어다.

## Elevation & Depth

엘리베이션은 **혼합(고도별)** 전략이다. 기본 면은 **플랫**(`{elevation.flat}`) — 경계선(`{colors.border}`)과 면색(`{colors.card}` vs `{colors.background}`)으로만 깊이를 구분하고 그림자를 쓰지 않는다. 카드·리스트 로우·패널은 모두 플랫이다.

**그림자는 진짜로 떠야 하는 요소에만** 허용한다:

- **바텀시트**(`{elevation.sheet}`) — 지도 위로 부드럽게 올라오는 카카오맵식 패턴. 상단 모서리만 둥글게(`{rounded.xl}`).
- **모달 / 다이얼로그**(`{elevation.dialog}`)
- **토스트**(`{elevation.toast}`)
- **플로팅 챗봇 버튼(FAB)**(`{elevation.fab}`)

그림자는 위계 장식이 아니라 "이 요소가 다른 면 위에 떠 있다"는 물리적 메타포로만 쓴다. 위계는 레이아웃·타이포·색이 책임진다.

## Shapes

**shadcn 기본 라운드**(radius `0.5rem` 패밀리)를 따른다. 친근하되 절제된 균형 — 활기는 색·모션이 내고, 형태는 과하게 둥글지 않게 한다.

- `{rounded.sm}` (0.25rem) — 인풋, 작은 칩.
- `{rounded.md}` (0.375rem) — 작은 버튼·태그.
- `{rounded.DEFAULT}` / `{rounded.lg}` (0.5rem) — 버튼, 카드, 다이얼로그.
- `{rounded.xl}` (0.75rem) — 바텀시트 상단 모서리.
- `{rounded.full}` — 배지(예약 가능), 챗봇 FAB, 아바타 등 진짜 원형/필만.

이미지는 항상 컨테이너 모서리 반경을 따른다. 극단적 라운딩(전체 필 버튼)은 배지·FAB 외에는 쓰지 않는다.

## Components

행동·상태 전이는 EXPERIENCE.md에 귀속되며, 여기서는 **시각 스펙**만 정의한다. shadcn 기본을 그대로 쓰는 컴포넌트(Button 비-primary 변형, Card 기본, Sheet, Dialog, Popover, Toast, Tabs 등)는 shadcn 스펙을 계약으로 삼는다. 아래는 브랜드 레이어 오버라이드 및 DeskNow 고유 컴포넌트다.

참조 목업: [지도+바텀시트](mockups/key-map-bottomsheet.html), [상세+슬롯](mockups/key-detail-slotpicker.html), [챗봇 룸메이트](mockups/key-chatbot-roommate.html), [예약현황](mockups/key-reservation-list.html). **충돌 시 스파인이 정본이다**(spines win on conflict).

- **맵 핀** — 가용성의 핵심 신호. **색은 절대 단독 신호가 아니며 항상 아이콘과 병행**한다. 예약 가능 = `{colors.pin-available}` 초록 + **체크 아이콘**, 마감 = `{colors.pin-full}` 회색 + **X 아이콘**. 색맹·저대비 환경에서도 아이콘으로 구분 가능해야 한다.
- **바텀시트** — `{colors.card}` 면, 상단만 `{rounded.xl}`, 떠 있는 요소이므로 그림자 허용. 핀 탭 시 지도 위로 올라와 룸 요약을 보여준다.
- **스터디룸 상세 레이아웃** — 같은 페이지 내 예약 전개. 상단 룸 정보(이미지 자리·제목 `h1`·메타 `caption`) → 캘린더+슬롯 피커 → 확정. 여백 우선(밀도 낮음).
- **캘린더 + 슬롯 피커** — 1시간 단위 고정 슬롯. 상태: **가용**(선택 가능, 기본 면+테두리), **비활성/마감**(`{colors.muted}` 배경 + `{colors.muted-foreground}` 텍스트, 클릭 불가), **선택-범위**(연속 슬롯만, `{colors.primary}` 강조 — 시작~끝 연속 표시). 비연속 선택은 시각적으로 불가능하게 막는다.
- **배지(예약 가능)** — `{colors.success}` 배경 + 흰 텍스트, `{rounded.full}`. **체크 아이콘 동반 필수.**
- **버튼(primary, 예약하기)** — `{colors.primary}` 채움 + `{colors.primary-foreground}` 텍스트 + `{rounded.DEFAULT}`. 나머지 변형은 shadcn 상속.
- **즐겨찾기 하트 토글** — 활성 = `{colors.destructive}` 채워진 하트, 비활성 = `{colors.muted-foreground}` 외곽선 하트.
- **인앱 배너** — 접속 시 노출되는 알림(도래 리마인드·상태변경). 면 위 플랫, `{colors.secondary}` 또는 `{colors.muted}` 배경 + 아이콘 + 텍스트. (푸시 아님.)
- **플로팅 챗봇 버튼(FAB, "룸메이트")** — `{colors.primary}` 원형(`{rounded.full}`), 떠 있는 요소이므로 그림자 허용. 모든 주요 화면 전역.
- **카드** — `{colors.card}` 면 + `{colors.border}` 테두리 + `{rounded.lg}`, **플랫**(그림자 없음). 목록의 룸 카드는 이미지·제목·거리/가용성 메타.
- **리스트 로우** — 지도/목록 화면의 촘촘한 행. 플랫, 하단 `{colors.border}` 디바이더로 구분.

## Do's and Don'ts

| Do | Don't |
|---|---|
| **모든 상태색에 아이콘/텍스트 라벨 병행** — 핀(가용=초록+체크, 마감=회색+X)뿐 아니라 예약 가능 배지·슬롯 상태·인앱 배너 전부 | 색만으로 가용성·상태를 표현(핀·배지·슬롯·배너 어디서든) |
| 가용성은 초록(`{colors.pin-available}`), 마감은 회색(`{colors.pin-full}`)으로 고정 | 웜 프라이머리(`{colors.primary}`)를 가용성·상태 의미로 사용 |
| 기본 면은 플랫(경계선·면색으로 깊이) | 위계 장식용 카드 그림자 |
| 그림자는 진짜 떠 있는 요소(바텀시트·모달·토스트·챗봇 FAB)에만 | 모든 면에 그림자를 깔아 깊이를 흉내 |
| shadcn 기본을 정본으로 상속, 델타만 오버라이드 | `primary`/`accent`/의미색·타이포 외 토큰을 임의 변경 |
| 크림 배경(`{colors.background}`) 위 WCAG AA 대비 유지 | 저대비 텍스트로 친근함과 가독성을 맞바꿈 |
| 활기는 색·모션·마이크로카피로 표현 | 형태를 과하게 둥글리거나 장식을 더해 활기를 냄 |
| 한글 가독성 위해 본문 행간 `1.6` 유지 | 밀도를 위해 본문을 `body-sm` 아래로 축소 |
| 연속 슬롯만 선택 가능하게 시각적으로 강제 | 비연속 슬롯 선택을 시각적으로 허용 |

---

### 모션 [ASSUMPTION]

사용자가 모션을 명시하지 않아, 활기·경쾌 감성에 맞춰 **부드럽되 약간 생기 있는 마이크로모션**을 가정한다: 짧은 스프링감, ≤100ms 로컬 피드백, 과하지 않게. 바텀시트의 떠오름, 슬롯 선택, 하트 토글 등 로컬 인터랙션에 적용한다. Finalize에서 검토 대상. (상세 모션 행동은 EXPERIENCE.md에 귀속.)

**접근성(가정 아님):** 모든 모션은 `prefers-reduced-motion`을 존중한다 — 해당 설정 시 비필수 애니메이션은 줄이거나 제거하고, ≤100ms 기능적 피드백만 유지한다. (위 모션 *성격*만 `[ASSUMPTION]`이며, reduced-motion 존중은 접근성 하한선이다.)
