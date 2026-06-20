---
stepsCompleted: [step-01-document-discovery, step-02-prd-analysis, step-03-epic-coverage-validation, step-04-ux-alignment, step-05-epic-quality-review, step-06-final-assessment]
documentsIncluded:
  - prds/prd-desknow-2026-06-14/prd.md
  - architecture.md
  - epics.md
  - ux-designs/ux-desknow-2026-06-14/DESIGN.md
  - ux-designs/ux-desknow-2026-06-14/EXPERIENCE.md
---

# Implementation Readiness Assessment Report

**Date:** 2026-06-14
**Project:** desknow

## Document Inventory

| 유형 | 정본 파일 | 상태 |
|------|-----------|------|
| PRD | `prds/prd-desknow-2026-06-14/prd.md` | ✅ |
| Architecture | `architecture.md` | ✅ |
| Epics & Stories | `epics.md` (8 에픽 / 48 스토리) | ✅ |
| UX Design | `ux-designs/ux-desknow-2026-06-14/DESIGN.md`, `EXPERIENCE.md` | ✅ |

- 중복 문서: 없음
- 누락 필수 문서: 없음
- `project-context.md`: 없음 (그린필드 — 정상)

## PRD Analysis

### Functional Requirements (총 34개: FR-1~33 + FR-18a)

| FR | 요약 | Realizes |
|----|------|----------|
| FR-1 | 이메일 회원가입(역할 지정·중복 차단) | UJ-1,2,3 |
| FR-2 | 로그인/로그아웃/세션 유지·역할 확정 | UJ-1~4 |
| FR-3 | 비밀번호 정책(8자+대/특/숫·해싱) *횡단* | — |
| FR-4 | 첫 진입 지도+주변 핀(≤2초) | UJ-2 |
| FR-5 | 핀 색상 예약 가능 구분(서버 집계+보조표식) | UJ-2 |
| FR-6 | 바텀시트 요약(1차 정보 스크롤 없이) | UJ-1,2 |
| FR-7 | 위치 권한 거부 우회(행정동 목록) | UJ-2 |
| FR-8 | 행정동 콤보 목록 조회 | UJ-1 |
| FR-9 | 반경 검색(기본 3km·조정) | UJ-2 |
| FR-10 | 즐겨찾기 추가/조회(비활성 라벨) | UJ-1 |
| FR-11 | 상세 정보 화면(같은 페이지 예약 전개) | UJ-1,2 |
| FR-12 | 날짜·슬롯 가용성 표시 | UJ-1,2 |
| FR-13 | 연속 슬롯 선택(비연속 불허 D1) | UJ-1 |
| FR-14 | 즉시 예약(결제 없음·3스텝·all-or-nothing) | UJ-1,2 |
| FR-15 | 중복 예약 방지(동시성·부분점유 0) | UJ-1(edge) |
| FR-16 | 예약 취소(시작 6h 전·원자 재활성) | UJ-2 |
| FR-17 | 예약현황/히스토리(예약자) | UJ-1,2 |
| FR-18 | 예약 도래 인앱 배너(24h) | UJ-1 |
| FR-18a | 상태변경 통지 배너(거절·임의취소) | UJ-3 |
| FR-19 | 카카오톡 예약 공유 | UJ-1 |
| FR-20 | 후기 작성(이용완료·1회·1~5·500자) | UJ-1 |
| FR-21 | 후기 답글(제공자) | UJ-3 |
| FR-22 | 스터디룸 등록/수정(제공자당 1개·5분) | UJ-3 |
| FR-23 | 예약현황 조회(제공자·이메일 비노출) | UJ-3 |
| FR-24 | 예약 거절(시작 전·원자 재활성) | UJ-3 |
| FR-25 | 플로팅 진입+세션 대화 유지 | UJ-4 |
| FR-26 | 서비스 안내 문서 RAG(3분기) | UJ-4 |
| FR-27 | 자연어 예약 검색(상위 3+더보기) | UJ-4 |
| FR-28 | 범위 밖 질문 거절 | UJ-4 |
| FR-29 | 멀티 LLM 스위칭(공통 5종) *횡단* | — |
| FR-30 | 응답 스트리밍(첫 토큰 ≤2초) | UJ-4 |
| FR-31 | 계정 관리·비활성 *운영* | — |
| FR-32 | 예약 임의 취소 *운영* | — |
| FR-33 | 챗봇 문서 인제스트 관리(멱등) *운영* | — |

### Non-Functional Requirements (PRD §10 횡단)

