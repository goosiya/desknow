"use client";

// 카카오톡 공유 버튼 (Story 5.4 — AC1·AC3·AC4). 확정 예약을 한 번의 클릭으로 카카오톡에 공유한다.
// 예약현황 확정 행 + 즉시예약 성공 배너(climax) 두 진입점이 같은 컴포넌트를 쓴다(추가 API 조회 0 —
// 공유 데이터는 호출처가 이미 보유한 필드에서 합성).
//
// ⚠️ graceful degrade(AC4): SDK 로드/초기화/공유 실패는 친근한 안내(role="status") + 재시도로
//    처리하고 throw 를 전파하지 않는다(예약 행/화면 크래시 금지 — maps 로더 reject 패턴 동형).
// ⚠️ set-state-in-effect 금지: 공유는 **클릭 이벤트**에서 lazy 로드(effect 아님)·실패 state 도
//    이벤트 핸들러에서만 갱신한다.
// ⚠️ 색 단독 금지: 버튼 = 아이콘(Share2) + 가시 텍스트("공유") + aria-label. tap-target(≥44px).
//    카톡 외 SNS 진입점 없음(단일 버튼 — epics L958).
import { useState } from "react";
import { Share2 } from "lucide-react";

import { shareReservation } from "@/lib/kakao-share";

type KakaoShareButtonProps = {
  roomName: string;
  slotStarts: string[];
  roomId: string;
};

export function KakaoShareButton({ roomName, slotStarts, roomId }: KakaoShareButtonProps) {
  // 공유 실패 안내 표시 여부(로컬 — 클릭 핸들러에서만 갱신). 진행 중 이중 클릭은 isSharing 가드.
  const [failed, setFailed] = useState(false);
  const [isSharing, setIsSharing] = useState(false);

  async function handleShare() {
    if (isSharing) return;
    setIsSharing(true);
    setFailed(false);
    try {
      await shareReservation({ roomName, slotStarts, roomId });
    } catch {
      // AC4 — 조용한 실패 금지: 친근한 안내 + 재시도(에러 throw 전파 금지·예약 행 크래시 금지).
      setFailed(true);
    } finally {
      setIsSharing(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-1">
      <button
        type="button"
        onClick={handleShare}
        disabled={isSharing}
        aria-label="카카오톡으로 공유"
        className="tap-target inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md border border-border px-3 text-sm font-medium text-card-foreground disabled:opacity-50"
      >
        <Share2 aria-hidden="true" className="size-4" />
        공유
      </button>
      {failed ? (
        <p role="status" className="text-xs leading-[1.6] text-muted-foreground">
          지금은 공유를 할 수 없어요. 잠시 후 다시 해주세요.
        </p>
      ) : null}
    </div>
  );
}
