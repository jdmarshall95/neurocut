export type TaskId =
  | "transcribe"
  | "cut_xml"
  | "cut_clips"
  | "render_clip"
  | "subtitles";
export type ExportMode = "xml" | "clips" | "render";

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
}

export interface PipelineState {
  job_id: string;
  stage: string;
  message: string;
  progress_percent: number;
  export_mode: ExportMode | "plugin";
  analysis_mode: "speech" | "visual" | null;
  error: string | null;
}

export interface PipelineStatusResponse {
  pipeline: PipelineState;
  transcription: {
    status: string;
    message: string;
    progress_percent: number;
  } | null;
  analysis: {
    status: string;
    message: string;
  } | null;
}

export interface JobResult {
  job_id: string;
  prompt: string;
  export_mode: ExportMode;
  analysis_mode: "speech" | "visual" | null;
  original_path: string;
  transcript_path: string;
  visual_timeline_path: string | null;
  edit_plan_path: string;
  xml_path: string | null;
  clips_dir_path: string | null;
  clips_zip_path: string | null;
  render_path: string | null;
  language: string | null;
  duration: number | null;
  clip_count: number;
  marker_count: number;
  fps: number | null;
  timebase: number | null;
  edit_plan: {
    clips: Array<{
      start_sec: number;
      end_sec: number;
      track: number;
      reason: string;
    }>;
    markers: Array<{ time_sec: number; comment: string }>;
  };
  transcript: TranscriptSegment[];
}

export interface TranscriptionStatus {
  status: string;
  message: string;
  progress_percent: number;
  error?: string | null;
}

export interface TranscriptResult {
  job_id: string;
  source: string;
  has_speech: boolean;
  cached: boolean;
  language: string | null;
  duration: number | null;
  segment_count: number;
  transcript: TranscriptSegment[];
}

export type StageStatus = "done" | "active" | "pending" | "error";

export interface Step {
  stage: string;
  label: string;
}

export interface SubtitleStatus {
  status: string;
  progress_percent: number;
  message: string;
  segment_count: number;
  output_path?: string | null;
  error?: string | null;
}

export interface EditableSegment {
  start: number;
  end: number;
  text: string;
}
