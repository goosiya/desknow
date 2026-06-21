"use client";

// 스터디룸 찾기 컨테이너 (Story 3.4 + 3.5 + 3.6 — AC1~AC5). 지도(3.2)와 목록을 **지도/목록 토글**로
// 전환하고, 목록 안에서 **지역|반경 검색방식 서브토글**로 두 검색을 오간다. **선택 상태(지역
// 시군구/동 + 반경값)를 컨테이너가 보유**해 토글·검색방식 왕복 시 보존된다(AC2·AC5). 목록 행 탭은
// 3.3 RoomSheet(지도-비결합 재사용)를 연다 — 신규 시트/상세 라우트 0.
//
// 3.6 위치 신호 단일 소유 + 진입 자동 우회: useGeolocation 을 **마운트 즉시 enable** 해 위치를
// 1회만 요청하고, 그 결과를 지도(coords/locationDenied prop)·반경(center) 양쪽에 공급한다(AC4).
// 거부/미지원이면 진입을 **지역 목록으로 자동 우회**(viewMode=list·searchMode=region) + 안내한다
// (AC1). 자동 우회는 세션당 1회·useRef 비파괴 가드 — 사용자가 토글을 직접 누르면(또는 이미
// 우회했으면) 다시 자동 전환하지 않는다(AC5③). 허용이면 지도 유지(현위치 중심), 측정 중이면 대기.
// 범위: lg 2열(지도+사이드 목록)은 비포함(토글 단일 뷰).
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { LocateFixed } from "lucide-react";

import type { RoomListItem } from "@/lib/api-client";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { MapView } from "@/features/map/MapView";
import { RoomSheet } from "@/features/map/RoomSheet";
import { pinStatus } from "@/features/map/pin";

import { RadiusControl } from "./RadiusControl";
import { RegionCombos } from "./RegionCombos";
import { RoomList } from "./RoomList";
import { resolveRegionCode } from "./regions";
import { useGeolocation } from "./useGeolocation";

type ViewMode = "map" | "list";
type SearchMode = "region" | "radius";

const DEFAULT_RADIUS_KM = 3; // 범위 결정 #6 — 반경 기본 3km

/** 두 토글(지도/목록·지역/반경)의 공통 세그먼트 버튼 스타일(3.4 토글 미러 — 토큰만). */
function segmentClass(active: boolean): string {
  return `tap-target inline-flex items-center justify-center rounded-md px-4 text-sm font-medium ${
    active
      ? "bg-primary text-primary-foreground"
      : "text-muted-foreground hover:bg-muted"
  }`;
}