- **NFR-1 시간·타임존:** slot_start UTC 저장 / 판정은 Asia/Seoul. FR-5·12·16·18·20의 시간경계 전제.
- **NFR-2 성능:** 첫 지도 ≤2초, 챗봇 첫 토큰 ≤2초(p90), 로컬 UI 피드백 ≤100ms.
- **NFR-3 예약 단순성:** 단독 예약 상세 진입~3스텝.
- **NFR-4 시각 완성도·일관성:** 디자인 토큰 기반 웹/앱 이질감 제로.
- **NFR-5 접근성·상태 설계:** 키보드/스크린리더(WCAG 2.2 AA), 색 비의존, 빈/에러/오프라인/로딩 매트릭스.
- **NFR-6 보안:** API 키 백엔드 격리, 단일 토큰 웹/앱 공용, 역할 백엔드 강제, 스트리밍 인증, 비밀번호 해싱.
- **NFR-7 신뢰성·데이터 정합성:** 동시 예약 중복·부분점유 0(DB 제약+단일 트랜잭션), 상태 전이 원자·멱등.

### PRD Completeness Assessment

PRD는 §0~§14 완결 구조 — Glossary로 어휘 고정, FR마다 testable Consequences + UJ realize 인라인 참조, ASSUMPTION 색인(§9), Non-Goals/Out of Scope 명시, Success Metrics에 counter-metric까지 포함. 관리자성 FR(FR-3·29·31~33)이 UJ를 realize하지 않는 것은 §2.2에서 **의도된 누락**으로 명시. 구현 세부(스택·전송)는 addendum/리서치로 위임. **완성도·명확성 높음 — 추적성 검증에 충분한 입력.**

## Epic Coverage Validation

### Coverage Matrix (PRD FR → Epic)

| FR | Epic | Status |
|----|------|--------|
| FR-1, FR-2, FR-3 | Epic 1 (계정/인증) | ✓ Covered |
| FR-22 | Epic 2 (제공자 공간 등록) | ✓ Covered |
| FR-4~FR-10 | Epic 3 (탐색: 지도·목록·즐겨찾기) | ✓ Covered |
| FR-11~FR-17 | Epic 4 (예약 핵심) | ✓ Covered |
| FR-18, FR-18a, FR-19, FR-20, FR-21 | Epic 5 (예약 후 경험) | ✓ Covered |
| FR-23, FR-24 | Epic 6 (제공자 예약 관리) | ✓ Covered |
| FR-25~FR-30 | Epic 7 (챗봇) | ✓ Covered |
| FR-31, FR-32, FR-33 | Epic 8 (운영) | ✓ Covered |

### Missing Requirements

- **없음.** PRD 34개 FR 전부가 에픽 문서의 명시적 FR Coverage Map(라인 154–191)에 매핑됨.
- 역방향(에픽엔 있으나 PRD에 없는 FR)도 없음 — 에픽의 FR 집합 = PRD FR 집합.
- NFR-1~7, UX-DR1~13, Architecture 요건도 각각 NFR/UX-DR/Additional 커버리지 절(라인 193–197)에 에픽 매핑 존재.

### Coverage Statistics

- Total PRD FRs: **34**
- FRs covered in epics: **34**
- Coverage percentage: **100%**

## UX Alignment Assessment

### UX Document Status

**Found** — DESIGN.md(시각 정본) + EXPERIENCE.md(행동 정본) + 검토 산출물(접근성·루브릭·검증 리포트) + 목업 4종(`key-map-bottomsheet`, `key-detail-slotpicker`, `key-chatbot-roommate`, `key-reservation-list` — 전부 실재 확인).

### UX ↔ PRD Alignment

- DESIGN.md frontmatter `sources`에 PRD를 명시 인용 → UJ-1~4, 7개 마찰 지점, 미감의 닻(토스·에어비앤비·카카오맵)이 PRD §12와 일치.
- UX-DR1~13이 PRD FR/NFR을 직접 realize: 핀 색 비의존(FR-5/§10 접근성), 연속 슬롯 강제(FR-13), 인앱 배너 2종(FR-18·18a), 챗봇 FAB(FR-25~30), 상태 매트릭스(§10 접근성·상태 설계).
- UX 고유 요구 중 PRD에 없는 항목: **없음**(모션 성격만 `[ASSUMPTION]`으로 표기, reduced-motion 존중은 접근성 하한선으로 확정).

### UX ↔ Architecture Alignment

