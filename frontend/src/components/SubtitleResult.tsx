import { ArrowDownTrayIcon, CheckCircleIcon } from "@heroicons/react/24/outline";
import { GlassCard } from "./ui/GlassCard";
import { Button } from "./ui/Button";
import { subtitledDownloadUrl } from "../lib/api";

interface SubtitleResultProps {
  jobId: string;
  version?: number;
}

export function SubtitleResult({ jobId, version }: SubtitleResultProps) {
  const url = subtitledDownloadUrl(jobId, version);
  return (
    <GlassCard tone="strong" className="space-y-6 p-6 animate-fade-in-up sm:p-8">
      <div className="flex items-center gap-3">
        <CheckCircleIcon className="h-7 w-7 text-emerald-400" />
        <div>
          <h3 className="text-lg font-bold text-slate-50">Subtitles burned in</h3>
          <p className="text-sm text-slate-400">
            Text is embedded in the video. Preview below and download the finished MP4.
          </p>
        </div>
      </div>

      <video
        key={url}
        src={url}
        controls
        className="w-full rounded-2xl border border-white/10 bg-black shadow-glass"
      />

      <a href={url} download className="block">
        <Button
          size="lg"
          className="w-full"
          icon={<ArrowDownTrayIcon className="h-5 w-5" />}
        >
          Download video with subtitles
        </Button>
      </a>
    </GlassCard>
  );
}
