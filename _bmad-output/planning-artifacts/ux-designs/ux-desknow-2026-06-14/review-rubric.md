# Spine Pair Review — desknow

## Overall verdict

The DeskNow spine pair is **strong-to-adequate** and consumer-ready in substance: every PRD UJ has a named-protagonist Key Flow with climax and failure path, the state matrix is exhaustive with explicit N/A justification, every DESIGN token and prose `{token}` reference resolves, and product-specific contracts (concurrency, timezone, chatbot) are committed in dedicated sections that downstream architecture/story-dev can source-extract verbatim. Two real defects block a perfectly clean source-extraction: EXPERIENCE.md references `{elevation.sheet}` / `{elevation.fab}` which resolve to **no DESIGN frontmatter token** (elevation is prose + literal component strings only), and the visual-reference contract is **vacuous** — both spines point at `mockups/` HTML that does not exist while the only working file is a color-palette HTML (no screen mockups at all, not just pending promotion). Neither corrupts the behavioral/visual contract, but both should be fixed before this is treated as the finalized contract.

## 1. Flow coverage — strong

Checked: all 4 PRD UJs (UJ-1..UJ-4) → present as Key Flows with verbatim names, named protagonists (지우/민재/현우/누구든), numbered steps, explicit **Climax** beat, Resolution, and Edge/failure path where applicable (UJ-1 concurrency edge, UJ-2 location-denied edge). Admin/cross-cutting FRs (FR-3, FR-29, FR-31~33) correctly have **no** flow — PRD §2.2 marks them as intentionally non-UJ-realizing, and the spine's self-check names this as intended non-realization, not a miss. PRD performance bars (3-step, 3-min, 5-min register, 2s first token) are woven into the climax beats.

### Findings
- **low** UJ-3 has no failure/edge path while UJ-1 and UJ-2 do (EXPERIENCE.md:235-242). Provider registration has plausible failure modes (address-search miss, save failure) — the State matrix row "제공자 등록" covers them, but the flow itself omits an edge beat. *Fix:* add a one-line Edge to UJ-3 (e.g., 주소 검색 실패 → 입력 보존 + 재시도) for parity, or note the State row carries it.

## 2. Token completeness — adequate

Checked: every YAML token in DESIGN.md frontmatter is defined; every `{path.to.token}` prose/component reference in DESIGN.md (≈70 refs) resolves to a defined token; all color tokens carry hex values (no missing-hex criticals). Contrast intent is stated for load-bearing combos (cream bg + foreground WCAG AA, primary-foreground warm-brown chosen over pure white) but **no numeric ratios** are committed.

### Findings
- **medium** No measured contrast ratios for load-bearing combos (DESIGN.md:173, 263). Cream `#FFFCF4` + foreground `#28200F`, white text on `success #19A65A` badge, and pin colors on map tiles are asserted "AA" without numbers. The warm-brown `primary-foreground #3A2400` on `primary #FF8A1E` is the riskiest (both mid-tone) and unverified. *Fix:* add ratio targets/measured values for bg+fg, badge text, and primary-fg-on-primary; the pair claims "brand overrides verified to maintain ratios" (EXPERIENCE.md:155) — commit the numbers that back that claim.
- **low** `{typography.body}` is referenced in prose (DESIGN.md:188) to cite line-height 1.6; resolves cleanly. No issue — noted only because it is the sole typography token reference, so the rest of the type ramp is defined-but-unreferenced (acceptable for a ramp).

## 3. Component coverage — adequate

Checked: components used in EXPERIENCE.Component Patterns vs DESIGN.Components. Matched (visual + behavioral both present): 지도+핀, 바텀시트, 상세 내 예약 전개 / 스터디룸 상세 레이아웃, 달력+슬롯 피커, 즐겨찾기 토글, 인앱 배너, 플로팅 챗봇 FAB, 카드, 리스트 로우, 배지(예약 가능), 버튼-primary. shadcn-inherited components (Sheet/Dialog/Toast/Tabs/Popover) correctly named as contract-by-inheritance in both.

### Findings
- **low** Naming drift between sections (not broken, but a consumer mapping cost): DESIGN calls it "상세 내 예약 전개" is EXPERIENCE's term while DESIGN titles the row "스터디룸 상세 레이아웃" + "캘린더 + 슬롯 피커"; EXPERIENCE row is "달력 + 슬롯 피커" (달력 vs 캘린더). Same component, two spellings. *Fix:* pick one term (캘린더/슬롯 피커) and use it identically in both files.
- **low** "지도 + 핀" (EXPERIENCE behavioral row) maps to DESIGN's "맵 핀" (visual row) — the map surface itself has no DESIGN visual row, only the pin. Acceptable (map is a 3rd-party카카오맵 surface), but the name pairing is implicit. *Fix:* optional — align to "맵 핀 / 지도+핀" or note the map is vendor-owned.

## 4. State coverage — strong

