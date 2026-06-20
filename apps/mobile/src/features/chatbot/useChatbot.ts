// 챗봇 대화 상태 훅 — 웹 useChatbot.ts RN 포팅 (Story 9.3 — AC6·AC7).
//
// - transcript 쿼리(`["chatbot","messages",deviceId]`): QueryClient(_layout 레벨)가 탭 네비게이션을
//   가로질러 캐시를 보존(AC6)하고, 패널 오픈/마운트 시 `GET /chatbot/messages`로 서버 checkpointer
//   상태를 재수화한다(GET/DELETE는 SDK 경유·Bearer는 인터셉터). `refetchOnMount:false`로 스트리밍
//   옵티미스틱 캐시를 재수화가 덮지 않게 한다(전역 기본 refetchOnMount:'always'를 챗봇에선 끈다).
// - send(스트리밍): 사용자 메시지를 옵티미스틱 append 후 `streamMessage`(react-native-sse)로 토큰
//   소비. 첫 델타 전엔 타이핑 인디케이터(isSending), 정상 종료(done)면 최종화, 실패면 부분 어시스턴트
//   제거 + 사용자 버블 유지(재전송용) + isError. BE가 실패 turn 입력을 서버 thread에서 롤백하므로
//   ([[langgraph-failed-turn-input-rollback]]) 클라는 부분 어시스턴트만 정리한다.
// - 로그아웃/미인증 초기화(AC6): useSession data가 로그인→null 전이하면 transcript 캐시 제거 + 패널
//   닫기(onSessionEnd) + `DELETE /chatbot/session` best-effort. device_id는 유지(thread만 초기화).
import { useEffect, useRef, useState } from "react";
import * as Location from "expo-location";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  chatbotGetTranscript,
  chatbotResetSession,
  type ChatMessage,
} from "@/lib/api-client";
import { useSession } from "@/features/auth/useSession";

import { streamMessage } from "./streamMessage";

/** 챗봇 transcript 캐시 키 프리픽스(최상위 독립 — ["rooms"]/광역 무효화 금지). */
const CHATBOT_KEY = ["chatbot"] as const;

/** deviceId별 transcript 정확 키. */
function transcriptKey(deviceId: string) {
  return [...CHATBOT_KEY, "messages", deviceId] as const;
}

export type UseChatbotResult = {
  /** 표시 transcript(서버 재수화 + 옵티미스틱 + 스트리밍 누적). */
  messages: ChatMessage[];
  /** 새 메시지 전송(옵티미스틱 append → SSE 스트리밍 소비). deviceId 미준비 시 no-op. */
  send: (text: string) => void;
  /** 마지막 실패 메시지 재전송(사용자 버블 재append 없이 스트림만 재시도). */
  retry: () => void;
  /** 첫 델타 대기 중(타이핑 인디케이터 — 전송~첫 토큰 사이). */
  isSending: boolean;
  /** 스트림 진행 중(전송~종료/에러 전체 — 입력 비활성으로 동시 전송 차단). */
  isStreaming: boolean;
  /** 마지막 전송 실패(에러 카피 + 재전송 노출). */
  isError: boolean;
  /** device_id 준비 완료(빈 동안 입력 비활성). */
  isReady: boolean;
  /** 로그인 여부(미로그인이면 패널이 로그인 안내로 분기 — 백엔드 /chatbot/stream 인증 필수). */
  isAuthed: boolean;
};

