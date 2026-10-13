import type { ExportMode, Step } from "./types";

const FINAL_STEP: Record<ExportMode, Step> = {
  xml: { stage: "generating_xml", label: "Export XML" },
  clips: { stage: "generating_clips", label: "Splitting clips" },
  render: { stage: "rendering_clip", label: "Rendering clip" },
};

export function buildPipelineSteps(exportMode: ExportMode): Step[] {
  const steps: Step[] = [
    { stage: "extracting_audio", label: "Audio" },
    { stage: "transcribing", label: "Transcription" },
    { stage: "analyzing_scenes", label: "Scene detection" },
  ];
  steps.push({ stage: "ai_editing", label: "AI edit" });
  steps.push(FINAL_STEP[exportMode]);
  return steps;
}

export const TRANSCRIBE_STEPS: Step[] = [
  { stage: "loading_model", label: "Loading model" },
  { stage: "transcribing", label: "Transcription" },
  { stage: "completed", label: "Done" },
];

export const SUBTITLE_STEPS: Step[] = [
  { stage: "loading_model", label: "Transcription" },
  { stage: "transcribing", label: "Speech recognition" },
  { stage: "approval", label: "Review" },
  { stage: "burning", label: "Burn-in" },
  { stage: "completed", label: "Done" },
];
