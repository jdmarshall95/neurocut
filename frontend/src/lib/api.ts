import type {
  JobResult,
  PipelineStatusResponse,
  TranscriptionStatus,
  TranscriptResult,
} from "./types";

const STORAGE_KEY = "neurocut.apiBaseUrl";

const ENV_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();

const DEFAULT_BASE = ENV_BASE && ENV_BASE.length > 0 ? ENV_BASE : "http://127.0.0.1:8000";

export function getApiBaseUrl(): string {
  const saved = localStorage.getItem(STORAGE_KEY);
  return (saved && saved.trim()) || DEFAULT_BASE;
}

export function setApiBaseUrl(url: string): void {
  const cleaned = url.trim().replace(/\/+$/, "");
  if (cleaned) {
    localStorage.setItem(STORAGE_KEY, cleaned);
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseError(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (data && typeof data.detail === "string") return data.detail;
    if (data && Array.isArray(data.detail)) {
      return data.detail.map((d: { msg?: string }) => d.msg).join("; ");
    }
  } catch {
    // ignore
  }
  return `HTTP ${response.status}`;
}

export async function checkHealth(signal?: AbortSignal): Promise<boolean> {
  try {
    const response = await fetch(`${getApiBaseUrl()}/health`, {
      signal,
      cache: "no-store",
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function startTranscribe(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${getApiBaseUrl()}/jobs/transcribe`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
  const data = await response.json();
  return data.job_id as string;
}

export async function startGenerate(
  files: File[],
  prompt: string,
  exportMode: "xml" | "clips" | "render",
): Promise<string> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  form.append("prompt", prompt);
  form.append("export_mode", exportMode);
  const response = await fetch(`${getApiBaseUrl()}/jobs/generate`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
  const data = await response.json();
  return data.job_id as string;
}

export async function getPipelineStatus(
  jobId: string,
): Promise<PipelineStatusResponse | null> {
  const response = await fetch(`${getApiBaseUrl()}/jobs/${jobId}/status`, {
    cache: "no-store",
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
  return response.json();
}

export async function getJobResult(jobId: string): Promise<JobResult> {
  const response = await fetch(`${getApiBaseUrl()}/jobs/${jobId}/result`, {
    cache: "no-store",
  });
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
  return response.json();
}

export async function getTranscriptionStatus(
  jobId: string,
): Promise<TranscriptionStatus | null> {
  const response = await fetch(
    `${getApiBaseUrl()}/jobs/${jobId}/transcription/status`,
    { cache: "no-store" },
  );
  if (response.status === 404) return null;
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
  return response.json();
}

export async function getTranscript(jobId: string): Promise<TranscriptResult> {
  const response = await fetch(`${getApiBaseUrl()}/jobs/${jobId}/transcript`, {
    cache: "no-store",
  });
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
  return response.json();
}

export function downloadUrl(
  jobId: string,
  exportMode: "xml" | "clips" | "render",
): string {
  const suffix =
    exportMode === "xml"
      ? "export/xml/download"
      : exportMode === "render"
        ? "export/render/download"
        : "export/clips/download";
  return `${getApiBaseUrl()}/jobs/${jobId}/${suffix}`;
}

export interface SubtitleBurnOptions {
  autoChunk?: boolean;
  maxWords?: number;
  fontName?: string;
  primaryColor?: string;
  outlineColor?: string;
  maskSize?: number;
  borderStyle?: number;
}

export async function startSubtitleRender(
  jobId: string,
  segments: Array<{ start: number; end: number; text: string }>,
  options: SubtitleBurnOptions = {},
): Promise<void> {
  const body: Record<string, unknown> = { segments };
  if (options.autoChunk !== undefined) body.auto_chunk = options.autoChunk;
  if (options.maxWords !== undefined) body.max_words = options.maxWords;
  const style: Record<string, unknown> = {};
  if (options.fontName) style.font_name = options.fontName;
  if (options.primaryColor) style.primary_color = options.primaryColor;
  if (options.outlineColor) style.outline_color = options.outlineColor;
  if (options.maskSize !== undefined) style.outline = options.maskSize;
  if (options.borderStyle !== undefined) style.border_style = options.borderStyle;
  if (Object.keys(style).length > 0) body.style = style;
  const response = await fetch(
    `${getApiBaseUrl()}/jobs/${jobId}/subtitles/render`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
}

export async function getSubtitleStatus(
  jobId: string,
): Promise<import("./types").SubtitleStatus | null> {
  const response = await fetch(
    `${getApiBaseUrl()}/jobs/${jobId}/subtitles/status`,
    { cache: "no-store" },
  );
  if (response.status === 404) return null;
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
  return response.json();
}

export function subtitledDownloadUrl(
  jobId: string,
  cacheBust?: number | string,
): string {
  const base = `${getApiBaseUrl()}/jobs/${jobId}/subtitles/download`;
  return cacheBust ? `${base}?v=${cacheBust}` : base;
}

export interface ChunkPreviewSegment {
  start: number;
  end: number;
  text: string;
  overflow: boolean;
}

export interface ChunkPreviewResult {
  frame_width: number;
  font_size: number;
  char_budget: number;
  segment_count: number;
  overflow_count: number;
  segments: ChunkPreviewSegment[];
}

export async function previewSubtitleChunks(
  jobId: string,
  segments: Array<{ start: number; end: number; text: string }>,
  maxWords: number,
): Promise<ChunkPreviewResult> {
  const response = await fetch(
    `${getApiBaseUrl()}/jobs/${jobId}/subtitles/chunk`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ segments, max_words: maxWords }),
    },
  );
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
  return response.json();
}

export interface SubtitleFont {
  name: string;
  label: string;
}

export async function getSubtitleFonts(): Promise<SubtitleFont[]> {
  const response = await fetch(`${getApiBaseUrl()}/subtitles/fonts`, {
    cache: "no-store",
  });
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
  const data = await response.json();
  return data.fonts as SubtitleFont[];
}

export function subtitleFontFileUrl(name: string): string {
  return `${getApiBaseUrl()}/subtitles/fonts/${encodeURIComponent(name)}/file`;
}

const loadedFontFaces = new Set<string>();

/**
 * Registers @font-face rules that pull the exact TTFs used for burn-in, so the
 * in-app preview renders in the same typeface as the final video.
 */
export async function ensureSubtitleFontsLoaded(
  fonts: Array<{ name: string }>,
): Promise<void> {
  if (typeof document === "undefined" || !("fonts" in document)) return;
  await Promise.all(
    fonts.map(async ({ name }) => {
      if (loadedFontFaces.has(name)) return;
      loadedFontFaces.add(name);
      try {
        const url = subtitleFontFileUrl(name);
        const face = new FontFace(name, `url("${url}")`);
        const loaded = await face.load();
        (document as Document & { fonts: FontFaceSet }).fonts.add(loaded);
      } catch {
        loadedFontFaces.delete(name);
      }
    }),
  );
}

export async function proofreadSubtitles(
  segments: Array<{ start: number; end: number; text: string }>,
  language?: string | null,
): Promise<{
  segments: Array<{ start: number; end: number; text: string }>;
  changed: boolean;
}> {
  const response = await fetch(`${getApiBaseUrl()}/subtitles/proofread`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ segments, language: language ?? null }),
  });
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
  return response.json();
}
