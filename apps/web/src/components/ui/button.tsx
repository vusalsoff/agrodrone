import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonStyles = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors duration-150 select-none disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "bg-emerald-500 text-zinc-950 hover:bg-emerald-400 shadow-[inset_0_1px_0_rgba(255,255,255,0.22)]",
        secondary:
          "bg-white/[0.06] text-zinc-100 border border-white/[0.09] hover:bg-white/[0.10] hover:border-white/[0.16]",
        outline:
          "bg-transparent text-zinc-200 border border-white/[0.12] hover:bg-white/[0.05] hover:border-emerald-500/40",
        ghost: "bg-transparent text-zinc-300 hover:bg-white/[0.06] hover:text-zinc-100",
        subtle:
          "bg-emerald-500/10 text-emerald-300 border border-emerald-500/25 hover:bg-emerald-500/18",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-9 px-3.5 text-sm",
        lg: "h-10 px-4 text-sm",
        icon: "h-8 w-8",
      },
    },
    defaultVariants: {
      variant: "secondary",
      size: "md",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonStyles> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Component = asChild ? Slot : "button";
    return (
      <Component
        ref={ref}
        className={cn(buttonStyles({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";
