"""favorites 도메인 모듈 (Story 3.7 — FR-10). 즐겨찾기 추가/제거/조회.

웹 최초 인증 필요 기능 — ``get_current_principal``(로그인만 요구·역할 무관)로 게이팅하고,
사용자×룸 1행(``uq_favorites_user_id_room_id``)을 토글 멱등성의 DB 근거로 둔다.
"""
