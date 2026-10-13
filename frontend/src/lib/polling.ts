/** Adaptive polling: faster after stage change, slower when idle. */
export const POLL_MIN_MS = 1_500;
export const POLL_MAX_MS = 4_000;
export const POLL_STEP_MS = 500;

export function nextPollIntervalMs(
  current: number,
  stageChanged: boolean,
): number {
  if (stageChanged) return POLL_MIN_MS;
  return Math.min(current + POLL_STEP_MS, POLL_MAX_MS);
}

export function isRetryableStatus(status: number): boolean {
  return status === 408 || status === 429 || status >= 500;
}
