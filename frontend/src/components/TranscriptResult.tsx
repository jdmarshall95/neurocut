import {
  ArrowDownTrayIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
} from "@heroicons/react/24/outline";
import { GlassCard } from "./ui/GlassCard";
import { Metric } from "./ui/Metric";
import { Button } from "./ui/Button";
import { Accordion } from "./ui/Accordion";
import { TranscriptView } from "./TranscriptView";
import {
  downloadTextFile,
  formatDuration,
  segmentsToPlainText,
  segmentsToSrt,
} from "../lib/format";
import type { TranscriptResult as TranscriptResultType } from "../lib/types";

interface TranscriptResultProps {
  result: TranscriptResultType;
}

export function TranscriptResult({ result }: TranscriptResultProps) {
  const segments = result.transcript;
  const shortId = result.job_id.slice(0, 8);

  const handleDownload = (kind: "txt" | "srt" | "json") => {
    if (kind === "txt") {
      downloadTextFile(`transcript_${shortId}.txt`, segmentsToPlainText(segments));
    } else if (kind === "srt") {
      downloadTextFile(
        `transcript_${shortId}.srt`,
        segmentsToSrt(segments),
        "application/x-subrip",
      );
    } else {
      downloadTextFile(
        `transcript_${shortId}.json`,
        JSON.stringify({ segments, language: result.language }, null, 2),
        "application/json",
      );
    }
  };

  return (
    <GlassCard tone="strong" className="space-y-6 p-6 animate-fade-in-up sm:p-8">
      <div className="flex items-center gap-3">
        <CheckCircleIcon className="h-7 w-7 text-emerald-400" />
        <div>
          <h3 className="text-lg font-bold text-slate-50">Transcript ready</h3>
          <p className="text-sm text-slate-400">
            {segments.length} {segments.length === 1 ? "segment" : "segments"}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric label="Job ID" value={`${shortId}…`} />
        <Metric label="Segments" value={segments.length} />
        <Metric label="Duration" value={formatDuration(result.duration)} />
        <Metric label="Language" value={(result.language || "—").toUpperCase()} />
      </div>

      {result.cached && (
        <div className="flex items-center gap-2 rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-4 py-3 text-sm text-cyan-200">
          <CheckCircleIcon className="h-5 w-5" />
          Transcript loaded from cache — this video was processed before.
        </div>
      )}

      {segments.length === 0 ? (
        <div className="flex items-center gap-2 rounded-2xl border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">
          <ExclamationTriangleIcon className="h-5 w-5" />
          No speech detected — the video has no recognizable audio track.
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <Button
              variant="outline"
              icon={<ArrowDownTrayIcon className="h-4 w-4" />}
              onClick={() => handleDownload("txt")}
            >
              Download TXT
            </Button>
            <Button
              variant="outline"
              icon={<ArrowDownTrayIcon className="h-4 w-4" />}
              onClick={() => handleDownload("srt")}
            >
              Download SRT
            </Button>
            <Button
              variant="outline"
              icon={<ArrowDownTrayIcon className="h-4 w-4" />}
              onClick={() => handleDownload("json")}
            >
              Download JSON
            </Button>
          </div>

          <Accordion title="Transcript" defaultOpen>
            <TranscriptView segments={segments} />
          </Accordion>
        </>
      )}
    </GlassCard>
  );
}
