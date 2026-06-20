"use client";

// 스터디룸 등록/수정 폼 (idea.md L36 — provider 스터디룸 설정/수정). provider 웹 표면 구축.
//
// 이름·수용·시간당 금액·룸형태·부대시설·영업시간 + **주소 검색(지오코딩)**으로 좌표/지역을 채운다.
// 보유 룸이 있으면 그 값으로 prefill(수정), 없으면 생성. MVP는 제공자당 1개라 단일 폼이다.
// 백엔드 호출은 생성 SDK 경유 훅(useProviderRoom)만 — 직접 fetch 금지(1.9 가드).
import { useState } from "react";
import { useRouter } from "next/navigation";
import { MapPin, Search } from "lucide-react";

import type { GeocodeResult, ProviderRoomDetail, RoomCreateRequest } from "@/lib/api-client";
import { loadKakaoMaps } from "@/lib/kakao-map";
import { Button } from "@/components/ui/button";
import { AMENITY_LABELS, ROOM_TYPE_LABELS } from "@/features/map/roomSummary";
import { RoomLocationMap } from "@/features/detail/RoomLocationMap";
import { registerErrorCopy } from "@/features/auth/authCopy";
import {
  clearPendingSignup,
  getPendingSignup,
  type PendingSignup,
} from "@/features/auth/pendingSignup";
import { useRegister } from "@/features/auth/useAuth";
import { saveRoomErrorCopy, useGeocode, useMyRoom, useSaveRoom } from "./useProviderRoom";

const WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]; // index = date.weekday()(월=0)
const AMENITY_CODES = ["wifi", "whiteboard", "parking", "projector_tv", "coffee", "etc"] as const;
const ROOM_TYPES = ["open", "private"] as const;

type DayHours = { on: boolean; open: string; close: string };

/** "09:00:00" → "09:00"(input[type=time]용). */
function toHHMM(t: string): string {
  return t.slice(0, 5);
}

/** 초기 영업시간 — 보유 룸의 business_hours(영업일만 존재)를 7요일 행으로 펼친다. 없으면 매일 09–22. */
function initialHours(room: ProviderRoomDetail | null): DayHours[] {
  return WEEKDAYS.map((_, weekday) => {
    const found = room?.business_hours.find((h) => h.weekday === weekday);
    if (found) return { on: true, open: toHHMM(found.open_time), close: toHHMM(found.close_time) };
    // 신규는 매일 09–22 기본, 수정인데 그 요일이 없으면 휴무로.
    return { on: room === null, open: "09:00", close: "22:00" };
  });
}

/** 텍스트 인풋 공통 스타일(AuthForm Field 미러 — 토큰 기반). */
const inputClass =
  "h-11 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50";

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <span className="text-sm font-medium text-foreground">{children}</span>;
}

/** 가입 전(미인증) 주소 검색 — 카카오 JS SDK Geocoder 로 백엔드 없이 직접 조회한다(백엔드
 *  /rooms/geocode 는 provider 전용이라 가입 전엔 못 씀). 결과는 백엔드 GeocodeResult 형상으로
 *  통일(b_code=지역). 0건은 빈 배열(정상), 그 외 실패는 reject. */
async function geocodeViaKakaoJs(query: string): Promise<GeocodeResult[]> {
  const kakao = await loadKakaoMaps();
  const geocoder = new kakao.maps.services.Geocoder();
  return new Promise<GeocodeResult[]>((resolve, reject) => {
    geocoder.addressSearch(query, (data, status) => {
      if (status === "ZERO_RESULT") {
        resolve([]);
        return;
      }
      if (status !== "OK" || !Array.isArray(data)) {
        reject(new Error("주소 검색 실패"));
        return;
      }
      resolve(
        data.map((d) => ({
          address: d.address_name,
          lat: Number(d.y),
          lng: Number(d.x),
          admin_dong_code: d.address?.b_code || d.road_address?.b_code || "",
        })),
      );
    });
  });
}

