import {
  ArrowDownTrayIcon,
  CheckCircleIcon,
  EyeIcon,
  ScissorsIcon,
} from "@heroicons/react/24/outline";
import { GlassCard } from "./ui/GlassCard";
import { Metric } from "./ui/Metric";
import { Button } from "./ui/Button";
import { Accordion } from "./ui/Accordion";
import { TranscriptView } from "./TranscriptView";
import { downloadUrl } from "../lib/api";
import { formatDuration, formatTimestamp } from "../lib/format";
import type { ExportMode, JobResult } from "../lib/types";

interface EditResultProps {
  result: JobResult;
  exportMode: ExportMode;
}

const SUCCESS_TEXT: Record<ExportMode, string> = {
  xml: "ZIP with XML and source video is ready. Unpack the archive and import the XML — media will relink automatically.",
  clips:
    "Clips are ready. Unpack the ZIP and import the MP4s into CapCut, InShot, or another mobile editor.",
  render:
    "Your clip is stitched and ready. Preview below and download the MP4 — publish as-is.",
};

const DOWNLOAD_LABEL: Record<ExportMode, string> = {
  xml: "Download ZIP (XML + video)",
  clips: "Download ZIP of clips",
  render: "Download finished MP4",
};

export function EditResult({ result, exportMode }: EditResultProps) {
  const shortId = result.job_id.slice(0, 8);
  const isVisual = result.analysis_mode === "visual";
  const title = exportMode === "render" ? "Turnkey clip ready" : "Edit ready";

  return (
    <GlassCard tone="strong" className="space-y-6 p-6 animate-fade-in-up sm:p-8">
      <div className="flex items-center gap-3">
        <CheckCircleIcon className="h-7 w-7 text-emerald-400" />
        <div>
          <h3 className="text-lg font-bold text-slate-50">{title}</h3>
          <p className="text-sm text-slate-400">{SUCCESS_TEXT[exportMode]}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-5">
        <Metric label="Job ID" value={`${shortId}…`} />
        <Metric label="Clips" value={result.clip_count} />
        <Metric label="Markers" value={result.marker_count} />
        <Metric label="Duration" value={formatDuration(result.duration)} />
        {exportMode === "xml" ? (
          <Metric label="FPS" value={result.fps ? result.fps.toFixed(2) : "—"} />
        ) : (
          <Metric label="Mode" value={result.analysis_mode || "clips"} />
        )}
      </div>

      {isVisual && (
        <div className="flex items-center gap-2 rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-4 py-3 text-sm text-cyan-200">
          <EyeIcon className="h-5 w-5" />
          No speech in video: edit was built from visual analysis and scene detection.
        </div>
      )}

      {exportMode === "render" && (
        <video
          key={downloadUrl(result.job_id, "render")}
          src={downloadUrl(result.job_id, "render")}
          controls
          className="w-full rounded-2xl border border-white/10 bg-black shadow-glass"
        />
      )}

      <a href={downloadUrl(result.job_id, exportMode)} download className="block">
        <Button
          size="lg"
          className="w-full"
          icon={<ArrowDownTrayIcon className="h-5 w-5" />}
        >
          {DOWNLOAD_LABEL[exportMode]}
        </Button>
      </a>

      <div className="space-y-3">
        <Accordion
          title="Edit plan"
          defaultOpen
          badge={
            <span className="flex items-center gap-1 rounded-full bg-violet-500/20 px-2 py-0.5 text-xs font-medium text-violet-200">
              <ScissorsIcon className="h-3.5 w-3.5" />
              {result.edit_plan.clips.length}
            </span>
          }
        >
          <div className="space-y-2">
            {result.edit_plan.clips.map((clip, index) => (
              <div
                key={index}
                className="rounded-xl bg-white/[0.03] px-3 py-2.5 transition-colors hover:bg-white/[0.06]"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="font-mono text-xs text-violet-300/80">
                    {formatTimestamp(clip.start_sec)} → {formatTimestamp(clip.end_sec)}
                  </span>
                  <span className="rounded-full bg-white/5 px-2 py-0.5 text-[0.68rem] font-medium text-slate-400">
                    track {clip.track}
                  </span>
                </div>
                <p className="mt-1 text-sm text-slate-300">{clip.reason}</p>
              </div>
            ))}
          </div>
        </Accordion>

        {result.edit_plan.markers.length > 0 && (
          <Accordion title={`Markers (${result.edit_plan.markers.length})`}>
            <div className="space-y-2">
              {result.edit_plan.markers.map((marker, index) => (
                <div key={index} className="flex gap-3 rounded-xl bg-white/[0.03] px-3 py-2">
                  <span className="shrink-0 font-mono text-xs text-fuchsia-300/80">
                    {formatTimestamp(marker.time_sec)}
                  </span>
                  <span className="text-sm text-slate-300">{marker.comment}</span>
                </div>
              ))}
            </div>
          </Accordion>
        )}

        <Accordion title="Transcript">
          <TranscriptView segments={result.transcript} />
        </Accordion>

        <Accordion title="How to use">
          {exportMode === "xml" ? (
            <ol className="list-decimal space-y-1.5 pl-5 text-sm text-slate-300">
              <li>Download and unpack the ZIP.</li>
              <li>The folder contains the XML and the source video file.</li>
              <li>Import the XML into Premiere Pro or DaVinci Resolve.</li>
              <li>
                If you use your own local file — place the XML next to it (the filename
                must match what the project references).
              </li>
            </ol>
          ) : exportMode === "render" ? (
            <ol className="list-decimal space-y-1.5 pl-5 text-sm text-slate-300">
              <li>Watch the preview above — that is the final stitched clip.</li>
              <li>Download the MP4 with one click.</li>
              <li>Publish as-is or polish in any editor.</li>
            </ol>
          ) : (
            <ol className="list-decimal space-y-1.5 pl-5 text-sm text-slate-300">
              <li>Download and unpack the ZIP.</li>
              <li>
                Inside — numbered MP4s and <code>manifest.json</code> with timecodes and
                reasons.
              </li>
              <li>Import the clips into a mobile editor in order.</li>
            </ol>
          )}
        </Accordion>
      </div>
    </GlassCard>
  );
}
