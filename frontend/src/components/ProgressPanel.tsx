import { GlassCard } from "./ui/GlassCard";
import { Stepper } from "./Stepper";
import { ProgressBar } from "./ProgressBar";
import type { Step } from "../lib/types";

interface ProgressPanelProps {
  title: string;
  message: string;
  percent: number;
  steps: Step[];
  currentStage: string | null;
  failed?: boolean;
}

export function ProgressPanel({
  title,
  message,
  percent,
  steps,
  currentStage,
  failed,
}: ProgressPanelProps) {
  return (
    <GlassCard tone="strong" className="space-y-6 p-6 animate-fade-in-up sm:p-8">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-bold text-slate-50">{title}</h3>
          <p className="mt-1 text-sm text-slate-400">{message}</p>
        </div>
        <div className="text-right">
          <span className="text-3xl font-extrabold text-gradient tabular-nums">
            {Math.round(percent)}%
          </span>
        </div>
      </div>

      <ProgressBar percent={percent} failed={failed} />

      <Stepper steps={steps} currentStage={currentStage} failed={failed} />
    </GlassCard>
  );
}
