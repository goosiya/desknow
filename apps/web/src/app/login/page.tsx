// 로그인 페이지(/login). 컨테이너(LoginView)가 폼·뮤테이션·라우팅을 담당한다.
//
// useSearchParams(?next=)는 클라이언트 훅이라 App Router에서 <Suspense> 경계가 필요하다
// (Next 빌드 가드 — CSR bailout). 셸·제목은 LoginView 내부 카드가 처리한다.
import { Suspense } from "react";

import { LoginView } from "@/features/auth/LoginView";

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginView />
    </Suspense>
  );
}
