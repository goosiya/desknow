"use client";

// 세션 슬라이딩 연장 + 만료 안내/리다이렉트 (KTH 2026-06-18). 전역 1회 마운트(Providers).
//
// access 토큰은 기본 15분이지만 **사용자 인터랙션이 있으면 계속 연장**한다 — 활동 플래그를 두고
// 10분 주기로 그 사이 활동이 있었으면 authRefresh 로 토큰 쌍을 회전 발급한다(쿠키 갱신). 활동이
// 없으면(유휴) 갱신하지 않아 자연 만료된다. 만료(authMe 401 → 세션 null 전이)되면 "로그인 시간이
// 만료됐어요" 안내와 함께 /login 으로 보낸다. **수동 로그아웃은 만료가 아니므로** 제외한다
// (sessionExpiry 플래그).
//
// 갱신 주기 10분 < TTL 15분이라 활동 중엔 만료 전에 항상 1회 이상 갱신된다(여유 5분). 백그라운드
// 탭은 setInterval 이 throttle 되지만, 복귀 시 refetchOnWindowFocus(useSession)가 authMe 를
// 재조회해 유휴 만료를 곧바로 잡는다(만료 전이 발화).
import { useEffect, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";

import { authRefresh } from "@/lib/api-client";
import { useSession } from "./useSession";
import { consumeManualLogout } from "./sessionExpiry";

// 활동 시 갱신 최소 간격(< access TTL 15분). 이 주기 tick 에서 직전 활동 여부를 보고 갱신한다.
const REFRESH_INTERVAL_MS = 10 * 60_000;

export function SessionKeeper() {
  const { data: user } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  // 직전 tick 이후 사용자 인터랙션 발생 여부(유휴 판정용 — 활동 없으면 갱신 skip).
  const activeSinceTick = useRef(false);
  // 직전 로그인 여부 — 로그인→null **전이**에서만 만료 처리(최초 미로그인엔 발화 금지).
  const wasAuthed = useRef(false);

  // 인터랙션 마킹 — passive 리스너로 렌더/스크롤 비용 0. 마운트 1회.
  // ⚠️ **capture 단계**로 등록한다 — 챗봇 드로어(vaul 포털)·모달 등 오버레이 내부에서 일어나는
  //    입력/클릭도 window 까지 버블되기 전에 포착해 세션 연장으로 친다(KTH 2026-06-18 — 챗봇
  //    인터랙션도 로그아웃 타임 연장). capture 는 stopPropagation 에도 영향받지 않는다(top-down).
  useEffect(() => {
    const mark = () => {
      activeSinceTick.current = true;
    };
    const events = ["pointerdown", "keydown", "scroll"] as const;
    const opts = { capture: true, passive: true } as const;
    events.forEach((e) => window.addEventListener(e, mark, opts));
    return () =>
      events.forEach((e) => window.removeEventListener(e, mark, opts));
  }, []);

  // 슬라이딩 갱신 — 로그인 상태에서만. tick 마다 직전 구간 활동이 있었으면 토큰 갱신(쿠키 회전).
  useEffect(() => {
    if (!user) return;
    const id = setInterval(() => {
      if (!activeSinceTick.current) return; // 유휴 → 갱신 안 함(자연 만료 허용)
      activeSinceTick.current = false;
      // 실패(refresh 토큰 만료 등)는 무시 — 다음 authMe 401 전이에서 만료 처리가 이어진다.
      void authRefresh({ body: {}, throwOnError: false }).catch(() => {});
    }, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [user]);

  // 만료 감지 — 로그인→null 전이. 수동 로그아웃이면 skip(만료 아님), 아니면 안내+로그인 이동.
  useEffect(() => {
    if (user) {
      wasAuthed.current = true;
      return;
    }
    if (user === null && wasAuthed.current) {
      wasAuthed.current = false;
      if (consumeManualLogout()) return; // 직접 로그아웃 → 만료 안내/리다이렉트 없음
      // 만료 → 로그인 화면으로(현재 경로를 next 로, 단 /login 자기 자신은 제외).
      const onLogin = pathname?.startsWith("/login");
      const next =
        pathname && !onLogin ? `&next=${encodeURIComponent(pathname)}` : "";
      if (!onLogin) router.replace(`/login?expired=1${next}`);
    }
  }, [user, pathname, router]);

  return null;
}
