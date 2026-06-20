// provider 랜딩(운영 진입점) — provider 웹 표면. 내 스터디룸/예약자 현황/후기로 안내한다.
import Link from "next/link";

const LINKS = [
  { href: "/provider/room", title: "내 스터디룸", desc: "스터디룸 정보를 등록하거나 수정해요." },
  { href: "/provider/reservations", title: "예약자 현황", desc: "들어온 예약을 확인하고 필요하면 거부해요." },
  { href: "/provider/reviews", title: "후기", desc: "후기를 보고 답글을 남겨요." },
];

export default function ProviderHomePage() {
  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-4 py-8">
      <h1 className="text-2xl font-bold leading-[1.4] tracking-[-0.01em]">스터디룸 운영</h1>
      <ul className="flex flex-col gap-3">
        {LINKS.map((l) => (
          <li key={l.href}>
            <Link
              href={l.href}
              className="flex flex-col gap-1 rounded-lg border border-border bg-card p-4 hover:bg-muted"
            >
              <span className="text-base font-semibold text-card-foreground">{l.title}</span>
              <span className="text-sm leading-[1.6] text-muted-foreground">{l.desc}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
