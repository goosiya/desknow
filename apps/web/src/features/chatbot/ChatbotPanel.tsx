"use client";

// 챗봇 "룸메이트" 대화 패널 (Story 7.3 → 7.4 스트리밍). vaul 드로어(RoomSheet 선례) = Radix Dialog
// 기반이라 포커스 트랩·Esc 닫기·포커스 복귀(FAB)·스크롤 잠금·reduced-motion 을 **상속**한다.
//
// 메시지 리스트(user/assistant 버블) + 입력 + 전송. 첫 진입(빈 대화) 시 제안 칩 2종이 보이고
// 탭하면 그 텍스트가 전송된다. 7.4 스트리밍: 첫 토큰 전엔 타이핑 인디케이터(`isSending`), 첫 토큰
// 도착 시 어시스턴트 버블이 토큰 누적으로 점진 렌더된다(인디케이터→텍스트 자연 전환). 스트림 진행
// 중(`isStreaming`)엔 입력·전송·제안 칩을 비활성화해 동시 전송을 막는다. 새 토큰은 aria-live=
// "polite" 영역으로 안내된다(스크린리더). 메시지 추가·스트리밍 토큰 누적 시 대화 영역을 항상
// 하단(최신)으로 자동 스크롤한다(아래 scrollRef 효과).
import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { Drawer } from "vaul";

import type { UseChatbotResult } from "./useChatbot";

// 모바일 소프트 키패드 대응 — 키패드가 화면 하단을 가린 높이(px)를 visualViewport 로 구한다.
// vh/dvh 는 키패드가 떠도 줄지 않으므로, bottom-0 고정 드로어의 입력창이 키패드 뒤로 숨는다
// (iOS·Android 공통). 이 값으로 Drawer.Content 의 bottom/maxHeight 를 보정해 입력창을 키패드
// 바로 위로 올린다. 드로어가 닫혀 있거나(visualViewport 미지원) 키패드가 없으면 0(보정 없음).
function useKeyboardInset(active: boolean): number {
  const [inset, setInset] = useState(0);
  useEffect(() => {
    const vv = typeof window !== "undefined" ? window.visualViewport : null;
    if (!active || !vv) {
      setInset(0);
      return;
    }
    const update = () => {
      // 레이아웃 높이 - (보이는 높이 + 보이는 영역 상단 오프셋) = 키패드가 하단을 가린 높이.
      const covered = window.innerHeight - vv.height - vv.offsetTop;
      // 주소창 변동 등 작은 차이는 키패드로 보지 않는다(60px 임계 — 떨림 방지).
      setInset(covered > 60 ? Math.round(covered) : 0);
    };
    update();
    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    return () => {
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
    };
  }, [active]);
  return inset;
}

// 첫 진입 제안 칩(EXPERIENCE.md) — 탭=전송. 답변 정확도/환각은 7.3 결함 아님(툴·근거=7.5/7.6).
const SUGGESTION_CHIPS = ["환불 규정?", "강남 오후 3시 빈 방"] as const;

// 모델 실패 카피(고정). ⚠️ 네트워크 단절 카피는 별도 표준("네트워크 연결이 끊겼어요")이나, 본
// 패널의 일반 전송 실패는 업스트림(LLM) 막힘이 주 경로라 아래 카피를 쓴다([[terminology-network-disconnect-not-offline]]).
const ERROR_COPY = "잠깐 답이 막혔어요. 다시 물어봐 주실래요?";

