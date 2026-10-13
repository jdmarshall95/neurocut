import { formatTimestamp } from "../lib/format";
import type { TranscriptSegment } from "../lib/types";

interface TranscriptViewProps {
  segments: TranscriptSegment[];
}

export function TranscriptView({ segments }: TranscriptViewProps) {
  if (segments.length === 0) {
    return (
      <p className="text-sm text-slate-400">
        No speech detected. Visual scene timeline was used instead.
      </p>
    );
  }

  return (
    <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
      {segments.map((segment, index) => (
        <div
          key={index}
          className="flex gap-3 rounded-xl bg-white/[0.03] px-3 py-2 transition-colors hover:bg-white/[0.06]"
        >
          <span className="shrink-0 font-mono text-xs text-violet-300/80">
            {formatTimestamp(segment.start)}
          </span>
          <span className="text-sm leading-relaxed text-slate-200">
            {segment.text.trim()}
          </span>
        </div>
      ))}
    </div>
  );
}
