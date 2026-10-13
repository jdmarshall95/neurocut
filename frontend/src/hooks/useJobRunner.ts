import { useCallback, useRef, useState } from "react";
import {
  ApiError,
  getJobResult,
  getPipelineStatus,
  getSubtitleStatus,
  getTranscript,
  getTranscriptionStatus,
  startGenerate,
  startSubtitleRender,
  startTranscribe,
  type SubtitleBurnOptions,
} from "../lib/api";
import {
  nextPollIntervalMs,
  POLL_MIN_MS,
  isRetryableStatus,
} from "../lib/polling";
import type {
  EditableSegment,
  ExportMode,
  JobResult,
  TaskId,
  TranscriptResult,
} from "../lib/types";

const WAIT_TIMEOUT_MS = 30_000;
const POLL_NETWORK_RETRIES = 4;

export type RunPhase =
  | "idle"
  | "uploading"
  | "processing"
  | "approval"
  | "burning"
  | "done"
  | "error";

export interface BatchJobItem {
  clientId: string;
  fileName: string;
  jobId: string | null;
  phase: RunPhase;
  stage: string | null;
  message: string;
  percent: number;
  includeVisual: boolean;
  error: string | null;
  editResult: JobResult | null;
  transcriptResult: TranscriptResult | null;
  exportMode: ExportMode | null;
  subtitledReady: boolean;
  subtitledVersion: number;
}

export interface RunnerState {
  jobs: BatchJobItem[];
}

const INITIAL: RunnerState = { jobs: [] };

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function fetchWithRetry<T>(
  fetcher: () => Promise<T | null>,
  onRetry: (attempt: number, error: unknown) => void,
): Promise<T | null> {
  let interval = POLL_MIN_MS;
  for (let attempt = 0; attempt <= POLL_NETWORK_RETRIES; attempt++) {
    try {
      return await fetcher();
    } catch (error) {
      const retryable =
        error instanceof ApiError && isRetryableStatus(error.status);
      if (!retryable || attempt >= POLL_NETWORK_RETRIES) {
        throw error;
      }
      onRetry(attempt + 1, error);
      interval = nextPollIntervalMs(interval, false);
      await sleep(interval);
    }
  }
  return null;
}

function newJobItem(file: File): BatchJobItem {
  return {
    clientId: crypto.randomUUID(),
    fileName: file.name,
    jobId: null,
    phase: "uploading",
    stage: null,
    message: "Uploading to server…",
    percent: 0,
    includeVisual: false,
    error: null,
    editResult: null,
    transcriptResult: null,
    exportMode: null,
    subtitledReady: false,
    subtitledVersion: 0,
  };
}

