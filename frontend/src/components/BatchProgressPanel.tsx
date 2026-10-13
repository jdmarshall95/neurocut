import { FilmIcon } from "@heroicons/react/24/outline";
import clsx from "clsx";
import { GlassCard } from "./ui/GlassCard";
import { ProgressBar } from "./ProgressBar";
import type { BatchJobItem } from "../hooks/useJobRunner";

interface BatchProgressPanelProps {
  title: string;
  jobs: BatchJobItem[];
}

const PHASE_LABEL: Record<string, string> = {
  uploading: "Uploading",
  processing: "Processing",
  burning: "Burning subtitles",
  approval: "Awaiting review",
  done: "Done",
  error: "Error",
};

export function BatchProgressPanel({ title, jobs }: BatchProgressPanelProps) {
  const active = jobs.filter(
    (j) => j.phase === "uploading" || j.phase === "processing" || j.phase === "burning",
  );
  const done = jobs.filter((j) => j.phase === "done").length;
  const failed = jobs.filter((j) => j.phase === "error").length;
  const avgPercent =
    jobs.length > 0
      ? Math.round(jobs.reduce((sum, j) => sum + j.percent, 0) / jobs.length)
      : 0;

  return (
    <GlassCard tone="strong" className="space-y-6 p-6 animate-fade-in-up sm:p-8">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-bold text-slate-50">{title}</h3>
          <p className="mt-1 text-sm text-slate-400">
            {active.length > 0
              ? `In progress: ${active.length} of ${jobs.length}`
              : `Finished: ${done}${failed > 0 ? ` · failed: ${failed}` : ""}`}
          </p>
        </div>
        <div className="text-right">
          <span className="text-3xl font-extrabold text-gradient tabular-nums">
            {avgPercent}%
          </span>
        </div>
      </div>

      <ProgressBar percent={avgPercent} failed={failed > 0 && active.length === 0} />

      <div className="space-y-2">
        {jobs.map((job) => (
          <div
            key={job.clientId}
            className={clsx(
              "rounded-xl border px-4 py-3",
              job.phase === "error"
                ? "border-rose-400/20 bg-rose-500/10"
                : job.phase === "done"
                  ? "border-emerald-400/20 bg-emerald-500/10"
                  : "border-white/10 bg-white/[0.03]",
            )}
          >
            <div className="flex items-center gap-3">
              <FilmIcon className="h-5 w-5 shrink-0 text-slate-400" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold text-slate-100">
                  {job.fileName}
                </div>
                <div className="truncate text-xs text-slate-400">
                  {job.error ?? job.message}
                </div>
              </div>
              <div className="shrink-0 text-right">
                <div className="text-xs font-medium text-slate-300">
                  {PHASE_LABEL[job.phase] ?? job.phase}
                </div>
                <div className="text-sm font-bold tabular-nums text-slate-200">
                  {Math.round(job.percent)}%
                </div>
              </div>
            </div>
            {job.phase !== "done" && job.phase !== "error" && (
              <div className="mt-2">
                <ProgressBar percent={job.percent} />
              </div>
            )}
          </div>
        ))}
      </div>
    </GlassCard>
  );
}
