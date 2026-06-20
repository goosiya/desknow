// 핀 DOM 요소 빌더 (Story 3.2). 카카오 CustomOverlay 의 content 로 쓸 접근성 버튼을 만든다.
//
// pin.ts(순수 로직)와 분리한다 — 이 모듈은 DOM 에 의존하므로(impure) 별도로 둔다. 색은
// pinVisual 이 토큰에서 가져온 hex 를 inline style 로만 쓴다(하드코딩 금지·단일 출처). 아이콘과
// aria-label 을 함께 부여해 색 단독 신호를 피한다(AC2·AC4). 터치 타겟 ≥44px(.tap-target).
import { pinAriaLabel, pinVisual, type RoomPin } from "./pin";

const ICON_GLYPH: Record<"check" | "x", string> = {
  check: "✓",
  x: "✕",
};

/**
 * 핀 1개를 나타내는 접근성 버튼 요소를 만든다(role=button·aria-label·키보드 도달·≥44px).
 * 클릭/Enter 시 onSelect(pin) 을 호출한다(핀→바텀시트 — AC3).
 */
export function createPinElement(
  pin: RoomPin,
  onSelect: (pin: RoomPin) => void,
): HTMLButtonElement {
  const visual = pinVisual(pin.status);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "tap-target desknow-map-pin";
  button.setAttribute("aria-label", pinAriaLabel(pin.name, pin.status));
  button.dataset.roomId = pin.room_id;
  button.dataset.status = pin.status;
  // 원형 핀 — 색은 토큰 hex(단일 출처), 흰 글리프, 그림자. 색 외 아이콘이 독립 신호다.
  button.style.cssText = [
    "display:inline-flex",
    "align-items:center",
    "justify-content:center",
    "width:44px",
    "height:44px",
    "border-radius:9999px",
    "border:2px solid #FFFFFF",
    `background-color:${visual.hex}`,
    "color:#FFFFFF",
    "font-size:18px",
    "line-height:1",
    "cursor:pointer",
    "box-shadow:0 2px 6px rgba(40,32,15,0.28)",
  ].join(";");
  // 아이콘 글리프(시각). 스크린리더는 button 의 aria-label 을 읽으므로 글리프는 aria-hidden.
  const glyph = document.createElement("span");
  glyph.setAttribute("aria-hidden", "true");
  glyph.textContent = ICON_GLYPH[visual.icon];
  button.appendChild(glyph);
  button.addEventListener("click", () => onSelect(pin));
  return button;
}
