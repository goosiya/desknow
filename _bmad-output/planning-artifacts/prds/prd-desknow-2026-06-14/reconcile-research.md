# 입력 정합성 점검: 기술 타당성 조사 ↔ PRD/Addendum

> **점검 대상 입력:** `research/technical-desknow-mvp-tech-feasibility-research-2026-06-13.md` (기술 타당성 조사)
> **비교 대상:** `prds/prd-desknow-2026-06-14/prd.md`, `prds/prd-desknow-2026-06-14/addendum.md`
> **점검 일자:** 2026-06-14
> **점검 원칙:** 리서치의 리스크/제약/제품영향 발견이 PRD에는 *가정·열린질문·제약·범위*로, addendum에는 *구현 인계*로 반영되어야 한다. 원시 리서치를 그대로 옮기는 것은 정합이 아니다.

---

## 1. 요약 판정

전반적으로 **반영 수준이 매우 높다.** 리서치가 "PRD 전 못 박아야 한다"고 지목한 3대 결정(카카오맵 / Railway 상시과금 / 비밀번호 NIST 충돌)과 핵심 발견(UNIQUE 제약 동시성)은 PRD 본문·열린질문·제약과 addendum에 모두 정확히 착지했다. Risk Register R1~R4도 대응 항목으로 반영됐다.

다만 **R5의 일부(카카오 SDK 네이티브 모듈 → EAS dev build 필요)**, **R6(Supabase→Railway 벡터 이관 미검증)의 리스크 지위**가 약하게 처리되어 있어 GAP으로 분류한다. 그 외 리서치의 통합 함정(CORS / API 버저닝)과 Redis 사실상 필수 뉘앙스가 PRD 표면에 약하게 드러난다.

---

## 2. 핵심 항목별 정합 매트릭스

### 2.1 PRD 전 확정 3대 결정

| 리서치 항목 | PRD/Addendum 반영 위치 | 상태 |
|---|---|---|
| ① 지도/주소 카카오맵 우선(네이버 무료정책 재편) | PRD §4.2 Description("카카오맵 기반"), FR-22, §6.1, §8 Q1(약관 적합성), §11 함의 / addendum "지도/주소" | **완전 반영** |
| ② Railway 상시 컨테이너 과금 인지 | PRD §11 Constraints(Cost) 상세, §6.2 단계적 분리 언급, addendum "비용/운영" | **완전 반영** |
| ③ 비밀번호 강제 복잡도 ↔ NIST SP 800-63B Rev.4 충돌 | PRD FR-3 Notes(NOTE FOR PM), §6.2(완화=차기), §8 Q5(완화 시점) | **완전 반영** |

### 2.2 Risk Register (R1~R6)

| 리서치 | PRD/Addendum 반영 | 상태 |
|---|---|---|
| R1 네이버 정책 재편 → 카카오맵 | §8 Q1, addendum 지도/주소, 검증스파이크 ① | **완전 반영** |
| R2 Railway 상시과금 | §11 Constraints, addendum 비용/운영 | **완전 반영** |
| R3 비밀번호 NIST 충돌 | FR-3 Notes, §6.2, §8 Q5 | **완전 반영** |
| R4 멀티 LLM 파라미터 비대칭(Anthropic 최신 모델 temperature 미지원 등) | FR-29 Consequences, addendum "챗봇" | **완전 반영** |
| R5 RN SSE 미지원 + 카카오 SDK 네이티브 모듈 | FR-30(RN 전송 제약), addendum 챗봇(RN EventSource·react-native-sse) | **부분 반영(GAP)** — 카카오 SDK 네이티브 모듈→**EAS development build/prebuild 필요**(Expo Go 불가), iOS Info.plist·Android 키해시 등록 선행이 PRD/addendum 어디에도 없음 |
| R6 Supabase→Railway 벡터 이관 미검증 | addendum 검증스파이크 ③에만 등장 | **부분 반영(GAP)** — *리스크/열린질문 지위가 아닌* 스파이크 항목으로만 존재. §8 Open Questions·§11에 운영 이관 리스크로 명시 안 됨 |

### 2.3 핵심 발견 — 동시성(UNIQUE 제약)