Checked: State matrix walks every user IA surface × {빈/에러/오프라인/로딩}. Every cell is designed; the single N/A (상세 빈 상태) is explicitly justified ("룸이 있어야 진입"), not a gap. Permission-denied (위치 권한 거부) is a dedicated row with concrete bypass (행정동 콤보), and the PRD-mandated hard cells (지도 로드 실패, 목록 결과없음, 슬롯 동시성 충돌, 챗봇 범위밖/모름, 권한거부 우회) are all present and called out. Offline behavior is specified per surface (cache + toast).

### Findings
- **low** Admin-web surfaces (계정 관리, 예약 임의취소, 챗봇 문서 인제스트) have no State-matrix rows; only 제공자 등록 from the provider area is in the matrix. Admin is intentionally non-UJ and low-fidelity ("모바일 대응 부차적"), so this is defensible, but a story-dev building the admin app gets no empty/error/loading guidance for it. *Fix:* add a single coarse admin row, or state once that admin states inherit shadcn data-table defaults and are out of the experience-matrix scope.

## 5. Visual reference coverage — broken

Checked the folder: present = `.working/color-themes-1.html` (the D-05 palette picker), empty `imports/`, **no** `mockups/` folder, **no** `key-*.html` screen mockups anywhere. EXPERIENCE.md links generically to "`mockups/` 내 화면 HTML" (line 80); DESIGN.md has **no** visual-reference link at all. Spine-wins-on-conflict is stated once (EXPERIENCE.md:80).

### Findings
- **high** The visual-reference contract points at nothing. EXPERIENCE.md:80 links `mockups/` HTML that does not exist, and there are no `key-*.html` mocks in `.working/` to be promoted later — the only HTML is the color-palette tool, which is not a screen composition. The prompt's "judge pending promotion leniently" assumes mocks exist in `.working/`; they do not. A consumer following the link finds a dead path. *Fix:* either produce the screen mockups (지도/바텀시트/상세-예약전개/슬롯피커/챗봇 are the load-bearing ones) and link them per-section, or — if no mockups are planned for MVP — remove/soften the EXPERIENCE.md:80 pointer so it doesn't dangle.
- **medium** DESIGN.md links no visual reference at all and does not cite the palette source `.working/color-themes-1.html` that D-05 selected. *Fix:* add the palette-source reference (and per-component visual mocks if produced) so the visual spine traces to its picked artifact.
- **low** `color-themes-1.html` is an orphan relative to the spines — selected in the decision log (D-05) but unlinked from DESIGN.md. Not a conflict, just untraced. *Fix:* one-line cite in DESIGN.Colors.

## Mechanical notes

- **Broken cross-ref (high):** EXPERIENCE.md:111 `{elevation.sheet}` and EXPERIENCE.md:116 `{elevation.fab}` do **not resolve** — DESIGN.md has no `elevation` frontmatter token group. DESIGN expresses elevation as prose (## Elevation & Depth) and as literal component string values (`elevation: floating` / `elevation: flat`), not as addressable `{elevation.*}` tokens. A resolver flattening EXPERIENCE refs against DESIGN frontmatter will fail on these two. *Fix:* either add an `elevation` token group to DESIGN frontmatter (e.g., `elevation: { sheet: ..., fab: ..., flat: none }`) and have components reference `{elevation.sheet}`, or change EXPERIENCE to prose ("그림자 — DESIGN.Elevation 참조") and drop the token syntax. Pick one; right now the two files disagree on whether elevation is a token.
- **Section-name ref (low):** EXPERIENCE.md:148 cites `DESIGN.md.Motion`; DESIGN's motion lives under `### 모션 [ASSUMPTION]` nested below Do's & Don'ts, not a top-level `## Motion`. Resolves by intent but the anchor name differs. *Fix:* promote to `## Motion` or cite the actual heading.
- **Frontmatter:** Both files `status: draft` (consistent, pre-finalize). EXPERIENCE.design_ref → ./DESIGN.md ✔. Both share identical `sources` list resolving to real PRD/brief/research/idea paths ✔. DESIGN carries `ui_system: shadcn` and `document_output_language: korean` (extra keys beyond spec table — harmless, informative).
- **Inheritance discipline:** UJ names verbatim from PRD ✔. Glossary terms (바텀시트, 핀, 인앱 배너, 룸메이트) used consistently ✔. Concurrency/timezone/chatbot product-specific sections mirror PRD FR-15/§10/FR-25~30 faithfully without contradiction ✔.
- **Shape fit:** DESIGN body follows canonical order (Brand & Style → Colors → Typography → Layout → Elevation → Shapes → Components → Do's/Don'ts), with Motion appended as a flagged ASSUMPTION addendum ✔. EXPERIENCE has all required defaults (Foundation, IA, Voice/Tone, Component Patterns, State, Interaction Primitives, A11y, Responsive, Key Flows) plus required-when-applicable product sections ✔.
- **Bloat:** low. The product-specific sections (시간·타임존, 동시성, 챗봇) could be seen as PRD restatement, but they translate FRs into UX-decision form (graceful failure copy, adjacent-slot re-display, keyboard alt for drag) — load-bearing for story-dev, not bloat. Self-check section at EXPERIENCE end is process scaffolding that could be trimmed at finalize but harms nothing.
