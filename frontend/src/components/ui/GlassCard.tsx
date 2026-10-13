import type { HTMLAttributes, ReactNode } from "react";
import clsx from "clsx";

interface GlassCardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  tone?: "default" | "strong" | "soft";
}

const tones = {
  default: "glass",
  strong: "glass-strong",
  soft: "glass-soft",
};

export function GlassCard({
  children,
  tone = "default",
  className,
  ...props
}: GlassCardProps) {
  return (
    <div className={clsx(tones[tone], "rounded-3xl", className)} {...props}>
      {children}
    </div>
  );
}