| 리서치 | PRD/Addendum 반영 | 상태 |
|---|---|---|
| 중복 예약 = 애플리케이션 락 아닌 `UNIQUE(room_id, slot_start)` 원자적 차단 | FR-15(보장=DB 제약), §10 신뢰성, SM-4(중복 0건), SM-C3, addendum 예약/슬롯 모델(EXCLUDE/PG18 WITHOUT OVERLAPS 확장 포함) | **완전 반영 (모범적)** |

---

## 3. GAP 목록 (각: 리서치 항목 / PRD 커버리지 / 심각도)

### GAP-1 — 카카오 SDK 네이티브 모듈의 EAS dev build 요구 (R5 후반부)
- **리서치 근거:** Integration §카카오톡 공유 — RN은 공식 SDK 없어 `@react-native-kakao/share` 사용, **네이티브 모듈이라 Expo Go 불가 → EAS development build/prebuild 필요**, iOS Info.plist(URL 스킴·LSApplicationQueriesSchemes)·Android 키해시 등록 선행. R5에도 "카카오 SDK 네이티브 모듈"로 명시.
- **PRD/Addendum 커버리지:** FR-19(카카오톡 공유)는 기능만 기술. addendum은 RN SSE의 EventSource 제약만 다루고 **카카오 공유의 네이티브 모듈/EAS dev build/플랫폼 등록 선행 조건은 누락**. 빌드 파이프라인(Expo Go로 개발 불가)에 직접 영향을 주는 제약인데 인계가 안 됨.
- **심각도:** **중(Medium)** — 기능 자체는 가능하나, 개발 워크플로(Expo Go 사용 불가)와 사전 등록 작업을 모르면 일정 함정. addendum "챗봇/지도" 옆에 "공유(RN 구현 유의)" 한 줄 추가 권장.

### GAP-2 — Supabase→Railway 벡터 이관 미검증 리스크의 지위 격하 (R6)
- **리서치 근거:** R6(신뢰도 Medium) + Tech Stack §Supabase→Railway 이관 — pgvector 미설치 타깃에 restore 시 vector 컬럼 복원 실패, 인덱스 재빌드 시간 유의, "운영 이관 시 실패" 영향.
- **PRD/Addendum 커버리지:** addendum 맨 끝 "검증 스파이크 ③"으로만 등장. PRD §8 Open Questions에 **이관 리스크/검증 필요가 열린 질문으로 올라가 있지 않음**. 리서치가 명시적으로 Risk Register에 올린 항목이 PRD 표면에서 리스크 가시성을 잃음.
- **심각도:** **저~중(Low-Medium)** — MVP가 신규 Railway pgvector로 시작하면 이관 자체가 없을 수도 있으나, 브리프/idea가 Supabase 출발을 전제했다면 실제 리스크. §8에 "초기 DB를 Supabase로 시작할지/이관 검증 필요"를 열린 질문으로 추가 권장.

### GAP-3 — REST 통합 함정(CORS / API 버저닝)의 PRD 부재
- **리서치 근거:** Integration §웹/앱↔FastAPI REST — ① CORS(웹만 깨짐), ② `/api/v1` 버저닝(모바일 구버전 장기 잔존→하위호환), ③ RN localhost 접근 불가. "흔한 함정"으로 강조.
- **PRD/Addendum 커버리지:** PRD §14 Platform이 "OpenAPI 계약·surface별 구현 차이는 addendum"이라 했으나, addendum에 **CORS/API 버저닝 항목이 명시되지 않음**(OpenAPI→TS SDK 자동생성만 언급). 아키텍처 단계로 자연스럽게 흡수될 항목이긴 하나, 리서치가 "흔히 빠뜨림"으로 못 박은 부분이라 인계 누락 시 재발 위험.
- **심각도:** **저(Low)** — 순수 구현/아키텍처 영역이라 PRD 본문엔 부적합. addendum "아키텍처 방향"에 한 줄(CORS origin 등록·API 버저닝 하위호환) 추가면 충분.

