import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const SUPPORTED_LANGUAGES: { code: string; label: string }[] = [
  { code: "en", label: "English" },
  { code: "es", label: "Spanish" },
  { code: "hi", label: "Hindi" },
  { code: "fr", label: "French" },
  { code: "de", label: "German" },
  { code: "pt", label: "Portuguese" },
  { code: "ja", label: "Japanese" },
  { code: "ko", label: "Korean" },
  { code: "ar", label: "Arabic" },
  { code: "id", label: "Indonesian" },
];

export function fmtDuration(s: number | null | undefined): string {
  if (s == null || isNaN(s)) return "—";
  const total = Math.round(s);
  const m = Math.floor(total / 60);
  const r = total % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

export function statusColor(status: string): string {
  switch (status) {
    case "completed":
    case "ready":
    case "published":
      return "bg-success/15 text-success";
    case "failed":
      return "bg-danger/15 text-danger";
    case "publishing":
    case "rendering":
    case "dubbing":
    case "generating_clips":
    case "transcribing":
    case "downloading":
    case "segmenting":
      return "bg-accent/15 text-accent";
    default:
      return "bg-panel2 text-muted";
  }
}