export function ChatbotPanel({
  chatbot,
  open,
}: {
  chatbot: UseChatbotResult;
  /** 드로어 오픈 여부 — 오픈 직후 대화 영역을 최신(하단)으로 맞추기 위한 트리거. */
  open?: boolean;
}) {
  const { messages, send, retry, isSending, isStreaming, isError, isReady, isAuthed } =
    chatbot;
  const isEmpty = messages.length === 0;

  // 모바일 키패드가 가린 높이 — 드로어를 그만큼 들어올려 입력창이 키패드 뒤로 숨지 않게 한다.
  const keyboardInset = useKeyboardInset(Boolean(open));

  // 대화 영역 스크롤 컨테이너 — 새 메시지/스트리밍 토큰·오픈 시마다 최신(하단)으로 이동시킨다.
  const scrollRef = useRef<HTMLDivElement>(null);
  // messages 는 델타마다 새 배열(setQueryData)이고, isSending 전환(타이핑 인디케이터)·open 도 높이/
  // 가시성을 바꾸므로 의존성에 둔다. scrollTop 설정은 DOM 부작용이라 setState-in-effect 함정과 무관.
  // ⚠️ 오픈 시 vaul 이 포커스를 상단(닫기 버튼)으로 옮기며 컨테이너를 위로 스크롤시키므로, rAF(즉시
  //    스트리밍 반응)와 짧은 setTimeout(그 포커스 스크롤 **이후** 보정)으로 이중 고정한다.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !open) return;
    const toBottom = () => {
      el.scrollTop = el.scrollHeight;
    };
    const raf = requestAnimationFrame(toBottom);
    const timer = setTimeout(toBottom, 100);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(timer);
    };
    // keyboardInset: 키패드가 뜨고 maxHeight 가 줄면 대화 영역을 다시 하단(최신·입력 직전)으로 고정.
  }, [open, messages, isSending, isError, keyboardInset]);

  // 메시지 입력 ref — 오픈 시 포커스 대상(vaul 기본 상단 포커스 대체).
  const inputRef = useRef<HTMLInputElement>(null);
  // vaul/Radix 는 오픈 시 첫 포커스 가능 요소(상단 닫기 버튼)로 포커스를 옮기며 대화 영역을 위로
  // 스크롤시킨다(긴 대화가 최상단에서 열림). 그 기본 동작을 막고, 대신 **입력창에 포커스 + 대화
  // 영역을 하단 고정**한다(KTH 2026-06-18 — 챗봇은 최신 메시지부터 보이고 바로 입력 가능해야).
  const handleOpenAutoFocus = (event: Event) => {
    event.preventDefault();
    requestAnimationFrame(() => {
      const el = scrollRef.current;
      if (el) el.scrollTop = el.scrollHeight;
      inputRef.current?.focus(); // 미인증 시 input disabled → no-op(대화 없음)
    });
  };

  return (
    <Drawer.Portal>
      {/* 오버레이 — 클릭 시 닫힘(vaul). */}
      <Drawer.Overlay className="fixed inset-0 z-30 bg-foreground/20" />
      <Drawer.Content
        onOpenAutoFocus={handleOpenAutoFocus}
        // 키패드가 뜨면 그 높이만큼 드로어를 올리고(bottom) 보이는 영역에 맞춰 높이를 줄인다
        // (maxHeight). vaul 의 드래그/열기 애니메이션은 transform 기반이라 bottom/max-height
        // 전환과 충돌하지 않는다. dvh = 모바일 주소창까지 반영(vh 보다 정확).
        style={
          keyboardInset > 0
            ? { bottom: keyboardInset, maxHeight: `calc(100dvh - ${keyboardInset}px)` }
            : undefined
        }
        className="fixed inset-x-0 bottom-0 z-40 mx-auto flex h-[80dvh] max-h-[80dvh] w-full max-w-md flex-col rounded-t-xl border-t border-border bg-card shadow-sheet transition-[bottom,max-height] duration-200 ease-out focus:outline-none"
      >
        <Drawer.Handle className="mx-auto mt-3 h-1.5 w-12 shrink-0 rounded-full bg-border" />

        {/* 헤더 — 제목(Radix a11y 필수) + 닫기 */}
        <div className="flex items-center justify-between gap-2 px-5 pt-3">
          <Drawer.Title className="text-lg font-semibold text-card-foreground">
            룸메이트
          </Drawer.Title>
          <Drawer.Close
            aria-label="챗봇 닫기"
            className="tap-target inline-flex items-center justify-center rounded-md px-2 text-muted-foreground hover:bg-muted"
          >
            <span aria-hidden="true">✕</span>
          </Drawer.Close>
        </div>
        <Drawer.Description className="sr-only">
          스터디룸을 함께 찾아주는 룸메이트와 대화해요.
        </Drawer.Description>

        {/* 메시지 영역 — 새 응답을 aria-live polite 로 안내(접근성). */}
        <div
          ref={scrollRef}
          className="flex flex-1 flex-col gap-3 overflow-y-auto px-5 py-4"
          aria-live="polite"
        >
          {!isAuthed ? (
            // 미로그인: 입력 대신 로그인 안내(백엔드 /chatbot/stream 인증 필수 — 401 위장 차단).
            <div className="flex flex-col items-start gap-3">
              <p className="text-sm leading-[1.6] text-muted-foreground">
                로그인하면 룸메이트와 대화할 수 있어요.
              </p>
              <Drawer.Close asChild>
                <Link
                  href="/login?next=/"
                  className="tap-target inline-flex items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
                >
                  로그인하기
                </Link>
              </Drawer.Close>
            </div>
          ) : isEmpty ? (
            // 첫 진입: 인사 + 제안 칩(탭=전송).
            <div className="flex flex-col gap-3">
              <p className="text-sm leading-[1.6] text-muted-foreground">
                안녕하세요, 룸메이트예요. 무엇을 도와드릴까요?
              </p>
              <div className="flex flex-wrap gap-2">
                {SUGGESTION_CHIPS.map((chip) => (
                  <button
                    key={chip}
                    type="button"
                    onClick={() => send(chip)}
                    disabled={!isReady || isStreaming}
                    className="tap-target inline-flex items-center justify-center rounded-full border border-border bg-background px-3 text-sm font-medium text-foreground hover:bg-muted disabled:opacity-50"
                  >
                    {chip}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message, index) => (
              <ChatBubble key={index} role={message.role} content={message.content} />
            ))
          )}

          {/* 타이핑 인디케이터 — 전송~첫 토큰 사이만(스트리밍 시작 후 텍스트 버블로 전환). */}
          {isSending ? (
            <div
              className="self-start rounded-2xl bg-muted px-3 py-2 text-sm text-muted-foreground"
              data-testid="chatbot-typing"
            >
              <span className="sr-only">답변을 준비하고 있어요</span>
              <span aria-hidden="true">···</span>
            </div>
          ) : null}

          {/* 전송 실패 — 에러 카피 + 재전송(막다른 화면 금지). 스트림 종료 후에만 표시. */}
          {isError && !isStreaming ? (
            <div className="flex flex-col items-start gap-2" role="alert">
              <p className="text-sm leading-[1.6] text-muted-foreground">
                {ERROR_COPY}
              </p>
              <button
                type="button"
                onClick={retry}
                className="tap-target inline-flex items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
              >
                다시 보내기
              </button>
            </div>
          ) : null}
        </div>

        {/* 입력 + 전송 */}
        <form
          className="flex items-end gap-2 border-t border-border px-5 py-3"
          onSubmit={(event) => {
            event.preventDefault();
            const form = event.currentTarget;
            const input = form.elements.namedItem("message") as HTMLInputElement;
            send(input.value);
            input.value = "";
          }}
        >
          <input
            ref={inputRef}
            name="message"
            type="text"
            autoComplete="off"
            aria-label="메시지 입력"
            placeholder={isAuthed ? "메시지를 입력하세요" : "로그인 후 이용할 수 있어요"}
            disabled={!isReady || isStreaming || !isAuthed}
            className="min-h-11 flex-1 rounded-md border border-border bg-background px-3 text-sm text-foreground disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!isReady || isStreaming || !isAuthed}
            className="tap-target inline-flex items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            전송
          </button>
        </form>
      </Drawer.Content>
    </Drawer.Portal>
  );
}

