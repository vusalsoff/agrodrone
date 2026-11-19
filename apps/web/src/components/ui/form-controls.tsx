import * as React from "react";

import { cn } from "@/lib/utils";

const baseInputClass =
  "w-full rounded-lg border border-white/[0.10] bg-[#090D0B] px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 transition-colors focus:border-emerald-500/50 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50";

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <input ref={ref} className={cn(baseInputClass, "h-9", className)} {...props} />
));
Input.displayName = "Input";

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea ref={ref} className={cn(baseInputClass, "min-h-[84px] resize-y", className)} {...props} />
));
Textarea.displayName = "Textarea";

export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <select ref={ref} className={cn(baseInputClass, "h-9 cursor-pointer", className)} {...props}>
    {children}
  </select>
));
Select.displayName = "Select";

export function FieldLabel({
  htmlFor,
  required,
  children,
}: {
  htmlFor?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label
      htmlFor={htmlFor}
      className="mb-1.5 block text-xs font-medium text-zinc-300"
    >
      {children}
      {required && <span className="ml-1 text-emerald-400" aria-hidden="true">*</span>}
    </label>
  );
}

export function FormError({ message }: { message: string | null | undefined }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="rounded-lg border border-rose-500/30 bg-rose-500/[0.08] px-3.5 py-2.5 text-xs text-rose-200"
    >
      {message}
    </div>
  );
}
