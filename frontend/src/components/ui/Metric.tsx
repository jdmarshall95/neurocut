import type { ReactNode } from "react";

interface MetricProps {
  label: string;
  value: ReactNode;
}

export function Metric({ label, value }: MetricProps) {
  return (
    <div className="glass-soft rounded-2xl px-4 py-3">
      <div className="text-[0.68rem] font-medium uppercase tracking-wider text-slate-400">
        {label}
      </div>
      <div className="mt-1 truncate text-lg font-bold text-slate-50">{value}</div>
    </div>
  );
}