export function useChatbot({
  deviceId,
  onSessionEnd,
}: {
  deviceId: string;
  onSessionEnd?: () => void;
}): UseChatbotResult {
  const queryClient = useQueryClient();
  const { data: user } = useSession();
  const key = transcriptKey(deviceId);
  const isReady = deviceId !== "";
  // 백엔드 /chatbot/stream은 인증 필수 — 미로그인 전송은 401로 떨어져 카피로 위장된다(원인 추적 불가).
  // 따라서 미로그인이면 패널이 입력 대신 로그인 안내로 분기한다.
  const isAuthed = user != null;
  // 마지막 "실패한" 전송 텍스트(인터리빙 안전 — A 실패→B 전송 시 retry가 A 대상).
  const lastFailedText = useRef<string | null>(null);
  // 진행 중 스트림 취소 핸들 — 언마운트/로그아웃 시 abort(reader·연결 정리·제거된 캐시 부활 방지).
  const abortRef = useRef<AbortController | null>(null);
  // 동기 재진입 가드 — setIsStreaming 반영 전 좁은 창의 동시 스트림을 ref로 차단.
  const streamingRef = useRef(false);

  // 서버 transcript 재수화(AC6). deviceId 준비 전엔 비활성. 미로그인이면 401 → 빈 대화 유지.
  const transcriptQuery = useQuery({
    queryKey: key,
    enabled: isReady && !!user,
    // 스트리밍 옵티미스틱 캐시를 재수화가 덮지 않게 한다(전역 refetchOnMount:'always'를 끈다).
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    queryFn: async (): Promise<ChatMessage[]> => {
      const { data } = await chatbotGetTranscript({
        query: { device_id: deviceId },
        throwOnError: true,
      });
      return data?.messages ?? [];
    },
  });

  // 스트리밍 상태(타이핑 인디케이터·입력 비활성·에러 카피). useMutation 대신 직접 관리(SSE는 단일 응답
  // 모델에 안 맞고 "첫 델타 전/스트림 전체" 두 시점이 필요).
  const [isSending, setIsSending] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isError, setIsError] = useState(false);

  /** 마지막 어시스턴트 버블 content에 델타를 누적한다(점진 렌더). 마지막이 assistant일 때만. */
  const appendDelta = (text: string) => {
    queryClient.setQueryData<ChatMessage[]>(key, (old) => {
      if (!old || old.length === 0) return old;
      const last = old[old.length - 1];
      if (last.role !== "assistant") return old;
      return [...old.slice(0, -1), { ...last, content: last.content + text }];
    });
  };

  /** 마지막 어시스턴트 버블(부분 수신)을 제거한다(에러 강등 시 — 사용자 버블은 유지). */
  const dropPartialAssistant = () => {
    queryClient.setQueryData<ChatMessage[]>(key, (old) => {
      if (!old || old.length === 0) return old;
      const last = old[old.length - 1];
      if (last.role !== "assistant") return old;
      return old.slice(0, -1);
    });
  };

  /** 전송/재전송 공통 스트리밍 루프. 옵티미스틱 사용자 버블 → SSE 델타 누적 → 종료/에러 처리. */
  const runStream = async (text: string, isRetry: boolean) => {
    // 동기 재진입 가드 — setIsStreaming 반영 전 좁은 창의 동시 스트림을 ref로 차단.
    if (streamingRef.current) return;
    streamingRef.current = true;
    const controller = new AbortController();
    abortRef.current = controller;

    if (!isRetry) {
      // 정확 키만 — cancel 후 즉시 사용자 버블 append(≤100ms 반영). 광역 무효화 금지.
      await queryClient.cancelQueries({ queryKey: key });
      queryClient.setQueryData<ChatMessage[]>(key, (old) => [
        ...(old ?? []),
        { role: "user", content: text },
      ]);
    }
    setIsError(false);
    setIsSending(true); // 첫 델타 전 — 타이핑 인디케이터
    setIsStreaming(true);

    // 위치 권한 허용 시 마지막 좌표를 동봉한다(챗봇 "내 주변" 반경 검색). getLastKnownPositionAsync는
    // 빠르고(캐시) 권한 없음/미측정이면 null·throw → 좌표 없이 전송(서버가 "위치 정보를 받지 못했어요"로
    // graceful 안내). getCurrentPositionAsync는 새 fix를 기다리며 멈출 수 있어 쓰지 않는다.
    let coords: { lat: number; lng: number } | undefined;
    try {
      const last = await Location.getLastKnownPositionAsync();
      if (last) coords = { lat: last.coords.latitude, lng: last.coords.longitude };
    } catch {
      // 위치 미허용/미측정 — 좌표 없이 전송.
    }

    let assistantStarted = false;
    let errored = false;
    let receivedDone = false; // 명시 종료(event: done) 수신 여부 — 없이 끝나면 절단으로 간주.
    try {
      for await (const ev of streamMessage({
        message: text,
        deviceId,
        coords,
        signal: controller.signal,
      })) {
        if (ev.type === "delta") {
          if (!assistantStarted) {
            assistantStarted = true;
            setIsSending(false); // 첫 델타 도착 → 인디케이터 해제(스트리밍 텍스트로 전환)
            queryClient.setQueryData<ChatMessage[]>(key, (old) => [
              ...(old ?? []),
              { role: "assistant", content: ev.text },
            ]);
          } else {
            appendDelta(ev.text);
          }
        } else if (ev.type === "done") {
          receivedDone = true; // 정상 종료 신호(절단/무응답 구분용)
        } else if (ev.type === "error") {
          errored = true; // 인밴드 LLM 실패 — 강등 처리(아래)
          break;
        }
      }
    } catch {
      errored = true; // 네트워크 단절 등 예기치 못한 실패
    }

    // abort(언마운트/로그아웃): 캐시·에러 상태는 건드리지 않고 진행 플래그만 해제한다.
    if (controller.signal.aborted) {
      setIsSending(false);
      setIsStreaming(false);
      streamingRef.current = false;
      abortRef.current = null;
      return;
    }

    // 명시 done 없이 종료(절단)했거나 봇 출력 0개(빈 응답)면 graceful error로 강등한다(절단을 완성본으로
    // 오인하거나 무응답 막다른 화면이 남는 것을 막는다 — AC7).
    if (!errored && (!receivedDone || !assistantStarted)) {
      errored = true;
    }

    if (errored) {
      if (assistantStarted) dropPartialAssistant(); // 부분 어시스턴트 정리(사용자 버블 유지)
      lastFailedText.current = text; // 현재 에러 UI와 일치하는 실패 텍스트(retry 대상)
      setIsError(true);
    } else {
      lastFailedText.current = null; // 성공 → 보류 중 실패 텍스트 클리어
    }
    setIsSending(false);
    setIsStreaming(false);
    streamingRef.current = false;
    abortRef.current = null;
  };

  /** 새 메시지 전송. deviceId 미준비/미인증/스트림 진행 중이면 무시. */
  const send = (text: string) => {
    const trimmed = text.trim();
    if (!isReady || !isAuthed || streamingRef.current || trimmed === "") return;
    void runStream(trimmed, false);
  };

  /** 마지막 실패 메시지 재전송(실패 텍스트 ref 재사용 — 인터리빙 안전). */
  const retry = () => {
    const text = lastFailedText.current;
    if (!isReady || streamingRef.current || !text) return;
    void runStream(text, true);
  };

  // 언마운트 시 진행 중 스트림 취소(reader·연결 정리, 닫힌 패널에 대한 유령 setState 방지).
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  // ── 로그아웃/미인증 초기화(AC6) — 로그인→null 전이에서만 발화 ──
  const wasAuthenticated = useRef(false);
  useEffect(() => {
    if (user) {
      wasAuthenticated.current = true;
      return;
    }
    if (user === null && wasAuthenticated.current) {
      wasAuthenticated.current = false;
      abortRef.current?.abort(); // 진행 중 스트림 취소 — 뒤늦은 델타가 제거할 캐시를 부활시키지 못하게
      queryClient.removeQueries({ queryKey: CHATBOT_KEY }); // transcript 캐시 제거
      onSessionEnd?.(); // 패널 닫기
      if (deviceId !== "") {
        // 서버 thread 폐기(best-effort — 401/네트워크 실패 무시). device_id는 유지.
        chatbotResetSession({
          query: { device_id: deviceId },
          throwOnError: false,
        }).catch(() => {});
      }
    }
  }, [user, deviceId, queryClient, onSessionEnd]);

  return {
    messages: transcriptQuery.data ?? [],
    send,
    retry,
    isSending,
    isStreaming,
    isError,
    isReady,
    isAuthed,
  };
}
