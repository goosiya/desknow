// 카카오 지도 JS SDK 최소 ambient 타입 (Story 3.2).
//
// 공식 타입 패키지가 없으므로 **본 스토리가 실제로 쓰는 표면만** 선언한다(Map·LatLng·
// CustomOverlay·maps.load). SDK 는 `<script>` 주입 후 전역 `window.kakao` 로 노출된다.
// 핀은 색+아이콘 HTML 을 담기 위해 Marker 대신 CustomOverlay 로 렌더한다(접근성 라벨·
// 터치 타겟·아이콘을 마크업으로 직접 통제).

declare global {
  interface Window {
    kakao: typeof kakao;
  }

  namespace kakao.maps {
    /** autoload=false 일 때 SDK 초기화 완료 후 콜백을 호출한다. */
    function load(callback: () => void): void;

    class LatLng {
      constructor(lat: number, lng: number);
    }

    interface MapOptions {
      center: LatLng;
      level?: number;
    }

    class Map {
      constructor(container: HTMLElement, options: MapOptions);
      setCenter(latlng: LatLng): void;
      getCenter(): LatLng;
      setLevel(level: number): void;
      // 컨테이너 크기 변경(모바일 주소창 접힘·회전·동적 레이아웃) 후 내부 타일/좌표를 컨테이너에
      // 다시 맞춘다. 호출하지 않으면 지도가 일부 회색으로 남거나 드래그/탭 좌표가 어긋난다.
      relayout(): void;
    }

    interface CustomOverlayOptions {
      position: LatLng;
      content: HTMLElement | string;
      map?: Map;
      yAnchor?: number;
      xAnchor?: number;
      clickable?: boolean;
    }

    class CustomOverlay {
      constructor(options: CustomOverlayOptions);
      setMap(map: Map | null): void;
    }
  }

  // services 라이브러리(libraries=services) — 주소→좌표 Geocoder. provider 가입 전(미인증) 주소
  // 검색용(백엔드 /rooms/geocode 는 provider 전용). 본 앱이 쓰는 표면만 선언한다.
  namespace kakao.maps.services {
    // SDK 는 enum 객체를 주지만, 런타임 의존을 피하려 코드에선 문자열로 비교한다.
    type Status = "OK" | "ZERO_RESULT" | "ERROR";

    interface AddressResult {
      address_name: string;
      x: string; // 경도(lng)
      y: string; // 위도(lat)
      address: { b_code?: string } | null; // 지번 — b_code=지역 코드
      road_address: { b_code?: string } | null; // 도로명
    }

    class Geocoder {
      addressSearch(
        query: string,
        callback: (result: AddressResult[], status: Status) => void,
      ): void;
    }
  }
}

export {};
