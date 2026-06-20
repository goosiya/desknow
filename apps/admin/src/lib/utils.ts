import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// shadcn 표준 className 병합 유틸(clsx + tailwind-merge).
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
