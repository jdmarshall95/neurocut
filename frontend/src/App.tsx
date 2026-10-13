import { useMemo, useState } from "react";
import {
  ArrowPathIcon,
  ExclamationTriangleIcon,
  PlayIcon,
} from "@heroicons/react/24/outline";
import { Background } from "./components/Background";
import { HealthBadge } from "./components/HealthBadge";
import { TaskSelector, TASKS } from "./components/TaskSelector";
import { FileDropzone } from "./components/FileDropzone";
import { PromptField } from "./components/PromptField";
import { ProgressPanel } from "./components/ProgressPanel";
import { BatchProgressPanel } from "./components/BatchProgressPanel";
import { TranscriptResult } from "./components/TranscriptResult";
import { EditResult } from "./components/EditResult";
import { SubtitleEditor } from "./components/SubtitleEditor";
import { SubtitleResult } from "./components/SubtitleResult";
import { GlassCard } from "./components/ui/GlassCard";
import { Button } from "./components/ui/Button";
import { useJobRunner } from "./hooks/useJobRunner";
import { buildPipelineSteps, SUBTITLE_STEPS, TRANSCRIBE_STEPS } from "./lib/steps";
import type { TaskId } from "./lib/types";

const TASK_BUTTON: Record<TaskId, string> = {
  transcribe: "Transcribe",
  render_clip: "Build clip",
  subtitles: "Recognize speech",
  cut_xml: "Edit to XML",
  cut_clips: "Edit and split",
};

const PROMPT_TASKS: TaskId[] = ["cut_xml", "cut_clips", "render_clip"];

function pluralizeVideos(n: number): string {
  return n === 1 ? "clip" : "clips";
}

