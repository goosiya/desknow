"""notifications 도메인 모듈 (Story 5.1 — 인앱 배너 인프라).

통합 ``notifications`` 테이블 + 서비스 프리미티브(create/list_pending/dismiss) + 조회/소멸
엔드포인트를 세운다. Epic 4의 ``reservations`` foundation(4.1)과 동형 — 데이터 계층·전역
배너 표면만 책임지고, **실제 트리거(행 생성)는 후속에 위임**한다: 도래 리마인드 도출=5.2,
상태변경 통지 생성=6.2(거절)/8.3(임의취소) 배선·표시 정밀 카피=5.3. (FR-18·18a)
"""
