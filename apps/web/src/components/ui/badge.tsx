import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeStyles = cva(
  "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-medium tracking-wide transition-colors",
  {
    variants: {
      tone: {
        emerald: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
        amber: "border-amber-500/30 bg-amber-500/10 text-amber-300",
        rose: "border-rose-500/30 bg-rose-500/10 text-rose-300",
        neutral: "border-white/[0.10] bg-white/[0.04] text-zinc-300",
        muted: "border-white/[0.07] bg-transparent text-zinc-400",
      },
    },
    defaultVariants: {
      tone: "neutral",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeStyles> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeStyles({ tone }), className)} {...props} />;
}
