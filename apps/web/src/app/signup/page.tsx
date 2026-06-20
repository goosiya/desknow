// 회원가입 페이지(/signup). 컨테이너(SignupView)가 폼·뮤테이션·라우팅을 담당한다.
//
// useSearchParams(?next=)는 클라이언트 훅이라 App Router에서 <Suspense> 경계가 필요하다.
import { Suspense } from "react";

import { SignupView } from "@/features/auth/SignupView";

export default function SignupPage() {
  return (
    <Suspense fallback={null}>
      <SignupView />
    </Suspense>
  );
}
