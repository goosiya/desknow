// 챗봇 응답 SSE fetch-stream 클라이언트 (Story 7.4 — AC3·AC4).
//
// ⚠️ 이 파일은 **유일하게 raw fetch가 허용된 모듈**이다(eslint.config.mjs allowlist — preset NOTE가
// 예고한 "E7 챗봇 SSE만 해당 모듈 allowlist", architecture L290 예외). SSE 스트리밍은 생성 SDK
// (@hey-api)로 소비 불가하므로(SDK는 JSON 응답 가정) raw fetch + ReadableStream reader로 직접
// SSE 프레임을 파싱한다. 그 외 백엔드 호출은 전부 SDK 경유(가드 유지).
//
// 인증=기존 httpOnly 쿠키(`credentials:"include"` — api-client.ts와 동일). baseUrl은 `getApiBaseUrl()`
// 단일 출처(드리프트 방지). 프레이밍은 BE가 sse-starlette + JSON 인코딩(`data: {"delta":...}`)으로
// 견고화(deferred L129 회수)했으므로, 토큰에 `\n`·공백·`[DONE]`이 섞여도 와이어 `data:`는 단일
// 라인이라 프레임이 깨지지 않는다 — 파서는 JSON 디코드만 하면 된다.
import { authRefresh, getApiBaseUrl } from "@/lib/api-client";

/** 스트림 소비자에게 전달되는 이벤트(델타 누적·종료·강등). */
export type StreamEvent =
  | { type: "delta"; text: string }
  | { type: "done" }
  | { type: "error"; code: string; message: string };

/** 스트림 시작 전 실패(401·네트워크 등) 시 쓰는 강등 이벤트(인밴드 error와 동일 형태). */
const STREAM_FAILED: StreamEvent = {
  type: "error",
  code: "STREAM_FAILED",
  message: "스트림을 시작할 수 없습니다.",
};

/** SSE 프레임 1개(`\n\n` 경계 사이 텍스트)를 StreamEvent로 파싱한다. 빈/주석 프레임은 null. */
function parseFrame(rawFrame: string): StreamEvent | null {
  const frame = rawFrame.replace(/\r\n/g, "\n").trim();
  if (frame === "") return null;

  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith(":")) continue; // 주석(keep-alive ping) — 무시
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      // SSE 규약: data: 뒤 선행 공백 1개만 제거(이후 공백은 페이로드).
      dataLines.push(line.slice("data:".length).replace(/^ /, ""));
    }
  }
  const data = dataLines.join("\n");

  if (event === "done") return { type: "done" };
  if (event === "error") {
    try {
      const parsed = JSON.parse(data) as { code?: string; message?: string };
      return {
        type: "error",
        code: parsed.code ?? "UNKNOWN",
        message: parsed.message ?? "",
      };
    } catch {
      return { type: "error", code: "PARSE_ERROR", message: "" };
    }
  }
  // 기본 message 이벤트 = 토큰 델타.
  if (data === "") return null;
  try {
    const parsed = JSON.parse(data) as { delta?: string };
    return { type: "delta", text: parsed.delta ?? "" };
  } catch {
    return null; // 깨진 델타 프레임은 조용히 건너뛴다(전체 스트림은 계속)
  }
}

/**
 * `POST /api/v1/chatbot/stream`에 메시지를 보내고 SSE 토큰 스트림을 이벤트로 yield한다.
 *
 * - 스트림 시작 전 실패(non-OK 응답·body 없음)는 `error` 이벤트로 강등(막다른 화면 금지, AC4).
 * - 시작 후 BE는 LLM 실패를 인밴드 `event: error`로 보내므로(HTTP 상태 불가) 동일 `error`로 전달.
 * - `\n\n` 경계로 프레임을 분리하고 청크 경계에 걸친 프레임은 버퍼링한다(분할 프레임 안전).
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
  /** 진행 중 스트림 취소용(언마운트/로그아웃 — 소비처가 AbortController로 주입). */
  signal?: AbortSignal;
}): AsyncIterable<StreamEvent> {
  // 스트림 POST 1회 시도(refresh 재시도에서 재사용 — body/헤더/쿠키/signal 동일). 좌표가 있으면 동봉
  // (둘 다) — 백엔드가 "내 주변" 반경 검색 시 사용(LLM 비노출·graph config 주입).
  const postStream = (): Promise<Response> =>
    fetch(`${getApiBaseUrl()}/api/v1/chatbot/stream`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        coords
          ? { message, device_id: deviceId, lat: coords.lat, lng: coords.lng }
          : { message, device_id: deviceId },
      ),
      signal,
    });

  let response: Response;
  try {
    response = await postStream();
    // mid-session 토큰 만료 회복(C②): 로그인 상태에서 access 토큰(15분)이 만료되면 stream이
    // 401로 떨어진다. authRefresh(httpOnly refresh 쿠키, path=/api/v1/auth)로 토큰 쌍을 1회
    // 회전 발급해 access 쿠키를 갱신한 뒤 stream을 **1회만** 재시도한다(무한 루프 방지). refresh
    // 까지 401(refresh 토큰 만료/회전·로그아웃)이면 갱신을 건너뛰어 아래 비-OK 분기로 강등된다 —
    // 그때 useSession authMe도 401→session=null로 전이해 로그아웃 처리가 이어진다(이중 보정 아님).
    if (response.status === 401) {
      const { response: refreshed } = await authRefresh({
        body: {},
        throwOnError: false,
      });
      if (refreshed?.ok) {
        response = await postStream();
      }
    }
  } catch {
    yield STREAM_FAILED; // 네트워크 단절·abort 등 — 시작 전 실패
    return;
  }

  if (!response.ok || response.body === null) {
    yield STREAM_FAILED; // 갱신 후에도 401·5xx 등 시작 전 실패(스트림 헤더 전)
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      // sse-starlette는 `\r\n` 줄바꿈 + `\r\n\r\n` 프레임 구분자를 쓴다. 버퍼를 `\n`으로 정규화해
      // `\n\n` 단일 경계로 분리한다(data는 JSON이라 실제 \r·\n이 없어 무손실 — 청크 경계에 걸친
      // `\r`+`\n`도 다음 read에서 합쳐져 정규화된다).
      buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, "\n");
      let sepIndex = buffer.indexOf("\n\n");
      while (sepIndex !== -1) {
        const rawFrame = buffer.slice(0, sepIndex);
        buffer = buffer.slice(sepIndex + 2);
        const ev = parseFrame(rawFrame);
        if (ev) yield ev;
        sepIndex = buffer.indexOf("\n\n");
      }
    }
    // 종료 직전 `\n\n` 없이 끝난 잔여 프레임 처리(견고성).
    const tail = parseFrame(buffer);
    if (tail) yield tail;
  } finally {
    // 조기 종료(error break)·abort(언마운트/로그아웃)·소비처 return 시 응답 본문 스트림을
    // 정리한다(reader/연결 누수 방지). for-await 조기 break는 제너레이터 return()을 호출 → finally.
    try {
      await reader.cancel();
    } catch {
      // 이미 종료/취소된 reader 등의 정리 실패는 무시(스트림 결과에 영향 없음).
    }
  }
}