function RoomFormInner({
  initial,
  pendingSignup,
}: {
  initial: ProviderRoomDetail | null;
  // 가입 대기 정보(provider 신규 가입 플로우). 있으면 "등록하기"가 회원가입→룸 생성을 함께 수행한다.
  pendingSignup: PendingSignup | null;
}) {
  const router = useRouter();
  const geocode = useGeocode();
  const save = useSaveRoom(initial?.room_id ?? null);
  const register = useRegister();

  const [name, setName] = useState(initial?.name ?? "");
  // 신규 등록은 빈 값 + placeholder(기본값을 미리 넣지 않는다 — KTH 2026-06-19). 수정은 기존값 prefill.
  const [capacity, setCapacity] = useState(initial ? String(initial.capacity) : "");
  const [price, setPrice] = useState(initial ? String(initial.price_per_hour) : "");
  const [roomType, setRoomType] = useState<string>(initial?.room_type ?? "open");
  const [amenities, setAmenities] = useState<Set<string>>(
    new Set(initial?.amenities ?? ["wifi"]),
  );
  const [hours, setHours] = useState<DayHours[]>(() => initialHours(initial));

  // 주소(지오코딩으로 확정) — 좌표·지역은 사용자가 직접 못 넣고 검색 결과 선택으로만 채운다.
  const [query, setQuery] = useState(initial?.address ?? "");
  const [results, setResults] = useState<GeocodeResult[]>([]);
  // 검색은 됐으나 등록 가능한(지역 코드 보유) 결과가 없을 때 안내 — 도로명만(번지 없이) 입력하면
  // b_code가 없어 등록 불가하므로 번지 포함 주소를 유도한다.
  const [noUsable, setNoUsable] = useState(false);
  // 카카오 결과가 0건(주소를 못 찾음 — 상호명·오타 등)일 때 안내. noUsable(결과는 있으나 등록불가)과 구분.
  const [noResults, setNoResults] = useState(false);
  const [picked, setPicked] = useState<GeocodeResult | null>(
    initial
      ? {
          address: initial.address ?? "",
          lat: initial.lat,
          lng: initial.lng,
          admin_dong_code: initial.admin_dong_code,
        }
      : null,
  );
  const [formError, setFormError] = useState<string | null>(null);
  // 주소 검색 로딩/실패 — 백엔드(로그인 provider)·JS Geocoder(가입 전) 두 경로 공통 상태.
  const [searching, setSearching] = useState(false);
  const [searchFailed, setSearchFailed] = useState(false);

  function toggleAmenity(code: string) {
    setAmenities((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  function setDay(i: number, patch: Partial<DayHours>) {
    setHours((prev) => prev.map((d, idx) => (idx === i ? { ...d, ...patch } : d)));
  }

  async function runGeocode() {
    if (!query.trim() || searching) return;
    // 새 검색마다 이전 결과·안내를 먼저 비운다(다른 주소로 재검색 시 옛 후보가 남는 문제 방지).
    setResults([]);
    setNoUsable(false);
    setNoResults(false);
    setSearchFailed(false);
    setSearching(true);
    try {
      // 가입 전(pendingSignup)이면 미인증이라 백엔드 geocode(provider 전용)를 못 쓴다 → 프론트 JS
      // Geocoder 로 직접. 로그인 provider 는 기존 백엔드 프록시(REST 키)를 쓴다(결과 형상 동일).
      const all = pendingSignup
        ? await geocodeViaKakaoJs(query.trim())
        : await geocode.mutateAsync(query.trim());
      // 등록에는 지역 코드가 필수다 — 도로명만(번지 없는) 결과는 b_code가 비어 저장 시 422가 되므로
      // 선택지에서 거른다. 0건(못 찾음)과 "결과는 있으나 등록불가(지역·도로명only)"를 구분해 안내한다.
      const usable = all.filter((r) => r.admin_dong_code);
      setResults(usable);
      setNoResults(all.length === 0);
      setNoUsable(all.length > 0 && usable.length === 0);
      // 선택 가능한 결과가 하나도 없으면(0건·등록불가) 이전 선택 주소와 미니맵까지 지운다 — 재검색
      // 결과가 없는데 직전 선택·지도가 남아 혼란을 주지 않도록(KTH 2026-06-19).
      if (usable.length === 0) {
        setPicked(null);
      }
    } catch {
      setSearchFailed(true);
    } finally {
      setSearching(false);
    }
  }

  function submit() {
    setFormError(null);
    // 필수: 이름·주소·수용인원·시간당 금액·룸형태·영업시간 1개 이상(KTH 2026-06-19).
    if (!name.trim()) {
      setFormError("스터디룸 이름을 입력해 주세요.");
      return;
    }
    if (!picked) {
      setFormError("주소를 검색해 선택해 주세요.");
      return;
    }
    const capacityNum = Number(capacity);
    if (!capacity.trim() || !Number.isInteger(capacityNum) || capacityNum < 1) {
      setFormError("수용 인원을 1명 이상 입력해 주세요.");
      return;
    }
    const priceNum = Number(price);
    if (!price.trim() || !Number.isInteger(priceNum) || priceNum < 0) {
      setFormError("시간당 금액을 0원 이상 정수로 입력해 주세요.");
      return;
    }
    if (!roomType) {
      setFormError("룸 형태를 선택해 주세요.");
      return;
    }
    const businessHours = hours
      .map((d, weekday) => ({ d, weekday }))
      .filter(({ d }) => d.on)
      .map(({ d, weekday }) => ({
        weekday,
        open_time: `${d.open}:00`,
        close_time: `${d.close}:00`,
      }));
    if (businessHours.length === 0) {
      setFormError("영업하는 요일을 하나 이상 선택해 주세요.");
      return;
    }
    if (businessHours.some((b) => b.close_time <= b.open_time)) {
      setFormError("영업 종료 시각은 시작 시각보다 늦어야 해요.");
      return;
    }
    const payload: RoomCreateRequest = {
      name: name.trim(),
      price_per_hour: Number(price),
      capacity: Number(capacity),
      room_type: roomType as RoomCreateRequest["room_type"],
      amenities: [...amenities] as RoomCreateRequest["amenities"],
      lat: picked.lat,
      lng: picked.lng,
      admin_dong_code: picked.admin_dong_code,
      address: picked.address,
      business_hours: businessHours,
    };
    const goProvider = () => {
      router.replace("/provider");
      router.refresh();
    };
    if (pendingSignup) {
      // 가입 대기 모드: 회원가입(→자동 로그인) 성공 후에만 룸을 생성한다(가입+등록 원자 처리).
      // 가입 실패(이메일 중복 등)면 룸을 만들지 않고 에러만 노출한다 — 떠도는 계정/룸이 안 생긴다.
      register.mutate(
        { email: pendingSignup.email, password: pendingSignup.password, role: "provider" },
        {
          onSuccess: () => {
            save.mutate(payload, {
              onSuccess: () => {
                clearPendingSignup();
                goProvider();
              },
            });
          },
        },
      );
      return;
    }
    save.mutate(payload, { onSuccess: goProvider });
  }

  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-6 py-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold leading-[1.4] tracking-[-0.01em]">
          {initial ? "스터디룸 수정" : "스터디룸 등록"}
        </h1>
        <p className="text-sm leading-[1.6] text-muted-foreground">
          MVP에서는 제공자당 한 개의 스터디룸을 등록할 수 있어요.
        </p>
        {pendingSignup ? (
          <p className="text-xs font-semibold leading-[1.6] text-destructive">
            이 정보를 등록하면 회원가입이 함께 완료돼요.
          </p>
        ) : null}
      </div>

      <div className="flex flex-col gap-5">
        {/* 이름 */}
        <label className="flex flex-col gap-1.5">
          <FieldLabel>스터디룸 이름</FieldLabel>
          <input
            className={inputClass}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="예: 미사 스터디카페 A룸"
          />
        </label>

        {/* 주소 검색 */}
        <div className="flex flex-col gap-1.5">
          {/* 라벨 + 빨간 안내(온보딩 톤) — 모바일 고려 요점만. 부정확 주소는 지도 핀이 안 잡힘. */}
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <FieldLabel>주소</FieldLabel>
            <span className="text-xs font-semibold leading-[1.6] text-destructive">
              정확하지 않으면 지도에 안 보여요
            </span>
          </div>
          <div className="flex gap-2">
            <input
              className={inputClass}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void runGeocode();
                }
              }}
              placeholder="도로명·지번 주소 검색"
            />
            <Button
              type="button"
              variant="outline"
              onClick={runGeocode}
              disabled={searching}
              className="h-11 shrink-0 gap-1"
            >
              <Search className="size-4" aria-hidden />
              {searching ? "검색 중" : "검색"}
            </Button>
          </div>
          {/* 선택된 주소 + 위치 미니 지도(상세 RoomLocationMap 재사용) — 입력 좌표를 눈으로 확인. */}
          {picked ? (
            <div className="flex flex-col gap-2">
              <p className="flex items-start gap-1.5 text-sm leading-[1.6] text-foreground">
                <MapPin className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                <span>{picked.address}</span>
              </p>
              <RoomLocationMap lat={picked.lat} lng={picked.lng} name={picked.address} />
            </div>
          ) : null}
          {/* 검색 결과 후보 — 하단에 나오므로 "선택하라"고 명시해 인지시킨다. */}
          {results.length > 0 ? (
            <div className="flex flex-col gap-1.5">
              <p className="text-sm leading-[1.6] text-muted-foreground">
                검색된 주소예요. 아래에서 정확한 주소를 선택해 주세요.
              </p>
              <ul className="flex flex-col divide-y divide-border rounded-md border border-border">
                {results.map((r) => (
                  <li key={`${r.lat},${r.lng},${r.address}`}>
                    <button
                      type="button"
                      onClick={() => {
                        setPicked(r);
                        setQuery(r.address);
                        setResults([]);
                        setNoUsable(false);
                        setNoResults(false);
                      }}
                      className="flex w-full items-start gap-1.5 px-3 py-2 text-left text-sm hover:bg-muted"
                    >
                      <MapPin className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                      <span>{r.address}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {/* 결과 0건(못 찾음) — 상호명·오타 등. 지번/도로명 주소로 유도. */}
          {noResults ? (
            <p className="text-sm leading-[1.6] text-muted-foreground">
              검색 결과가 없어요. 지번 또는 도로명 주소(번지 포함)로 다시 검색해 주세요.
            </p>
          ) : null}
          {noUsable ? (
            <p className="text-sm leading-[1.6] text-muted-foreground">
              번지까지 포함한 구체적인 주소로 검색해 주세요(도로명만으로는 등록할 수 없어요).
            </p>
          ) : null}
          {searchFailed ? (
            <p className="text-sm text-destructive">주소 검색에 실패했어요. 다시 시도해 주세요.</p>
          ) : null}
        </div>

        {/* 수용 인원 · 시간당 금액 */}
        <div className="flex gap-3">
          <label className="flex flex-1 flex-col gap-1.5">
            <FieldLabel>수용 인원</FieldLabel>
            <input
              className={inputClass}
              type="number"
              min={1}
              value={capacity}
              onChange={(e) => setCapacity(e.target.value)}
              placeholder="예: 4"
            />
          </label>
          <label className="flex flex-1 flex-col gap-1.5">
            <FieldLabel>시간당 금액(원)</FieldLabel>
            <input
              className={inputClass}
              type="number"
              min={0}
              step={1000}
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              placeholder="예: 10000"
            />
          </label>
        </div>

        {/* 룸 형태 */}
        <div className="flex flex-col gap-1.5">
          <FieldLabel>룸 형태</FieldLabel>
          <div className="flex gap-2">
            {ROOM_TYPES.map((t) => (
              <button
                key={t}
                type="button"
                aria-pressed={roomType === t}
                onClick={() => setRoomType(t)}
                className={`flex-1 rounded-md border px-3 py-2 text-sm font-medium ${
                  roomType === t
                    ? "border-primary bg-primary/10 text-foreground"
                    : "border-border bg-background text-muted-foreground hover:bg-muted"
                }`}
              >
                {ROOM_TYPE_LABELS[t]}
              </button>
            ))}
          </div>
        </div>

        {/* 부대시설 */}
        <div className="flex flex-col gap-1.5">
          <FieldLabel>부대시설</FieldLabel>
          <div className="flex flex-wrap gap-2">
            {AMENITY_CODES.map((code) => (
              <button
                key={code}
                type="button"
                aria-pressed={amenities.has(code)}
                onClick={() => toggleAmenity(code)}
                className={`rounded-full border px-3 py-1.5 text-sm ${
                  amenities.has(code)
                    ? "border-primary bg-primary/10 text-foreground"
                    : "border-border bg-background text-muted-foreground hover:bg-muted"
                }`}
              >
                {AMENITY_LABELS[code]}
              </button>
            ))}
          </div>
        </div>

        {/* 영업시간 */}
        <div className="flex flex-col gap-2">
          <FieldLabel>영업시간</FieldLabel>
          <ul className="flex flex-col gap-2">
            {hours.map((d, i) => (
              <li key={WEEKDAYS[i]} className="flex items-center gap-3">
                <label className="flex w-16 shrink-0 items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={d.on}
                    onChange={(e) => setDay(i, { on: e.target.checked })}
                    className="size-4 accent-primary"
                  />
                  <span className="text-sm">{WEEKDAYS[i]}</span>
                </label>
                {d.on ? (
                  <div className="flex items-center gap-1.5">
                    <input
                      type="time"
                      value={d.open}
                      onChange={(e) => setDay(i, { open: e.target.value })}
                      className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    />
                    <span className="text-muted-foreground">–</span>
                    <input
                      type="time"
                      value={d.close}
                      onChange={(e) => setDay(i, { close: e.target.value })}
                      className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    />
                  </div>
                ) : (
                  <span className="text-sm text-muted-foreground">휴무</span>
                )}
              </li>
            ))}
          </ul>
        </div>

        {formError || save.error || register.error ? (
          <p
            role="alert"
            className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm leading-[1.6] text-destructive"
          >
            {/* 우선순위: 클라 검증(formError) → 저장 실패(409=1룸 초과 등) → 가입 실패(pending 모드).
                pending 모드는 register→save 순차라 둘이 동시 에러일 일은 없다. */}
            {formError ??
              (save.error
                ? saveRoomErrorCopy(save.error.failure)
                : register.error
                  ? registerErrorCopy(register.error.failure)
                  : "저장에 실패했어요. 입력값을 확인하고 다시 시도해 주세요.")}
          </p>
        ) : null}

        <Button
          type="button"
          size="lg"
          onClick={submit}
          disabled={save.isPending || register.isPending}
          className="w-full"
        >
          {save.isPending || register.isPending
            ? "처리 중…"
            : pendingSignup
              ? "가입하고 등록하기"
              : initial
                ? "수정 저장"
                : "등록하기"}
        </Button>
      </div>
    </div>
  );
}

/** 가입 대기(provider 신규) vs 로그인된 provider 분기. */
export function RoomForm() {
  // mount 시 1회 캡처 — 가입 대기 정보가 있으면 아직 미로그인이므로 useMyRoom(401)을 호출하지 않고
  // 곧장 생성 폼을 띄운다. full 새로고침이면 pending 이 사라져 ExistingRoomForm 경로로 가며, 이때
  // 미로그인이면 "불러오지 못했어요"가 뜬다(가입을 다시 진행해야 함 — 메모리 보관의 한계).
  const [pending] = useState(() => getPendingSignup());
  if (pending) {
    return <RoomFormInner initial={null} pendingSignup={pending} />;
  }
  return <ExistingRoomForm />;
}

/** 로그인된 provider — 내 룸 로드 후 prefill로 렌더(생성/수정 분기). 로드 전엔 스켈레톤. */
function ExistingRoomForm() {
  const { data, isLoading, isError } = useMyRoom();

  if (isLoading) {
    return (
      <p className="mx-auto w-full max-w-xl py-8 text-sm text-muted-foreground">
        불러오는 중…
      </p>
    );
  }
  if (isError) {
    return (
      <p className="mx-auto w-full max-w-xl py-8 text-sm text-pin-full">
        내 스터디룸 정보를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.
      </p>
    );
  }
  return <RoomFormInner initial={data ?? null} pendingSignup={null} />;
}