export function useJobRunner() {
  const [state, setState] = useState<RunnerState>(INITIAL);
  const cancelledRef = useRef(false);

  const patchJob = useCallback(
    (clientId: string, partial: Partial<BatchJobItem>) => {
      setState((prev) => ({
        jobs: prev.jobs.map((job) =>
          job.clientId === clientId ? { ...job, ...partial } : job,
        ),
      }));
    },
    [],
  );

  const reset = useCallback(() => {
    cancelledRef.current = true;
    setState(INITIAL);
  }, []);

  const pollPipeline = useCallback(
    async (clientId: string, jobId: string) => {
      let waitStart = Date.now();
      let includeVisual = false;
      let interval = POLL_MIN_MS;
      let lastStage: string | null = null;

      while (!cancelledRef.current) {
        const status = await fetchWithRetry(
          () => getPipelineStatus(jobId),
          (attempt) => {
            patchJob(clientId, {
              message: `Server busy, retrying poll (${attempt}/${POLL_NETWORK_RETRIES})…`,
            });
          },
        );
        if (status === null) {
          if (Date.now() - waitStart > WAIT_TIMEOUT_MS) {
            throw new ApiError("Job not found on server.", 404);
          }
          patchJob(clientId, { message: "Waiting for pipeline to start…" });
          await sleep(interval);
          continue;
        }
        waitStart = Date.now();

        const p = status.pipeline;
        if (p.analysis_mode === "visual" || p.stage === "analyzing_scenes") {
          includeVisual = true;
        }
        const stageChanged = p.stage !== lastStage;
        lastStage = p.stage;
        interval = nextPollIntervalMs(interval, stageChanged);

        patchJob(clientId, {
          stage: p.stage,
          message: p.message || "Processing…",
          percent: p.progress_percent || 0,
          includeVisual,
        });

        if (p.stage === "completed") break;
        if (p.stage === "failed") {
          throw new Error(p.error || "Pipeline failed.");
        }
        await sleep(interval);
      }
    },
    [patchJob],
  );

  const pollTranscription = useCallback(
    async (clientId: string, jobId: string) => {
      let waitStart = Date.now();
      let interval = POLL_MIN_MS;
      let lastStage: string | null = null;

      while (!cancelledRef.current) {
        const status = await fetchWithRetry(
          () => getTranscriptionStatus(jobId),
          (attempt) => {
            patchJob(clientId, {
              message: `Server busy, retrying poll (${attempt}/${POLL_NETWORK_RETRIES})…`,
            });
          },
        );
        if (status === null) {
          if (Date.now() - waitStart > WAIT_TIMEOUT_MS) {
            throw new ApiError("Job not found on server.", 404);
          }
          patchJob(clientId, { message: "Waiting for transcription to start…" });
          await sleep(interval);
          continue;
        }
        waitStart = Date.now();

        const stageChanged = status.status !== lastStage;
        lastStage = status.status;
        interval = nextPollIntervalMs(interval, stageChanged);

        patchJob(clientId, {
          stage: status.status,
          message: status.message || "Transcribing…",
          percent: status.progress_percent || 0,
        });

        if (status.status === "completed") break;
        if (status.status === "failed") {
          throw new Error(status.error || "Transcription failed.");
        }
        await sleep(interval);
      }
    },
    [patchJob],
  );

  const processGenerate = useCallback(
    async (
      clientId: string,
      files: File[],
      prompt: string,
      exportMode: ExportMode,
    ) => {
      try {
        patchJob(clientId, {
          phase: "uploading",
          message:
            files.length > 1
              ? `Uploading ${files.length} clips and editing brief to server…`
              : "Uploading video and editing brief to server…",
          exportMode,
          error: null,
        });

        const jobId = await startGenerate(files, prompt, exportMode);
        patchJob(clientId, {
          jobId,
          phase: "processing",
          message: "Job created. Processing…",
        });

        await pollPipeline(clientId, jobId);
        if (cancelledRef.current) return;

        const result = await getJobResult(jobId);
        patchJob(clientId, {
          phase: "done",
          stage: "completed",
          percent: 100,
          message: "Done",
          editResult: result,
        });
      } catch (error) {
        if (cancelledRef.current) return;
        patchJob(clientId, {
          phase: "error",
          error: error instanceof Error ? error.message : String(error),
        });
      }
    },
    [patchJob, pollPipeline],
  );

  const processTranscribe = useCallback(
    async (
      clientId: string,
      file: File,
      { approval = false }: { approval?: boolean } = {},
    ) => {
      try {
        patchJob(clientId, {
          phase: "uploading",
          message: "Uploading video to server…",
          error: null,
        });

        const jobId = await startTranscribe(file);
        patchJob(clientId, {
          jobId,
          phase: "processing",
          message: "Job created. Transcribing…",
        });

        await pollTranscription(clientId, jobId);
        if (cancelledRef.current) return;

        const transcript = await getTranscript(jobId);
        patchJob(clientId, {
          phase: approval ? "approval" : "done",
          stage: approval ? "approval" : "completed",
          percent: approval ? 60 : 100,
          message: approval ? "Review and approve the text" : "Done",
          transcriptResult: transcript,
        });
      } catch (error) {
        if (cancelledRef.current) return;
        patchJob(clientId, {
          phase: "error",
          error: error instanceof Error ? error.message : String(error),
        });
      }
    },
    [patchJob, pollTranscription],
  );

  const run = useCallback(
    (task: TaskId, files: File[], prompt: string) => {
      if (files.length === 0) return;

      cancelledRef.current = false;
      const isGenerateTask = task !== "transcribe" && task !== "subtitles";

      if (isGenerateTask) {
        const label =
          files.length === 1
            ? files[0].name
            : `${files.length} clips: ${files.map((f) => f.name).join(", ")}`;
        const item = { ...newJobItem(files[0]), fileName: label };
        setState({ jobs: [item] });

        const exportMode: ExportMode =
          task === "cut_xml" ? "xml" : task === "render_clip" ? "render" : "clips";
        void processGenerate(item.clientId, files, prompt, exportMode);
        return;
      }

      const items = files.map((file) => newJobItem(file));
      setState({ jobs: items });

      for (let i = 0; i < files.length; i++) {
        const { clientId } = items[i];
        const file = files[i];
        if (task === "transcribe") {
          void processTranscribe(clientId, file);
        } else {
          void processTranscribe(clientId, file, { approval: true });
        }
      }
    },
    [processGenerate, processTranscribe],
  );

  const burnSubtitles = useCallback(
    async (
      clientId: string,
      segments: EditableSegment[],
      options: SubtitleBurnOptions = {},
    ) => {
      let jobId: string | null = null;
      setState((prev) => {
        jobId = prev.jobs.find((j) => j.clientId === clientId)?.jobId ?? null;
        return prev;
      });
      if (!jobId) return;
      const activeJobId = jobId;

      cancelledRef.current = false;
      patchJob(clientId, {
        phase: "burning",
        stage: "burning",
        percent: 20,
        message: "Burning subtitles into video…",
        error: null,
      });

      try {
        await startSubtitleRender(activeJobId, segments, options);

        let waitStart = Date.now();
        let interval = POLL_MIN_MS;
        let lastStage: string | null = null;
        while (!cancelledRef.current) {
          const status = await fetchWithRetry(
            () => getSubtitleStatus(activeJobId),
            (attempt) => {
              patchJob(clientId, {
                message: `Server busy, retrying poll (${attempt}/${POLL_NETWORK_RETRIES})…`,
              });
            },
          );
          if (status === null) {
            if (Date.now() - waitStart > WAIT_TIMEOUT_MS) {
              throw new ApiError("Job not found on server.", 404);
            }
            await sleep(interval);
            continue;
          }
          waitStart = Date.now();

          const stageChanged = status.status !== lastStage;
          lastStage = status.status;
          interval = nextPollIntervalMs(interval, stageChanged);

          patchJob(clientId, {
            stage: status.status,
            message: status.message || "Burning subtitles…",
            percent: status.progress_percent || 20,
          });

          if (status.status === "completed") break;
          if (status.status === "failed") {
            throw new Error(status.error || "Subtitle burn-in failed.");
          }
          await sleep(interval);
        }

        if (cancelledRef.current) return;

        patchJob(clientId, {
          phase: "done",
          stage: "completed",
          percent: 100,
          message: "Done: subtitles burned in",
          subtitledReady: true,
          subtitledVersion: Date.now(),
        });
      } catch (error) {
        if (cancelledRef.current) return;
        patchJob(clientId, {
          phase: "error",
          error: error instanceof Error ? error.message : String(error),
        });
      }
    },
    [patchJob],
  );

  return { state, run, burnSubtitles, reset };
}
