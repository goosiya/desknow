// 챗봇 응답 SSE 스트리밍 클라이언트 — 웹 streamMessage.ts RN 대체 (Story 9.3 — AC7·§범위 3).
//
// 웹은 레포 유일의 raw fetch+ReadableStream+`credentials:"include"`(쿠키)였다. RN(Hermes)은 스트리밍
// ReadableStream이 불안정하므로 **react-native-sse `EventSource`**(POST+body+Bearer 헤더 지원)로
// 대체한다. `EventSource`는 별도 import라 eslint 직접-fetch 가드에 안 걸린다(allowlist 불요·내부 XHR).
//
// 인증=쿠키→**Bearer**(`getAccessToken` 헤더)·`credentials:"include"` 절대 금지(RN 무존재). 401은
// SDK 인터셉터가 SSE 경로를 안 타므로 **수동 재시도**: 9.1 `refreshSession()`(단일-flight) 1회 →
// 새 토큰으로 재연결(무한루프 가드). `StreamEvent` 타입·done/error/delta 의미부여는 웹 verbatim(파서는
// react-native-sse가 프레임을 분해해 주므로 data JSON 파싱만 한다).
import EventSource from "react-native-sse";

import { refreshSession } from "@/lib/api-client";
import { clearTokens, getAccessToken } from "@/lib/session-store";

/** 스트림 소비자에게 전달되는 이벤트(델타 누적·종료·강등) — 웹과 동일. */
export type StreamEvent =
  | { type: "delta"; text: string }
  | { type: "done" }
  | { type: "error"; code: string; message: string };

/** 스트림 시작 전/중 실패(401·네트워크 등) 강등 이벤트 — 웹과 동일. */
const STREAM_FAILED: StreamEvent = {
  type: "error",
  code: "STREAM_FAILED",
  message: "스트림을 시작할 수 없습니다.",
};

// 무활동(델타/이벤트 없음) 워치독 임계. 서버가 `event: done`/`error` 없이 연결을 깨끗이 끊으면(주로
// 배포 환경 프록시 버퍼링/컷오프) react-native-sse는 종료 이벤트를 디스패치하지 않아(`close`는 명시
// close() 시에만) 스트림이 영구 행(입력 영구 잠금)에 빠진다 — 웹 fetch+ReadableStream은 reader 종료로
// 자연 감지하나 RN 라이브러리는 못 한다. 이 시간만큼 무활동이면 graceful 강등해 동작 패리티를 복원한다.
// 값은 느린 RAG/툴콜 초기 지연(첫 토큰까지 10~30s 가능)을 충분히 넘겨 정상 스트림 오절단을 막는다.
const IDLE_TIMEOUT_MS = 60_000;

// baseUrl = 백엔드 origin만(api-client.ts와 동일 출처·드리프트 방지). SSE는 SDK가 소비 못 하므로
// EventSource로 직접 URL을 짠다(경로 /api/v1/...는 여기서만 명시).
const API_BASE = process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** message 프레임(`data:{"delta":"..."}`)을 delta 이벤트로 — 웹 parseFrame의 message 분기. */
function parseDeltaFrame(data: string | null): StreamEvent | null {
  if (!data) return null;
  try {
    const parsed = JSON.parse(data) as { delta?: string };
    return { type: "delta", text: parsed.delta ?? "" };
  } catch {
    return null; // 깨진 델타 프레임은 조용히 건너뛴다(스트림 계속) — 웹 동형
  }
}

/** 인밴드 `event: error` 프레임(`data:{"code","message"}`)을 error 이벤트로 — 웹 parseFrame의 error 분기. */
function parseErrorFrame(data: string | null): StreamEvent {
  try {
    const parsed = JSON.parse(data ?? "") as { code?: string; message?: string };
    return { type: "error", code: parsed.code ?? "UNKNOWN", message: parsed.message ?? "" };
  } catch {
    return { type: "error", code: "PARSE_ERROR", message: "" };
  }
}

/**
 * `POST /api/v1/chatbot/stream`에 메시지를 보내고 SSE 토큰 스트림을 이벤트로 yield한다(웹과 동일
 * AsyncIterable 인터페이스 — useChatbot의 `for await` 루프 그대로 재사용).
 *
 * react-native-sse(XHR 기반·web에선 XHR 폴백으로 동작)로 연결한다. **`pollingInterval: 0`**으로
 * 종료 후 자동 재연결(중복 POST)을 막는다(라이브러리 기본 5초 재연결 함정). 401 전송 오류 시
 * `refreshSession()` 후 **1회만** 재연결한다(무한루프 가드). 인밴드 `event: error`(LLM 실패)는
 * `.data`로, 전송 오류는 `.xhrStatus`로 구분한다.
 */