### GAP-4 — refresh 무효화 저장소 "사실상 필수"의 뉘앙스 약화
- **리서치 근거:** §인증 — 즉시 무효화를 위해 **서버측 저장소(Redis 또는 DB)가 사실상 필수**, "Redis 도입 여부가 핵심 결정 포인트".
- **PRD/Addendum 커버리지:** PRD §8 Q2·addendum 인증에서 "Redis vs DB는 아키텍처 단계 확정"으로 *선택지*로만 제시. "사실상 필수"라는 강제성(저장소 없이는 즉시 로그아웃/무효화 불가)이 §10 보안 NFR에 명시되지 않음(FR-2 로그아웃은 기능으로만 존재).
- **심각도:** **저(Low)** — 선택지로 열어둔 것 자체는 PRD 정합에 부합. 단 "무효화 저장소 없이 즉시 로그아웃 보장 불가"라는 제약 사실은 보존 가치 있음. §10 보안 또는 Q2 설명에 한 줄 보강 권장.

### GAP-5 — 챗봇 별도 서비스 배포 vs §6.2 "API 통합 후 분리"의 표면적 상충
- **리서치 근거:** Architecture §System — 챗봇은 "같은 레포·별도 프로세스/서비스 배포"(동기 예약 API 워커 풀 잠금 방지)가 권고. 동시에 R2/로드맵은 비용 위해 "초기엔 API에 통합 후 분리" 단계적 접근도 제시.
- **PRD/Addendum 커버리지:** addendum "아키텍처 방향"=별도 서비스 배포, PRD §11·§6.2=초기 통합 후 분리 — **두 권고가 같은 문서군에 병존하나 어느 것을 MVP 기본값으로 할지 미결**. 리서치 자체가 트레이드오프로 남긴 것이므로 distortion은 아니나, 결정 미정 상태가 열린 질문으로 명시돼 있지 않음.
- **심각도:** **저(Low)** — 의도된 트레이드오프. §8에 "챗봇 초기 배포 형태(통합 vs 분리)" 열린 질문 1줄 추가하면 결정 추적성 확보.

---

## 4. 정합 우수 항목 (왜곡·누락 없음, 참고)

- **카카오맵 채택·약관 확인**: 결정+열린질문+구현유의로 3중 착지. 모범.
- **Railway 상시과금**: 제약(§11)으로 정확히 캐스팅, 단계적 분리·비용 모니터링까지 인계.
- **비밀번호 NIST 충돌**: "MVP 수용 + 차기 완화"를 FR Notes·범위·열린질문 일관 처리. 리서치 권고와 정확히 일치.
- **UNIQUE 동시성**: FR-15·NFR·성공지표(SM-4)·반패턴(SM-C3)·addendum 확장경로까지 가장 완성도 높은 반영.
- **멀티 LLM 파라미터 비대칭(R4)**: FR-29와 addendum에 Anthropic 최신 모델 temperature 미지원 예시까지 보존.
- **임베딩 단일 고정**: FR-33 Notes·§8 Q3·assumptions index 일관.
- **인앱 배너(푸시 아님)**: idea "1일 기준" 해석(D3=24h)까지 addendum에 근거 보존.

---

## 5. 권고 조치 (우선순위)

1. **(중) GAP-1** — addendum에 "공유(RN 구현 유의)" 추가: 카카오 RN 공유는 네이티브 모듈 → **EAS dev build 필요(Expo Go 불가)**, iOS URL스킴/LSApplicationQueriesSchemes·Android 키해시 등록 선행.
2. **(저~중) GAP-2** — PRD §8에 "초기 DB Supabase 시작 여부 및 Railway pgvector 이관 검증 필요(R6)" 열린 질문 추가.
3. **(저) GAP-3** — addendum 아키텍처 방향에 CORS origin 등록·`/api/v1` 하위호환 한 줄.
4. **(저) GAP-4** — §10 또는 §8 Q2에 "무효화 저장소 없이는 즉시 로그아웃/무효화 불가" 제약 명시.
5. **(저) GAP-5** — §8에 "챗봇 초기 배포 형태(통합 vs 분리)" 결정 미정 명시.

> 결론: 리서치의 **제품영향 핵심(3대 결정 + 동시성 + R1~R4)**은 왜곡 없이 정확히 반영됨. 잔여 GAP은 모두 **누락(중 1 / 저 4)** 성격이며 distortion(왜곡)은 발견되지 않음. GAP-1만 일정 함정 가능성으로 중요도가 있고 나머지는 인계 보강 수준.
