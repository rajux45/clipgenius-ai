import { Sparkles } from "lucide-react";

export function Logo({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const cls = size === "lg" ? "text-2xl" : size === "sm" ? "text-base" : "text-xl";
  return (
    <div className={`flex items-center gap-2 font-semibold ${cls}`}>
      <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-accent2 text-white">
        <Sparkles size={16} />
      </span>
      <span className="bg-gradient-to-r from-white to-white/70 bg-clip-text text-transparent">
        ClipGenius<span className="text-accent">.ai</span>
      </span>
    </div>
  );
}
