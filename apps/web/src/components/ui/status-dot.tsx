import { cn } from "@/lib/utils";

export type DotTone = "emerald" | "amber" | "rose" | "neutral";

const DOT_COLOR: Record<DotTone, string> = {
  emerald: "bg-emerald-400",
  amber: "bg-amber-400",
  rose: "bg-rose-500",
  neutral: "bg-zinc-500",
};

export function StatusDot({
  tone,
  pulse = false,
  className,
}: {
  tone: DotTone;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("relative inline-flex h-2 w-2 shrink-0", className)} aria-hidden="true">
      {pulse && (
        <span
          className={cn(
            "absolute inline-flex h-full w-full animate-ping rounded-full opacity-55",
            DOT_COLOR[tone],
          )}
        />
      )}
      <span className={cn("relative inline-flex h-2 w-2 rounded-full", DOT_COLOR[tone])} />
    </span>
  );
}
