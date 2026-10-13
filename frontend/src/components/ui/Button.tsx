import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import clsx from "clsx";

type Variant = "primary" | "ghost" | "outline";
type Size = "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

const base =
  "group relative inline-flex select-none items-center justify-center gap-2 rounded-2xl font-semibold transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950 disabled:cursor-not-allowed disabled:opacity-40";

const sizes: Record<Size, string> = {
  md: "px-4 py-2.5 text-sm",
  lg: "px-6 py-3.5 text-base",
};

const variants: Record<Variant, string> = {
  primary:
    "btn-gradient shadow-glow hover:shadow-[0_0_50px_-6px_rgba(139,92,246,0.7)] hover:-translate-y-0.5 active:translate-y-0",
  ghost: "text-slate-200 hover:bg-white/10",
  outline:
    "glass-soft text-slate-100 hover:bg-white/10 hover:border-white/20 hover:-translate-y-0.5 active:translate-y-0",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, icon, children, className, disabled, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={clsx(base, sizes[size], variants[variant], className)}
      {...props}
    >
      {loading ? (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
      ) : (
        icon
      )}
      <span className="relative z-10">{children}</span>
    </button>
  );
});