// 어시스턴트 답변에서 **내부 경로만** 클릭 가능하게 만드는 화이트리스트(Story 7.6 — AC6).
// 룸 상세 `/rooms/{uuid}`와 탐색 홈의 단독 `/`만 허용한다. LLM이 생성한 임의 외부 URL/스킴은
// 절대 링크화하지 않는다(오픈리다이렉트·피싱·XSS 방지 — dangerouslySetInnerHTML 미사용).

/** href 화이트리스트(완전 일치) — 룸 상세 `/rooms/{uuid}` · 홈 `/` · 탐색 딥링크
 *  `/?view=list&sigungu=&dong=`(더보기 — 지역 필터된 목록)만 링크 허용. 모두 same-origin 상대경로라
 *  오픈리다이렉트 위험 없음(스킴·`//` 불허). 그 밖 임의 URL/쿼리는 링크화하지 않는다. */
const INTERNAL_HREF_RE =
  /^(?:\/rooms\/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|\/(?:\?view=list(?:&(?:sigungu|dong)=\d{1,10})*)?)$/;

// LLM이 룸 안내에 쓰는 마크다운 링크 `[라벨](href)`. href는 상대경로(`/rooms/{uuid}`·`/`)일 수도, LLM이
// 도메인을 붙인 절대 URL(`https://.../rooms/...`)일 수도 있다(2026-06-20 관측). 둘 다 매칭하고 아래
// toInternalPath로 경로만 뽑아, 내부 경로면 라벨만 링크화·아니면 라벨만 평문 — **어느 경우든 URL은
// 화면에 노출하지 않는다**(KTH 2026-06-18·#7). 라벨만 보이고 URL/슬래시는 항상 숨긴다.
const MD_LINK_RE = /\[([^\]\n]+)\]\(([^)\s]+)\)/g;