export default function App() {
  const [task, setTask] = useState<TaskId>("render_clip");
  const [files, setFiles] = useState<File[]>([]);
  const [prompt, setPrompt] = useState("");
  const { state, run, burnSubtitles, reset } = useJobRunner();

  const { jobs } = state;
  const isBatch = jobs.length > 1;
  const primaryJob = jobs[0] ?? null;

  const busy = jobs.some(
    (j) =>
      j.phase === "uploading" || j.phase === "processing" || j.phase === "burning",
  );

  const hasStarted = jobs.length > 0;
  const allTerminal =
    hasStarted &&
    jobs.every(
      (j) => j.phase === "done" || j.phase === "error" || j.phase === "approval",
    );
  const anyApproval = jobs.some((j) => j.phase === "approval");
  const anyError = jobs.some((j) => j.phase === "error");

  const needsPrompt = PROMPT_TASKS.includes(task);
  const canRun = files.length > 0 && (!needsPrompt || prompt.trim().length > 0) && !busy;

  const steps = useMemo(() => {
    if (task === "transcribe") return TRANSCRIBE_STEPS;
    if (task === "subtitles") return SUBTITLE_STEPS;
    const exportMode =
      task === "cut_xml" ? "xml" : task === "render_clip" ? "render" : "clips";
    return buildPipelineSteps(exportMode);
  }, [task, jobs]);

  const handleRun = () => {
    if (files.length === 0) return;
    run(task, files, prompt.trim());
  };

  const handleReset = () => {
    reset();
    setFiles([]);
    setPrompt("");
  };

  const progressTitle =
    task === "transcribe"
      ? "Transcription"
      : task === "subtitles"
        ? "Subtitles"
        : "Video processing";

  const showProgress =
    hasStarted && (busy || (anyError && !allTerminal)) && !anyApproval;

  const runButtonLabel = (() => {
    if (busy) return "Processing…";
    if (files.length > 1) {
      const verb =
        task === "transcribe" || task === "subtitles"
          ? "Process"
          : TASK_BUTTON[task];
      return `${verb} ${files.length} ${pluralizeVideos(files.length)}`;
    }
    return TASK_BUTTON[task];
  })();

  return (
    <div className="relative min-h-screen">
      <Background />

      <div className="mx-auto flex min-h-screen max-w-5xl flex-col px-4 py-6 sm:px-6 sm:py-10">
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 via-violet-500 to-fuchsia-500 text-xl shadow-glow">
              🎬
            </div>
            <div>
              <h1 className="text-xl font-extrabold tracking-tight text-slate-50">
                Neuro<span className="text-gradient">Cut</span>
              </h1>
              <p className="text-xs text-slate-400">AI Video Editor Assistant</p>
            </div>
          </div>
          <HealthBadge />
        </header>

        <main className="mt-8 flex flex-1 flex-col gap-6">
          <section className="text-center">
            <h2 className="mx-auto max-w-2xl text-3xl font-extrabold leading-tight tracking-tight text-slate-50 sm:text-4xl">
              Upload video and get a{" "}
              <span className="text-gradient">finished result</span>
            </h2>
            <p className="mx-auto mt-3 max-w-xl text-sm text-slate-400">
              Turnkey clip, subtitles, transcript, or rough cut for Premiere /
              DaVinci — in one pass. You can upload multiple clips at once.
            </p>
          </section>

          <GlassCard className="space-y-6 p-6 sm:p-8">
            <div className="space-y-3">
              <label className="text-sm font-semibold text-slate-200">Task</label>
              <TaskSelector value={task} onChange={setTask} disabled={busy} />
              <p className="text-xs text-slate-400">
                {TASKS.find((t) => t.id === task)?.description}
              </p>
            </div>

            <FileDropzone files={files} onChange={setFiles} disabled={busy} />

            {needsPrompt && (
              <PromptField value={prompt} onChange={setPrompt} disabled={busy} />
            )}

            <div className="flex flex-col gap-3 sm:flex-row">
              <Button
                size="lg"
                className="flex-1"
                onClick={handleRun}
                disabled={!canRun}
                loading={busy}
                icon={<PlayIcon className="h-5 w-5" />}
              >
                {runButtonLabel}
              </Button>
              {hasStarted && (allTerminal || anyApproval) && (
                <Button
                  size="lg"
                  variant="outline"
                  onClick={handleReset}
                  icon={<ArrowPathIcon className="h-5 w-5" />}
                >
                  New task
                </Button>
              )}
            </div>
          </GlassCard>

          {showProgress && isBatch && (
            <BatchProgressPanel title={progressTitle} jobs={jobs} />
          )}

          {showProgress && !isBatch && primaryJob && (
            <ProgressPanel
              title={progressTitle}
              message={primaryJob.message}
              percent={primaryJob.percent}
              steps={steps}
              currentStage={primaryJob.stage}
              failed={primaryJob.phase === "error"}
            />
          )}

          {jobs
            .filter((j) => j.phase === "error" && j.error)
            .map((job) => (
              <GlassCard
                key={job.clientId}
                tone="soft"
                className="flex items-start gap-3 border-rose-400/20 bg-rose-500/10 p-5 animate-fade-in-up"
              >
                <ExclamationTriangleIcon className="h-6 w-6 shrink-0 text-rose-400" />
                <div>
                  <div className="font-semibold text-rose-100">
                    Error: {job.fileName}
                  </div>
                  <p className="mt-1 break-words text-sm text-rose-200/90">
                    {job.error}
                  </p>
                </div>
              </GlassCard>
            ))}

          {task === "subtitles" &&
            jobs
              .filter((j) => j.phase === "approval" && j.transcriptResult && j.jobId)
              .map((job) => (
                <SubtitleEditor
                  key={job.clientId}
                  jobId={job.jobId as string}
                  transcript={job.transcriptResult as NonNullable<typeof job.transcriptResult>}
                  busy={job.phase === "burning"}
                  onConfirm={(segments, options) =>
                    burnSubtitles(job.clientId, segments, options)
                  }
                />
              ))}

          {task === "subtitles" &&
            jobs
              .filter((j) => j.subtitledReady && j.jobId)
              .map((job) => (
                <div key={job.clientId} className="space-y-2">
                  {isBatch && (
                    <h3 className="px-1 text-sm font-semibold text-slate-300">
                      {job.fileName}
                    </h3>
                  )}
                  <SubtitleResult
                    jobId={job.jobId as string}
                    version={job.subtitledVersion}
                  />
                </div>
              ))}

          {task === "transcribe" &&
            jobs
              .filter((j) => j.phase === "done" && j.transcriptResult)
              .map((job) => (
                <div key={job.clientId} className="space-y-2">
                  {isBatch && (
                    <h3 className="px-1 text-sm font-semibold text-slate-300">
                      {job.fileName}
                    </h3>
                  )}
                  <TranscriptResult result={job.transcriptResult!} />
                </div>
              ))}

          {jobs
            .filter((j) => j.phase === "done" && j.editResult && j.exportMode)
            .map((job) => (
              <div key={job.clientId} className="space-y-2">
                {isBatch && (
                  <h3 className="px-1 text-sm font-semibold text-slate-300">
                    {job.fileName}
                  </h3>
                )}
                <EditResult
                  result={job.editResult!}
                  exportMode={job.exportMode!}
                />
              </div>
            ))}
        </main>

        <footer className="mt-10 flex flex-col items-center gap-1 text-center text-xs text-slate-500">
          <p>
            Silent video automatically uses visual scene analysis. Processing is
            CPU-intensive — longer clips take more time.
          </p>
          <p className="text-slate-600">NeuroCut · FastAPI · Gemini · FFmpeg</p>
        </footer>
      </div>
    </div>
  );
}