export async function* streamMessage({
  message,
  deviceId,
  coords,
  signal,
}: {
  message: string;
  deviceId: string;
  /** 위치 권한 허용 시 현재 좌표 — 챗봇 "내 주변" 반경 검색에 동봉(없으면 미전송 → 서버가 위치 안내). */
  coords?: { lat: number; lng: number };
  /** 진행 중 스트림 취소(언마운트/로그아웃 — 소비처가 AbortController로 주입). */
  signal?: AbortSignal;
}): AsyncIterable<StreamEvent> {
  // 이벤트 → 비동기 이터러블 브릿지(큐 + 단일 대기 resolver).
  const queue: StreamEvent[] = [];
  let resolveNext: (() => void) | null = null;
  let finished = false;
  let source: EventSource<"done"> | null = null;
  let retriedAuth = false;
  // 무활동 idle 워치독 핸들 — 활동(push)마다 리셋, 종료(finish)·재연결·정리 시 해제.
  let watchdog: ReturnType<typeof setTimeout> | null = null;

  const clearWatchdog = () => {
    if (watchdog !== null) {
      clearTimeout(watchdog);
      watchdog = null;
    }
  };
  // 무활동 임계 초과 = 종료 신호 없는 멈춤으로 간주 → 연결 정리 + STREAM_FAILED 강등(소비처가 에러 처리).
  const armWatchdog = () => {
    clearWatchdog();
    watchdog = setTimeout(() => {
      source?.close();
      push(STREAM_FAILED);
      finish();
    }, IDLE_TIMEOUT_MS);
  };

  const push = (ev: StreamEvent) => {
    queue.push(ev);
    resolveNext?.();
    resolveNext = null;
    armWatchdog(); // 활동 있음 → idle 타이머 리셋
  };
  const finish = () => {
    finished = true;
    resolveNext?.();
    resolveNext = null;
    clearWatchdog(); // 종료(done/error/abort) → idle 타이머 해제
  };

  const connect = (token: string | null): EventSource<"done"> => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    const es = new EventSource<"done">(`${API_BASE}/api/v1/chatbot/stream`, {
      method: "POST",
      headers,
      // 좌표가 있으면 동봉(둘 다) — 백엔드가 챗봇 "내 주변" 반경 검색 시 사용(LLM 비노출·config 주입).
      body: JSON.stringify(
        coords
          ? { message, device_id: deviceId, lat: coords.lat, lng: coords.lng }
          : { message, device_id: deviceId },
      ),
      // ⚠️ 단발 스트림 — 종료 후 자동 재연결(중복 POST)을 끈다(기본 5000ms 함정).
      pollingInterval: 0,
    });

    // 기본 message 이벤트 = 토큰 델타.
    es.addEventListener("message", (e) => {
      const ev = parseDeltaFrame(e.data);
      if (ev) push(ev);
    });

    // 명시 종료(event: done) — addEventListener 등록 시에만 디스패치된다(라이브러리 동작).
    es.addEventListener("done", () => {
      push({ type: "done" });
      finish();
      es.close();
    });

    // 'error' 리스너는 두 종류를 받는다: ① 인밴드 SSE error(`.data` 보유=LLM 실패) ② 전송 오류
    // (`.xhrStatus` 보유=401/네트워크/타임아웃). data 유무로 구분한다.
    es.addEventListener("error", (e) => {
      const ev = e as { type: string; data?: string | null; xhrStatus?: number };
      if (typeof ev.data === "string" && ev.data.length > 0) {
        // 인밴드 LLM 실패 → graceful error로 전달(막다른 화면 금지).
        push(parseErrorFrame(ev.data));
        finish();
        es.close();
        return;
      }
      // 전송 오류. 401이면 refresh 회전 후 1회만 재연결(무한루프 가드).
      if (ev.xhrStatus === 401 && !retriedAuth) {
        retriedAuth = true;
        clearWatchdog(); // 재연결(refresh await) 동안 idle 워치독 일시 정지 — connect()가 재가동
        es.close();
        void (async () => {
          const ok = await refreshSession();
          // refresh await 도중 소비처가 abort(언마운트/로그아웃)했으면 새 연결을 만들지 않는다.
          // (안 그러면 onAbort가 닫은 옛 ES 뒤로 새 EventSource가 살아남아 중복 POST·연결 누수.)
          if (signal?.aborted) {
            finish();
            return;
          }
          if (ok) {
            const newToken = await getAccessToken();
            if (signal?.aborted) {
              finish();
              return;
            }
            source = connect(newToken); // 새 토큰으로 1회 재연결
          } else {
            // refresh까지 실패(만료/회전/로그아웃) → 토큰 정리(다음 authMe가 401→세션 null 전이).
            await clearTokens();
            push(STREAM_FAILED);
            finish();
          }
        })();
        return;
      }
      push(STREAM_FAILED); // 시작 불가/네트워크 단절/타임아웃 — 강등
      finish();
      es.close();
    });

    // 연결 직후 idle 워치독 가동(초기·재연결 공통) — 첫 델타까지 무활동도 임계로 본다.
    armWatchdog();
    return es;
  };

  // 시작 시 이미 abort면 즉시 종료(빈 스트림).
  if (signal?.aborted) return;
  const onAbort = () => {
    source?.close();
    finish();
  };
  signal?.addEventListener("abort", onAbort);

  try {
    const token = await getAccessToken();
    source = connect(token);
    while (true) {
      if (queue.length > 0) {
        yield queue.shift()!;
        continue;
      }
      if (finished) break;
      await new Promise<void>((resolve) => {
        resolveNext = resolve;
      });
    }
  } finally {
    // 조기 종료(소비처 break)·abort·정상 종료 모두 연결·타이머 정리(reader/연결 누수 방지 — 웹 reader.cancel 등가).
    clearWatchdog();
    signal?.removeEventListener("abort", onAbort);
    source?.close();
  }
}
