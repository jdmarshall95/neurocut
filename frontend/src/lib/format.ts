import type { TranscriptSegment } from "./types";

export function formatTimestamp(seconds: number): string {
  const total = Math.max(0, seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const pad = (n: number) => String(Math.floor(n)).padStart(2, "0");
  return `${pad(hours)}:${pad(minutes)}:${secs.toFixed(3).padStart(6, "0")}`;
}

/**
 * Parse a timecode string back into seconds. Accepts:
 *   - plain seconds ("12.5")
 *   - "MM:SS.mmm"
 *   - "HH:MM:SS.mmm"
 * Returns null if it cannot be parsed.
 */
export function parseTimestamp(value: string): number | null {
  const trimmed = value.trim().replace(",", ".");
  if (!trimmed) return null;
  const parts = trimmed.split(":");
  if (parts.some((p) => p !== "" && Number.isNaN(Number(p)))) return null;
  const nums = parts.map((p) => (p === "" ? 0 : Number(p)));
  let seconds: number;
  if (nums.length === 1) {
    seconds = nums[0];
  } else if (nums.length === 2) {
    seconds = nums[0] * 60 + nums[1];
  } else if (nums.length === 3) {
    seconds = nums[0] * 3600 + nums[1] * 60 + nums[2];
  } else {
    return null;
  }
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

export function segmentsToPlainText(segments: TranscriptSegment[]): string {
  return segments.map((s) => s.text.trim()).join("\n");
}

export function segmentsToSrt(segments: TranscriptSegment[]): string {
  const srtTime = (seconds: number): string => {
    const millis = Math.round(seconds * 1000);
    const hours = Math.floor(millis / 3_600_000);
    const minutes = Math.floor((millis % 3_600_000) / 60_000);
    const secs = Math.floor((millis % 60_000) / 1000);
    const ms = millis % 1000;
    const pad = (n: number, w = 2) => String(n).padStart(w, "0");
    return `${pad(hours)}:${pad(minutes)}:${pad(secs)},${pad(ms, 3)}`;
  };

  return segments
    .map((segment, index) => {
      return `${index + 1}\n${srtTime(segment.start)} --> ${srtTime(
        segment.end,
      )}\n${segment.text.trim()}\n`;
    })
    .join("\n");
}

export function downloadTextFile(
  filename: string,
  content: string,
  mime = "text/plain",
): void {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