/** 마크다운 링크 href → 내부 경로(경로+쿼리)만 추출. 절대 URL(LLM 도메인 환각 포함)이면 도메인을 버리고
 *  pathname+search 만, 상대경로면 그대로. 그 외는 null. 도메인을 신뢰하지 않아(오픈리다이렉트 안전)
 *  최종 라우팅은 INTERNAL_HREF_RE로 한 번 더 검증한다. */
function toInternalPath(href: string): string | null {
  if (/^https?:\/\//i.test(href)) {
    try {
      const u = new URL(href);
      return `${u.pathname}${u.search}`;
    } catch {
      return null;
    }
  }
  return href.startsWith("/") ? href : null;
}

// 마크다운 링크 밖 평문에 떠도는 bare 내부 경로(안전망). 경계는 `\p{L}\p{N}`(유니코드 letter/number)
// + `/`로 잡는다(`u` 플래그) — 한글("예약/취소")·외부 URL 박힘(`https://evil/rooms/…`)·날짜(2026/06)를
// 오탐 없이 제외한다. 라벨 없이 떠도는 경로라 라벨=경로로 링크한다(마크다운 링크가 우선이라 드묾).
const BARE_PATH_RE =
  "(?<![\\p{L}\\p{N}/])(?:\\/rooms\\/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|\\/(?![\\p{L}\\p{N}/]))";

/** 내부 경로 링크 1개 — 라벨 텍스트로 표시. 탭 시 라우팅 + 드로어 닫기(Drawer.Close asChild 상속). */
function internalLink(href: string, label: string, key: string): ReactNode {
  return (
    <Drawer.Close asChild key={key}>
      <Link
        href={href}
        className="font-medium text-primary underline underline-offset-2"
      >
        {label}
      </Link>
    </Drawer.Close>
  );
}

/** 평문 조각에서 bare 내부 경로(라벨=경로)를 링크화한다. 마크다운 링크 처리 후의 안전망. */
function linkifyBarePaths(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = new RegExp(BARE_PATH_RE, "gu");
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const path = match[0];
    nodes.push(internalLink(path, path, `${keyPrefix}-${match.index}`));
    last = match.index + path.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

/** 어시스턴트 content를 렌더 분해한다: 마크다운 `[라벨](/경로)`는 **라벨만** 링크(URL 숨김),
 *  그 밖 평문의 bare 내부 경로는 안전망으로 링크, 비-내부 URL은 링크하지 않는다. */
function renderAssistantContent(content: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = new RegExp(MD_LINK_RE.source, "g");
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  while ((match = re.exec(content)) !== null) {
    if (match.index > last) {
      nodes.push(...linkifyBarePaths(content.slice(last, match.index), `seg${i}`));
    }
    const label = match[1];
    const path = toInternalPath(match[2]); // 절대 URL이어도 경로만 추출(URL 비노출 — KTH #7)
    if (path && INTERNAL_HREF_RE.test(path)) {
      // 내부 경로 → 라벨("상세보기"·"여기")만 링크, URL은 숨긴다.
      nodes.push(internalLink(path, label, `md${i}`));
    } else {
      // 비-내부(잠재 악성 URL/스킴) → 라벨만 평문(URL 제거·링크 금지 — 신뢰 경계).
      nodes.push(label);
    }
    last = match.index + match[0].length;
    i += 1;
  }
  if (last < content.length) {
    nodes.push(...linkifyBarePaths(content.slice(last), "tail"));
  }
  return nodes;
}

/** 대화 한 줄 버블 — user(우측 primary) / assistant(좌측 muted). */
function ChatBubble({ role, content }: { role: string; content: string }) {
  const isUser = role === "user";
  return (
    <div
      className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm leading-[1.6] ${
        isUser
          ? "self-end bg-primary text-primary-foreground"
          : "self-start bg-muted text-foreground"
      }`}
    >
      {/* 어시스턴트 버블만 내부 경로 linkify(LLM 출력 신뢰 경계). user 입력은 평문 유지. */}
      {isUser ? content : renderAssistantContent(content)}
    </div>
  );
}