| UX 요구 | Architecture 지원 | 정합 |
|---------|-------------------|------|
| shadcn/Tailwind 디자인 토큰 공유(UX-DR1) | `packages/ui`로 web/admin/mobile 공유, DESIGN.md 토큰 매핑(§Frontend) | ✓ |
| 핀 색 = 서버 집계(UX-DR2) | 핀 색 = 서버측 집계 엔드포인트, 클라이언트 N회 계산 금지(안티패턴) | ✓ |
| 옵티미스틱 ≤100ms(UX-DR7·12) | TanStack Query 옵티미스틱(즐겨찾기·슬롯 선택) | ✓ |
| 챗봇 FAB 스트리밍(UX-DR6) | SSE(text/event-stream), 웹 EventSource / RN react-native-sse | ✓ |
| 인앱 배너 2종(UX-DR5) | `notifications` 도메인(pending/dismiss) + 전역 배너 컴포넌트 | ✓ |
| 상태 매트릭스 빈셀 0(UX-DR9/NFR-5) | 접근성 ✅ 상태 매트릭스(EXPERIENCE.md 승계), 화면별 스켈레톤 | ✓ |
| 슬롯 피커 연속 강제(UX-DR4) | UNIQUE+트랜잭션 데이터 모델, 슬롯 도출 규칙 | ✓ |

### Alignment Issues

- **없음.** PRD ↔ UX ↔ Architecture 3자 정합. Architecture 자체 검증(§Requirements Coverage)도 접근성·성능·UX 토큰을 명시적으로 커버.

### Warnings

- **경미(차단 아님):** DESIGN.md 모션 *성격*이 `[ASSUMPTION]` 상태 — Finalize에서 확정 대상으로 명기됨. 구현 시 마이크로모션 톤만 확정하면 되며, 접근성(reduced-motion)은 이미 하한선으로 고정되어 구현 차단 요소가 아님.

## Epic Quality Review

*검토 기준: create-epics-and-stories 베스트 프랙티스 — 사용자 가치, 에픽 독립성, 순방향 의존 금지, 스토리 사이징, AC 품질, DB 테이블 적시 생성, 스타터 템플릿.*

### Best Practices Compliance Checklist

| 항목 | 결과 | 근거 |
|------|------|------|
| 에픽이 사용자 가치 전달 | ✅ | E2~E8 전부 사용자/운영자 결과 중심. E1은 foundation 에픽이나 가입·로그인 사용자 가치 포함 |
| 에픽 독립성(N이 N+1 불요) | ✅ | 모든 에픽 간 의존이 **후방**(E6→E5, E8→E5·E7) — 순방향 차단 위반 0 |
| 스토리 적정 사이징 | ✅ | 48 스토리 모두 단일 책임, 독립 완료 가능 |
| 순방향 의존 없음 | ✅(설계적 처리) | 잠재 순방향 3건 모두 명시적으로 후방/독립 설계로 해소(아래 참조) |
| DB 테이블 적시 생성 | ✅ | 1.4가 빈 베이스라인만, 각 도메인이 필요 시점에 테이블 생성(2.1·3.7·4.1·5.1·5.5·1.8) |
| AC 명확성(BDD) | ✅ | 전 스토리 Given/When/Then, 에러·경계·동시성 케이스 포함 |
| FR 추적성 유지 | ✅ | 각 스토리에 FR/UJ/UX-DR/NFR 인라인 참조 |
| 스타터 템플릿 → E1 S1 | ✅ | 아키텍처 하이브리드 스캐폴드 → Story 1.2 스캐폴드(1.1은 사람 선행 외부 가입) |
| 그린필드 셋업/CI | ✅ | 1.2 스캐폴드 · 1.3 Phase 0 스파이크 · 1.9 SDK drift CI |

### 🔴 Critical Violations

- **없음.** 기술 밀어내기형 에픽(no user value), 독립성 깨는 순방향 의존, 완료 불가 에픽-크기 스토리 모두 발견되지 않음.

### 🟠 Major Issues

- **없음.** 모호한 AC, 미래 스토리 요구, DB 일괄 선행 생성 위반 모두 없음.

### 🟡 Minor Concerns (설계적으로 이미 처리됨 — 차단 아님)