export function ExploreView() {
  // 딥링크 진입(챗봇 '더보기' 등) — `?view=list&sigungu=&dong=` 로 목록 뷰 + 지역 필터를 미리
  // 적용한다(KTH 2026-06-18). 챗봇이 "상위 3 + 더보기"로 끊어 보여준 뒤, 더보기를 누르면 그 지역
  // 전체 목록으로 바로 진입하게 하는 연결 고리다.
  // useSearchParams 는 환경에 따라 null 일 수 있어(테스트·SSR 경계) 옵셔널 체이닝으로 방어한다 —
  // 없으면 딥링크 미적용(기존 지도 기본 진입과 동일).
  const searchParams = useSearchParams();
  const deepLinkSigungu = searchParams?.get("sigungu") ?? undefined;
  const deepLinkDong = searchParams?.get("dong") ?? undefined;
  const deepLinked =
    searchParams?.get("view") === "list" || deepLinkSigungu !== undefined;

  const [viewMode, setViewMode] = useState<ViewMode>(deepLinked ? "list" : "map");
  const [searchMode, setSearchMode] = useState<SearchMode>("region");
  // 지역 선택(3.4) — 컨테이너가 보유해 토글/검색방식 왕복 시 보존(AC2·AC5). RegionCombos 는 controlled.
  // 딥링크면 URL 의 지역 코드로 초기화(미지정이면 기존대로 undefined).
  const [sigunguCode, setSigunguCode] = useState<string | undefined>(deepLinkSigungu);
  const [dongCode, setDongCode] = useState<string | undefined>(deepLinkDong);
  // 반경값(3.5) — 컨테이너가 보유해 검색방식 전환 후에도 보존(AC2). 기본 3km.
  const [radiusKm, setRadiusKm] = useState<number>(DEFAULT_RADIUS_KM);
  // 목록 행 탭으로 열리는 시트 대상(3.3 RoomSheet 재사용 — roomId+name+fallbackStatus).
  const [selectedRoom, setSelectedRoom] = useState<RoomListItem | null>(null);

  const regionCode = resolveRegionCode(sigunguCode, dongCode);
  // 위치는 ExploreView 단일 소유 — 지도 중심·반경 center·UI 분기에 공급한다(요청 1회). 위치 권한
  // 선확인 개편(KTH 2026-06-18): granted면 자동 측정해 내 위치로, prompt/denied면 자동 측정하지
  // 않고 기본 위치 유지(지도 화면은 안내 문구, 목록 반경은 사용자 요청 시 측정).
  const geo = useGeolocation(true);
  // 지역 상수로 풀어 effect 의존성을 원시값/안정 ref 로 둔다(exhaustive-deps — geo 객체는 매 렌더
  // 새로 생성되므로 deps 에 넣으면 매 렌더 재실행됨). geo.locate 는 useCallback 으로 안정적이다.
  const {
    status: geoStatus,
    permission: geoPermission,
    permissionResolved: geoPermissionResolved,
    coords: geoCoords,
    locate: geoLocate,
    refresh: geoRefresh,
  } = geo;
  const locationDenied = geoStatus === "denied" || geoStatus === "unsupported";
  const hasLocationPermission = geoPermission === "granted";

  // 지도 생성 보류 신호(KTH 2026-06-19): 지도를 서울 폴백으로 먼저 그렸다가 coords 도착 시
  // 이동시키면 "서울→내 위치 점프"가 보이고 느리게 느껴진다. 그래서 **권한이 있으면 좌표를 확보할
  // 때까지 지도 생성을 미뤄** 처음부터 내 위치로 그린다. 권한 판정 전(아직 모름)이거나 granted로
  // 측정 중이고 좌표가 없을 때만 보류한다 — prompt/denied/미지원 확정이면 즉시 서울로 그린다.
  const mapPendingLocation =
    !geoCoords &&
    (!geoPermissionResolved ||
      (geoPermission === "granted" &&
        (geoStatus === "idle" || geoStatus === "locating")));

  // '내 반경' 재중심 신호 — 클릭마다 증가시켜 MapView 가 현 위치로 중심을 다시 옮기게 한다(좌표가
  // 동일해도 effect 가 재실행되도록 nonce 사용). 클릭 시 위치도 갱신(이동했을 수 있음)한다.
  const [recenterNonce, setRecenterNonce] = useState(0);
  // 거부(denied) 안내 카드 펼침 상태 — 칩 클릭 시 '자물쇠 → 위치 → 허용' 수동 설정 경로를 펼친다.
  // 브라우저는 denied 상태에서 네이티브 권한 팝업/설정창을 코드로 다시 못 열어, 안내만이 유일한 길이다.
  const [geoGuideOpen, setGeoGuideOpen] = useState(false);

  // 수동 토글/딥링크 비파괴 가드: true 면 위치 신호가 뷰를 자동 전환하지 않는다. 딥링크(더보기)는
  // 의도된 진입이라 처음부터 잠근다. (위치 거부 자동 우회는 지도 UX 개편으로 제거 — 지도는 기본
  // 위치 유지 + 안내 문구로 처리한다.)
  const viewLockedRef = useRef(deepLinked);

  // 목록 반경 모드 진입 시 위치 권한이 prompt면 그때 측정을 요청한다(지도 화면처럼 진입만으로
  // 프롬프트를 띄우지 않되, 사용자가 반경 검색을 고르면 측정한다 — 막힘 방지). granted/denied/측정
  // 중이면 아무 것도 하지 않는다. set-state-in-effect 회피 위해 마이크로태스크로 이월.
  useEffect(() => {
    if (searchMode === "radius" && geoPermission === "prompt" && geoStatus === "idle") {
      queueMicrotask(() => geoLocate());
    }
  }, [searchMode, geoPermission, geoStatus, geoLocate]);

  // 딥링크 파라미터 변화 동기화 — useState 초기화는 **최초 마운트에만** 동작하므로, 이미 마운트된
  // ExploreView(챗봇 '더보기' 클릭 = 같은 '/' 라우트의 쿼리만 변경되는 클라 네비)에선 이 효과가
  // 목록 뷰 + 지역 필터를 적용한다. set-state-in-effect 동기 캐스케이드 함정은 마이크로태스크
  // 이월로 회피한다(위 geo 우회 선례). isList 일 때만 적용해 루프 없음(searchParams 는 URL 변경 시만 갱신).
  useEffect(() => {
    const sigungu = searchParams?.get("sigungu") ?? undefined;
    const dong = searchParams?.get("dong") ?? undefined;
    const isList = searchParams?.get("view") === "list" || sigungu !== undefined;
    if (!isList) return;
    viewLockedRef.current = true; // 의도된 진입 — 위치 자동 우회보다 우선
    queueMicrotask(() => {
      setViewMode("list");
      setSearchMode("region");
      if (sigungu !== undefined) setSigunguCode(sigungu);
      if (dong !== undefined) setDongCode(dong);
    });
  }, [searchParams]);

  // 최상위 지도/목록 토글 핸들러 — 수동 선택은 자동 우회를 잠근다(AC5③).
  function handleSelectView(next: ViewMode): void {
    viewLockedRef.current = true;
    setViewMode(next);
  }

  // 검색방식(지역|반경) 수동 선택도 자동 우회를 잠근다(AC5③ 일관 — code-review 2026-06-16).
  // 사용자가 검색방식을 직접 고른 뒤 늦게 도착한 denied 가 그 선택을 region 으로 덮어쓰지
  // 않도록 한다. (현재 list 뷰 진입 경로는 모두 viewLockedRef 를 먼저 세우므로 — 방어적
  // 하드닝 성격이며 불변식을 명시한다: "사용자의 어떤 토글 선택도 자동 우회보다 우선".)
  function handleSelectSearchMode(next: SearchMode): void {
    viewLockedRef.current = true;
    setSearchMode(next);
  }

  // 지도 빈/에러 상태의 "목록 우회" 액션(3.8 AC1) — 목록 뷰로 전환하고 검색방식을 지정한다.
  // 수동 토글과 동일하게 자동 우회를 잠근다(AC5③ 정신). 위치가 없으면 list/radius 가 자체적으로
  // "위치 확인 중/거부" graceful 처리하므로 막힘이 아니다.
  function handleSwitchToList(mode: SearchMode): void {
    viewLockedRef.current = true;
    setViewMode("list");
    setSearchMode(mode);
  }

  // '내 반경' 클릭 — 위치를 갱신(이동했을 수 있음)하고 지도를 현 위치로 재중심한다. 권한이 이미
  // granted라 프롬프트 없이 측정된다.
  function handleRecenter(): void {
    geoLocate();
    setRecenterNonce((n) => n + 1);
  }

  return (
    <div className="flex flex-col gap-4">
      {/* 최상위 줄: 지도/목록 토글(왼쪽) + 지도 화면에서 위치 권한 있을 때 '내 반경'(오른쪽 끝). */}
      <div className="flex items-center justify-between gap-2">
        {/* 지도/목록 토글 — 텍스트 라벨(접근 이름 내장) + aria-pressed(NFR-5). */}
        <div
          role="group"
          aria-label="지도·목록 보기 전환"
          className="inline-flex rounded-md border border-border p-0.5"
        >
          <button
            type="button"
            aria-pressed={viewMode === "map"}
            onClick={() => handleSelectView("map")}
            className={segmentClass(viewMode === "map")}
          >
            지도
          </button>
          <button
            type="button"
            aria-pressed={viewMode === "list"}
            onClick={() => handleSelectView("list")}
            className={segmentClass(viewMode === "list")}
          >
            목록
          </button>
        </div>

        {/* '내 반경' — 지도 화면 + 위치 권한 허용 시에만. 클릭하면 지도가 어디 있든 내 위치로 재중심. */}
        {viewMode === "map" && hasLocationPermission && (
          <button
            type="button"
            onClick={handleRecenter}
            className="tap-target inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 text-sm font-medium text-card-foreground hover:bg-muted"
          >
            <LocateFixed className="size-4" aria-hidden />내 반경
          </button>
        )}
      </div>

      {viewMode === "map" ? (
        // 위치 좌표/거부를 prop 으로 주입(MapView 인라인 위치 제거 — 위치 요청 1회). 허용=현위치 중심,
        // 미허용=서울 폴백 중심. recenterNonce 로 '내 반경' 클릭 시 재중심.
        // 권한 안내는 지도 위에 **오버레이**한다 — 일반 흐름에 두면 모바일에서 지도를 영역 밖으로
        // 밀어내므로(지도 높이 고정), 지도 상단에 떠서 레이아웃을 차지하지 않게 한다.
        // -mb-24(모바일): main 의 pb-24(하단 네비 여백)를 지도 뷰에서만 상쇄한다 — 지도 높이를
        // 네비 상단까지 맞췄으므로(MapView fitHeight) 그 패딩이 남으면 47px 잔여 스크롤이 생겨
        // 스크롤 시 지도가 네비에서 떨어진다. md+ 는 mb-0(PC 무영향 — 60vh 정상 흐름).
        <div className="relative -mb-24 md:mb-0">
          {/* ★권한 확인 완료(geoPermissionResolved) 후에만 칩을 렌더한다(KTH 2026-06-19 깜빡임 수정).
              useGeolocation 의 초기 permission 은 "prompt" 라, 게이트가 없으면 Permissions API 가
              실제 권한을 확인하기 **전부터** 칩이 떴다가 granted 로 resolve 되면 사라져 "보였다 사라짐"
              깜빡임이 난다. 확인 전엔 아무 것도 안 띄우고(권한 모름), 확인 후 granted 아니면 그때 띄운다. */}
          {geoPermissionResolved && !hasLocationPermission && (
            // pointer-events-none 래퍼 + auto 칩: 칩 밖 지도 영역은 그대로 드래그 가능, 칩만 클릭.
            <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex justify-center p-3">
              {geoPermission === "prompt" ? (
                // prompt: 클릭하면 getCurrentPosition → 브라우저 네이티브 권한 팝업이 뜬다. 문구를
                // "여기를 눌러"로 보강 — 칩을 눌러야 한다는 걸 모르는 사용자를 위해(KTH 2026-06-21).
                <button
                  type="button"
                  onClick={geoLocate}
                  className="pointer-events-auto inline-flex items-center gap-1.5 rounded-md bg-secondary px-3 py-2 text-sm text-secondary-foreground shadow-sheet hover:bg-secondary/80"
                >
                  <LocateFixed className="size-4 shrink-0" aria-hidden />
                  위치 권한이 꺼져 있어요. 여기를 눌러 위치 권한을 허용해 주세요.
                </button>
              ) : (
                // denied/미지원 — 네이티브 팝업이 다시 안 뜨므로(브라우저 차단), 칩 클릭 시 수동 설정
                // 경로('자물쇠 → 위치 → 허용')를 카드로 펼쳐 안내한다(코드로 설정창을 못 연다). 설정 후
                // 탭 복귀 시 focus 재확인이 자동 반영하고, '새로고침'(geoRefresh)으로도 즉시 재확인한다.
                // ⚠️ 카피는 모바일 앱과 의도적으로 다르다(웹 전용 — KTH 2026-06-20). 재-동기화 금지.
                <div className="pointer-events-auto flex w-full max-w-xs flex-col gap-2">
                  <button
                    type="button"
                    aria-expanded={geoGuideOpen}
                    onClick={() => setGeoGuideOpen((open) => !open)}
                    className="inline-flex items-center gap-1.5 rounded-md bg-secondary px-3 py-2 text-sm text-secondary-foreground shadow-sheet hover:bg-secondary/80"
                  >
                    <LocateFixed className="size-4 shrink-0" aria-hidden />
                    위치 권한이 꺼져 있어요. 여기를 눌러 위치 권한을 허용해 주세요.
                  </button>
                  {geoGuideOpen && (
                    <div className="rounded-md bg-card p-3 text-left text-sm text-card-foreground shadow-sheet">
                      <p className="mb-1.5 font-medium">위치 권한 허용 방법</p>
                      <ol className="list-decimal space-y-1 pl-4 text-muted-foreground">
                        <li>주소창의 자물쇠(🔒) 아이콘을 누르세요.</li>
                        <li>‘위치’ 권한을 ‘허용’으로 바꿔주세요.</li>
                        <li>아래 ‘새로고침’을 누르세요.</li>
                      </ol>
                      <button
                        type="button"
                        onClick={geoRefresh}
                        className="mt-2 inline-flex items-center justify-center rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                      >
                        새로고침
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
          <MapView
            coords={geoStatus === "granted" ? geoCoords : null}
            pendingLocation={mapPendingLocation}
            recenterNonce={recenterNonce}
            onSwitchToList={handleSwitchToList}
          />
        </div>
      ) : null}

      {viewMode !== "map" && (
        <div className="flex flex-col gap-3">
          {/* 검색방식 토글(지역|내 반경) + 인라인 컨트롤(지역 콤보 / 반경 프리셋)을 한 줄에 둔다.
              flex-wrap 으로 좁은 화면에선 자연 줄바꿈, 표준 간격(gap-3)으로 토글과 컨트롤을 분리. */}
          <div className="flex flex-wrap items-center gap-3">
            {/* 검색방식 토글(지역|내 반경) — aria-pressed·접근 이름(NFR-5). 양쪽 상태는 보존.
                "내 반경"은 지도 검색 버튼과 용어만 통일(기능 공유 아님 — 검색방식 전환 토글 그대로). */}
            <SegmentedControl
              ariaLabel="검색 방식 전환"
              value={searchMode}
              onChange={(v) => handleSelectSearchMode(v as SearchMode)}
              options={[
                { value: "region", label: "지역" },
                { value: "radius", label: "내 반경" },
              ]}
            />

            {/* 토글 옆 인라인 컨트롤 — 지역: 콤보 / 반경(위치 허용 시): 프리셋.
                그 외(거부·미지원·측정 중)는 컨트롤 없이 토글만 두고, 안내는 아래 줄에 둔다. */}
            {searchMode === "region" ? (
              <RegionCombos
                sigunguCode={sigunguCode}
                dongCode={dongCode}
                onSigunguChange={setSigunguCode}
                onDongChange={setDongCode}
              />
            ) : geoStatus === "granted" && geoCoords ? (
              <RadiusControl radiusKm={radiusKm} onChange={setRadiusKm} />
            ) : null}
          </div>

          {/* 안내·목록 — 컨트롤 줄 아래. */}
          {searchMode === "region" ? (
            <>
              {/* 3.6 AC1②: 위치 거부/미지원으로 우회된 경우 이유 안내(거부 신호와 연동 —
                  허용/측정 중엔 미표시). MapView 배너와 같은 카피·토큰(secondary)·role="status". */}
              {locationDenied && (
                <p
                  role="status"
                  className="rounded-md border border-border bg-secondary px-4 py-2 text-sm leading-[1.6] text-secondary-foreground"
                >
                  현재 위치를 못 받았어요. 동네를 골라서 찾아볼게요.
                </p>
              )}
              <RoomList
                search={{ kind: "region", regionCode }}
                onSelectRoom={setSelectedRoom}
              />
            </>
          ) : geoStatus === "granted" && geoCoords ? (
            // 위치 허용: 반경 목록(가까운 순). center 는 현위치(컨트롤은 위 줄).
            <RoomList
              search={{ kind: "radius", center: geoCoords, radiusKm }}
              onSelectRoom={setSelectedRoom}
            />
          ) : geoStatus === "denied" || geoStatus === "unsupported" ? (
            // AC3: 위치 거부/미지원 → 반경 비활성 + 이유 안내 + 지역 유도(막다른 화면 금지).
            <div
              role="status"
              className="flex flex-col items-center gap-3 rounded-lg border border-border bg-card p-6 text-center"
            >
              <p className="text-sm leading-[1.6] text-card-foreground">
                현재 위치를 못 받았어요. 동네를 골라서 찾아볼게요.
              </p>
              <button
                type="button"
                onClick={() => handleSelectSearchMode("region")}
                className="tap-target inline-flex items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
              >
                지역으로 찾기
              </button>
            </div>
          ) : (
            // prompting/idle: 위치 확인 중(막힘 아님).
            <p className="rounded-lg border border-border bg-card p-6 text-center text-sm leading-[1.6] text-muted-foreground">
              현위치를 확인하고 있어요…
            </p>
          )}

          {/* 목록 항목 탭 → 3.3 시트(지도-비결합 재사용). 두 검색방식이 공유. open 으로 제어. */}
          <RoomSheet
            roomId={selectedRoom?.room_id ?? ""}
            name={selectedRoom?.name ?? ""}
            fallbackStatus={
              selectedRoom ? pinStatus(selectedRoom.remaining_slots) : undefined
            }
            open={!!selectedRoom}
            onOpenChange={(o) => {
              if (!o) setSelectedRoom(null);
            }}
          />
        </div>
      )}
    </div>
  );
}
