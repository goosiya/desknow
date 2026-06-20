"use client";

// 첫 방문 온보딩 오버레이 (Story 3.9 — AC1·AC2·AC4). 진입 화면 위에 뜨는 소개 모달.
//
// 단발 카드가 아니라 **스와이프 캐러셀**(수동 드래그/화살표/점 + 자동 넘김)로 사용·예약 방법을
// 페이지 단위로 안내한다. cross-cutting app 레벨 표시라 features 밖 components 직하에 둔다
// (NetworkNotice 선례). Radix `Dialog`(radix-ui — 3.4 도입분 재사용, 신규 의존성 0)로 포커스 트랩·
// Esc·aria-modal·포커스 복귀·스크롤 잠금을 **상속**한다.
//
// 닫기 정책(2026-06-19 변경): **"다시 보지 않기"만 플래그 영속**(dismiss — 재방문 무노출).
//   "시작하기"·우상단 X·Esc·바깥 클릭은 영속 없이 이번만 닫는다(close — 다음 방문 시 재노출).
//   막다른 화면 금지(AC4) — 닫으면 이미 렌더된 탐색 화면이 드러난다.
//
// ★a11y: 오픈 시 포커스를 모달 내부(Content)로 명시 이동한다(onOpenAutoFocus) — 안 그러면 바깥의
//   챗봇 FAB가 포커스를 쥔 채 aria-hidden 처리돼 "Blocked aria-hidden … retained focus" 경고가 난다.
import { Dialog } from "radix-ui";
import {
  CalendarCheck,
  ChevronLeft,
  ChevronRight,
  Compass,
  MessageCircle,
  Sparkles,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { useOnboarding } from "@/lib/useOnboarding";

/** 자동 넘김 간격(ms). 사용자가 한 번이라도 직접 조작하면 자동 넘김은 멈춘다. */
const AUTO_ADVANCE_MS = 4500;
/** 스와이프 판정 임계 픽셀 — 이만큼 끌어야 페이지가 넘어간다(오조작 방지). */
const SWIPE_THRESHOLD_PX = 56;

type Slide = {
  icon: LucideIcon;
  title: string;
  body: string;
  /** 선택적 주의 문구(작은 두꺼운 빨강). 위치 권한 같은 전제 조건 안내용. */
  note?: string;
};

// 사용·예약 흐름을 페이지 단위로 친절하게 안내한다(톤앤매너: 만다린 토큰 + 해요체).
const SLIDES: Slide[] = [
  {
    icon: Sparkles,
    title: "DeskNow에 오신 걸 환영해요",
    body: "내 주변에서 지금 비어 있는 스터디룸을 찾아 바로 예약하는 가장 빠른 방법이에요. 잠깐 둘러볼까요?",
  },
  {
    icon: Compass,
    title: "지도와 목록으로 찾기",
    body: "지도 핀과 목록에서 지금 이용할 수 있는 스터디룸을 한눈에 볼 수 있어요. 지역이나 반경으로 원하는 동네만 좁혀보세요.",
    note: "브라우저나 휴대폰의 위치 정보가 꺼져 있으면 반경 검색은 이용할 수 없어요. 위치 권한을 켜주세요.",
  },
  {
    icon: CalendarCheck,
    title: "원하는 시간에 바로 예약",
    body: "스터디룸 상세에서 날짜와 시간을 고르고 ‘예약하기’를 누르면 끝이에요. 연속된 시간도 한 번에 선택할 수 있어요.",
  },
  {
    icon: MessageCircle,
    title: "궁금하면 룸메이트 챗봇",
    body: "오른쪽 아래 챗봇에게 “강남에 지금 빈 방 있어?”처럼 물어보면 자리를 찾아 예약까지 도와드려요. 예약현황·즐겨찾기로 관리도 간편해요.",
  },
];

export function OnboardingOverlay() {
  const { shouldShow, dismiss, close } = useOnboarding();
  const [current, setCurrent] = useState(0);
  // 사용자가 직접 조작(스와이프·화살표·점)하면 자동 넘김 중단 — 통제권을 가져가는 순간 멈추는 게 가장 덜 거슬린다.
  const [autoPlay, setAutoPlay] = useState(true);
  const [reduced, setReduced] = useState(false);
  // 드래그 중 트랙을 손가락 따라 움직이는 오프셋(px). pointerup에서 임계 넘으면 페이지 전환.
  const [dragPx, setDragPx] = useState(0);
  // 드래그 중에는 트랙 transition을 끈다(손가락 추적) — 렌더 중 ref 접근 금지(react-hooks/refs)라 state로 둔다.
  const [dragging, setDragging] = useState(false);
  const dragStartX = useRef<number | null>(null);
  // ★최신 델타는 ref로 따로 둔다 — pointerup이 state(dragPx)를 읽으면 React 배칭으로 직전
  //   pointermove의 setState가 아직 반영 안 돼 stale(0)을 볼 수 있다(전환 누락). ref는 항상 최신.
  const dragDelta = useRef(0);
  const contentRef = useRef<HTMLDivElement>(null);

  const last = SLIDES.length - 1;
  const isLast = current === last;

  // prefers-reduced-motion: 자동 넘김·슬라이드 애니메이션을 끈다(NFR-5).
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduced(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  // 자동 넘김 — 마지막 페이지 전까지 한 칸씩. 직접 조작/reduced-motion/닫힘 시 멈춘다.
  useEffect(() => {
    if (!shouldShow || !autoPlay || reduced || current >= last) return;
    const id = window.setTimeout(
      () => setCurrent((c) => Math.min(c + 1, last)),
      AUTO_ADVANCE_MS,
    );
    return () => window.clearTimeout(id);
  }, [shouldShow, autoPlay, reduced, current, last]);

  function goTo(index: number) {
    setAutoPlay(false); // 직접 조작 → 자동 넘김 중단.
    setCurrent(Math.max(0, Math.min(index, last)));
  }

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    dragStartX.current = e.clientX;
    setDragging(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (dragStartX.current === null) return;
    dragDelta.current = e.clientX - dragStartX.current;
    setDragPx(dragDelta.current);
  }
  function onPointerUp() {
    if (dragStartX.current === null) return;
    const delta = dragDelta.current;
    dragStartX.current = null;
    dragDelta.current = 0;
    setDragPx(0);
    setDragging(false);
    if (delta <= -SWIPE_THRESHOLD_PX && current < last) goTo(current + 1);
    else if (delta >= SWIPE_THRESHOLD_PX && current > 0) goTo(current - 1);
  }

  return (
    <Dialog.Root
      open={shouldShow}
      onOpenChange={(open) => {
        // Esc·바깥 클릭 → 영속 없이 이번만 닫는다(close). 영속은 "다시 보지 않기"만.
        if (!open) close();
      }}
    >
      <Dialog.Portal>
        {/* 딤 배경 — reduced-motion 시 모션 생략(motion-safe 게이팅, NFR-5). 토큰만. */}
        <Dialog.Overlay className="fixed inset-0 z-50 bg-foreground/30 data-[state=open]:motion-safe:animate-in data-[state=open]:motion-safe:fade-in-0" />
        {/* 중앙 카드 — 안내가 넉넉하도록 폭/높이를 키운다(max-w-md). RoomSheet 카드 토큰 미러. */}
        <Dialog.Content
          ref={contentRef}
          tabIndex={-1}
          // ★오픈 시 포커스를 Content로 가져와 바깥 FAB의 포커스 잔존(aria-hidden 경고)을 없앤다.
          onOpenAutoFocus={(e) => {
            e.preventDefault();
            contentRef.current?.focus();
          }}
          className="fixed left-1/2 top-1/2 z-50 flex w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 flex-col gap-5 rounded-xl border border-border bg-card p-6 text-card-foreground shadow-dialog focus:outline-none data-[state=open]:motion-safe:animate-in data-[state=open]:motion-safe:fade-in-0 data-[state=open]:motion-safe:zoom-in-95 sm:p-7"
        >
          {/* 우상단 닫기(X) — 영속 없이 이번만 닫는다(close). 다음 방문 시 다시 노출.
              ★z-10(KTH 2026-06-19 모바일): 아래 슬라이드 트랙의 내부 div 가 `transform: translateX`
              로 스택킹 컨텍스트를 만들어, z-index 없는 absolute X(z-auto)를 DOM 순서상 **위에서**
              덮어 클릭/탭을 가로챘다(마우스·터치 공통 — 닫기 버튼이 안 눌리던 원인). X 를 z-10 으로
              올려 트랙 위에서 항상 눌리게 한다. PC 도 동일하게 올바른 동작(닫기는 항상 최상단). */}
          <button
            type="button"
            onClick={close}
            aria-label="닫기"
            className="absolute right-3 top-3 z-10 rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X className="size-5" aria-hidden />
          </button>

          {/* Radix 요구 — 현재 슬라이드를 SR에 노출(시각 텍스트와 별개로 dialog 라벨/설명 제공). */}
          <Dialog.Title className="sr-only">{SLIDES[current].title}</Dialog.Title>
          <Dialog.Description className="sr-only">
            {SLIDES[current].note
              ? `${SLIDES[current].body} ${SLIDES[current].note}`
              : SLIDES[current].body}
          </Dialog.Description>

          {/* ── 슬라이드 뷰포트(스와이프) ── */}
          {/* 시각 전용: SR은 위 Dialog.Title/Description(현재 슬라이드)로 안내받으므로 트랙은
              aria-hidden 처리해 비현재 슬라이드 중복 낭독을 막는다. 내비게이션(점·버튼)은 트랙
              밖이라 접근 가능. */}
          <div
            aria-hidden
            className="-mx-1 touch-pan-y overflow-hidden"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
          >
            <div
              className={`flex ${!dragging && !reduced ? "transition-transform duration-300 ease-out" : ""}`}
              style={{ transform: `translateX(calc(-${current * 100}% + ${dragPx}px))` }}
            >
              {SLIDES.map((slide) => {
                const Icon = slide.icon;
                return (
                  <div
                    key={slide.title}
                    className="flex w-full shrink-0 select-none flex-col items-center gap-4 px-1 text-center"
                  >
                    {/* 아이콘 배지 — 만다린 토큰(secondary 크림 배경 + primary 오렌지 아이콘). */}
                    <div className="flex size-16 items-center justify-center rounded-full bg-secondary text-primary">
                      <Icon className="size-8" aria-hidden />
                    </div>
                    <div className="flex min-h-[120px] flex-col gap-2">
                      <h2 className="text-xl font-bold leading-[1.4] tracking-[-0.01em]">
                        {slide.title}
                      </h2>
                      <p className="text-sm leading-[1.6] text-muted-foreground">
                        {slide.body}
                      </p>
                      {/* 전제 조건 주의 — 작은 두꺼운 빨강(거슬리지 않게). 위치 권한 안내 등. */}
                      {slide.note ? (
                        <p className="text-xs font-semibold leading-[1.6] text-destructive">
                          {slide.note}
                        </p>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* ── 페이지 점(클릭 이동) ── */}
          <div className="flex justify-center gap-2" role="tablist" aria-label="안내 페이지">
            {SLIDES.map((slide, i) => (
              <button
                key={slide.title}
                type="button"
                role="tab"
                aria-selected={i === current}
                aria-label={`${i + 1}번째 안내`}
                onClick={() => goTo(i)}
                className={`size-2 rounded-full transition-colors ${
                  i === current ? "bg-primary" : "bg-border hover:bg-muted-foreground/40"
                }`}
              />
            ))}
          </div>

          {/* ── 하단: 다시 보지 않기 / 이전·다음(시작하기) ── */}
          <div className="flex items-center justify-between gap-3">
            <button
              type="button"
              onClick={dismiss}
              className="rounded text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline focus-visible:underline"
            >
              다시 보지 않기
            </button>
            <div className="flex items-center gap-2">
              {current > 0 ? (
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="이전"
                  onClick={() => goTo(current - 1)}
                >
                  <ChevronLeft className="size-4" aria-hidden />
                </Button>
              ) : null}
              {isLast ? (
                <Button variant="default" size="lg" onClick={close}>
                  시작하기
                </Button>
              ) : (
                <Button
                  variant="default"
                  size="lg"
                  onClick={() => goTo(current + 1)}
                  className="gap-1"
                >
                  다음
                  <ChevronRight className="size-4" aria-hidden />
                </Button>
              )}
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