1. **Epic 1이 foundation/인프라 에픽** — 일반 규칙상 "Authentication System"은 borderline이나, ① 걸음마 골격(walking skeleton) 패턴 + ② 아키텍처가 스타터 템플릿을 명시 → E1 S1 셋업 의무 충족 + ③ 가입·로그인이라는 실제 사용자 가치 포함. **수용 가능**.
2. **Story 5.3(상태변경 통지 배너) 소비자가 생산자(6.2 거절·8.3 임의취소)보다 먼저 구축** — 알림 채널을 트리거보다 먼저 만드는 일반 패턴. 시드 알림 레코드로 독립 빌드·테스트 가능하나, 실제 트리거 연동 e2e 데모는 E6/E8 완료 후. **독립 완료성 충족 — 시퀀싱 관찰사항**.
3. **Story 3.1(가용성 집계)과 4.9(예약 차감 연결) 분리** — 3.1은 reservations 미존재 시점이라 예약 집합을 공집합으로 취급하고, 실제 차감은 4.9에서 연결. **명시적으로 문서화된 의도된 설계**로 3.1이 독립 동작(공집합)하므로 순방향 의존 아님. 잘 엔지니어링됨.

### Remediation Guidance

- 위 3건은 모두 에픽 문서가 인라인 주석으로 의도를 명시(예: "순방향 의존 아님", "예약 차감 연결은 Story 4.9에서")하고 있어 **수정 불필요**.
- 스프린트 계획 시 권고: **E5 → E6 → E8 순서를 유지**(통지 배너 인프라 5.1·5.3이 거절·임의취소 트리거보다 선행)하고, 3.1의 가용성 정확성 검증은 **4.9 완료 후 회귀 테스트**로 확정.

## Summary and Recommendations

### Overall Readiness Status

## ✅ READY (구현 준비 완료)

PRD · UX · Architecture · Epics/Stories 4종 산출물이 상호 정합하며, 구현을 차단하는 결함이 없습니다.

### Assessment Scorecard

| 검증 영역 | 결과 |
|-----------|------|
| 문서 인벤토리(중복·누락) | ✅ 정본 4종 완비, 중복·누락 0 |
| FR 커버리지(PRD→에픽) | ✅ 34/34 (100%), 역방향 누락도 0 |
| NFR/UX-DR/Architecture 커버리지 | ✅ NFR-1~7·UX-DR1~13·기술요건 전부 에픽 매핑 |
| UX ↔ PRD ↔ Architecture 정합 | ✅ 3자 정합, 불일치 0 |
| 에픽/스토리 품질 | ✅ Critical 0 · Major 0 · Minor 3(설계적 처리됨) |

### Critical Issues Requiring Immediate Action

- **없음.** 구현 착수 전 반드시 해결해야 하는 차단 이슈가 발견되지 않았습니다.

### Recommended Next Steps

1. **[SP] 스프린트 계획 수립** (`bmad-sprint-planning`) — 48개 스토리의 구현 순서를 확정. 에픽 순서 **E1→E2→E3→E4→E5→E6→E7→E8**을 기본으로 하되, 본 보고서의 시퀀싱 권고(5.1·5.3 통지 인프라가 6.2·8.3 트리거보다 선행, 3.1 검증은 4.9 후 회귀)를 반영.
2. **Story 1.1(외부 서비스 가입) 선 착수** — 카카오/OpenAI/Anthropic/Google/Railway 가입·과금·키 발급은 사람만 수행 가능한 선행 작업이며, Phase 0 스파이크·챗봇·배포의 차단 요소. **가장 먼저 시작 권장**.
3. **Story 1.3 Phase 0 스파이크 3종 검증** — ① 카카오맵 e2e + 약관 적합성 1차 확인(부적합 시 지도 제공자 대안), ② SSE 스트리밍(FastAPI↔웹↔RN), ③ pgvector 이관. 본 구현 착수 전 리스크 차단.
4. **(선택) 모션 성격 확정** — DESIGN.md 모션 `[ASSUMPTION]`을 UI 셸(Story 1.6) 구현 시점에 확정. 비차단.

### Final Note

이 평가는 6단계(문서 발견 → PRD 분석 → 에픽 커버리지 → UX 정합 → 에픽 품질 → 종합)에 걸쳐 진행되었으며, **Critical/Major 결함 0건, 설계적으로 이미 처리된 Minor 관찰 3건**을 식별했습니다. DeskNow 계획 산출물은 구현 단계로 진행할 준비가 되어 있습니다. 위 권장 순서대로 **스프린트 계획**부터 시작하시면 됩니다.

---

**Assessment Date:** 2026-06-14
**Assessor:** Implementation Readiness 워크플로우 (PM 역할)
**Documents Assessed:** prd.md · architecture.md · epics.md(8 에픽 48 스토리) · DESIGN.md · EXPERIENCE.md
**Status:** READY FOR IMPLEMENTATION
