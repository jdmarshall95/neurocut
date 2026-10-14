// Captures the NeuroCut UI stage-by-stage for the README walkthrough.
//
// Two passes:
//   A. Cold pipeline run straight over the API (100 ms polling) — records the
//      real payload + timestamp of every stage.
//   B. Replays the recorded stages in the SPA via page.route("**/jobs/*/status")
//      and screenshots the progress card for each stage, then the result card
//      (with an FFmpeg-extracted poster frame so the preview isn't gray).
//
// Requires: docker compose up, Playwright + Chromium, ffmpeg on PATH.
//   node scripts/capture-ui-demo.mjs
//
// After screenshots land in docs/assets/, build the GIF/MP4 from a local
// (gitignored) concat list, e.g.:
//   scripts/capture-ui-demo.frames.txt  →  docs/assets/neurocut-demo.gif
//   ffmpeg -y -v error -f concat -safe 0 -i scripts/capture-ui-demo.frames.txt \
//     -vf "scale=960:-2:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4" \
//     -loop 0 docs/assets/neurocut-demo.gif
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import fs from "node:fs";

const UI = "http://127.0.0.1:8501";
const API = "http://127.0.0.1:8000";
const REPO = "/Users/i.drozdov/neurocut";
const VIDEO = `${REPO}/storage/test-input/sintel-trailer.mp4`;
const OUT = `${REPO}/docs/assets`;
const PROMPT =
  "Cut a 30 second cinematic teaser: keep the emotional narration and the most dramatic wide shots, drop slow dialogue scenes.";

// Pipeline stage -> screenshot name (matches the UI stepper order).
const WANTED = new Map([
  ["extracting_audio", "ui-03-audio"],
  ["transcribing", "ui-04-transcribing"],
  ["analyzing_scenes", "ui-05-scenes"],
  ["ai_editing", "ui-06-ai-editing"],
  ["rendering_clip", "ui-07-rendering"],
]);

const sh = (cmd, args) => execFileSync(cmd, args, { cwd: REPO, encoding: "utf8" });
const get = async (path) => (await fetch(`${API}${path}`)).json();

/* ------------------------------------------------------------------ *
 * Pass A — cold pipeline run over the API, fast polling.
 * Records the real payload + timestamp of every stage.
 * ------------------------------------------------------------------ */
sh("docker", ["compose", "exec", "-T", "api", "sh", "-c", "rm -rf /app/storage/transcripts/*"]);

const form = new FormData();
form.append("files", new Blob([fs.readFileSync(VIDEO)], { type: "video/mp4" }), "sintel-trailer.mp4");
form.append("prompt", PROMPT);
form.append("export_mode", "render");

const t0 = Date.now();
const cold = await (await fetch(`${API}/jobs/generate`, { method: "POST", body: form })).json();
console.log("▶ cold run job:", cold.job_id);

const stages = []; // [{ stage, at, payload }]
let lastStage = null;
while (Date.now() - t0 < 420_000) {
  const data = await get(`/jobs/${cold.job_id}/status`);
  const stage = data.pipeline.stage;
  if (stage !== lastStage) {
    stages.push({ stage, at: (Date.now() - t0) / 1000, payload: data });
    console.log(`  ${((Date.now() - t0) / 1000).toFixed(2)}s  ${stage}`);
    lastStage = stage;
  }
  if (stage === "completed" || stage === "failed") break;
  await new Promise((r) => setTimeout(r, 100));
}
const coldTotal = (Date.now() - t0) / 1000;

/* ------------------------------------------------------------------ *
 * Pass B — replay the recorded stages in the UI and screenshot each.
 * ------------------------------------------------------------------ */
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

const shot = async (name) => {
  await page.screenshot({ path: `${OUT}/${name}.png` });
  console.log(`  📸 ${name}`);
};

let queue = [];
let hold = null;
await page.route("**/jobs/*/status", async (route) => {
  if (hold && hold.left-- > 0) {
    return route.fulfill({ status: 200, body: hold.body, contentType: "application/json" });
  }
  const next = queue.shift();
  if (next) {
    hold = { body: JSON.stringify(next.payload), left: 5 };
    return route.fulfill({ status: 200, body: hold.body, contentType: "application/json" });
  }
  const res = await route.fetch();
  return route.fulfill({ status: res.status(), body: await res.text(), contentType: "application/json" });
});

// 1. Landing page
await page.goto(UI, { waitUntil: "networkidle" });
await page.waitForTimeout(1200);
await shot("ui-01-landing");

// 2. Upload video + editing brief
await page.setInputFiles('input[type="file"]', VIDEO);
await page.waitForTimeout(600);
await page.fill("textarea", PROMPT);
await page.waitForTimeout(400);
await shot("ui-02-upload");

// Queue only the stages we want to photograph, in order.
queue = stages.filter((s) => WANTED.has(s.stage));

await page.click('button:has-text("Build clip")');
console.log("▶ replay run started");

// Deterministic: wait for the exact message text that the backend emitted for
// this stage (pipeline.py may override STAGE_MESSAGES), so we never drift
// against the SPA's adaptive polling.
for (const s of stages.filter((x) => WANTED.has(x.stage))) {
  const msg = s.payload?.pipeline?.message ?? s.stage;
  await page
    .getByText(msg, { exact: false })
    .first()
    .waitFor({ state: "visible", timeout: 30_000 })
    .catch(() => console.log(`  ⚠ timeout waiting for "${msg}"`));
  const card = page.locator(".glass-strong").first();
  if (await card.isVisible().catch(() => false)) {
    await card.scrollIntoViewIfNeeded().catch(() => {});
    await shot(WANTED.get(s.stage));
  }
}

// 3. Result card
await page.waitForSelector("text=Turnkey clip ready", { timeout: 180_000 });
await page.waitForTimeout(1500);
try {
  sh("docker", ["compose", "cp", `api:/app/storage/${cold.job_id}/neurocut_render.mp4`, "/tmp/shot/render.mp4"]);
  execFileSync("ffmpeg", ["-y", "-ss", "6", "-i", "/tmp/shot/render.mp4", "-frames:v", "1",
    "-vf", "scale=1100:-2", "/tmp/shot/poster.jpg"], { stdio: "ignore" });
  const b64 = fs.readFileSync("/tmp/shot/poster.jpg").toString("base64");
  await page.evaluate((src) => {
    const v = document.querySelector("video");
    if (v) v.poster = `data:image/jpeg;base64,${src}`;
  }, b64);
  console.log("  🖼  poster frame injected");
} catch (err) {
  console.log("  poster skipped:", String(err).slice(0, 60));
}
// Scroll the result card to the top of the viewport, then take a full-page
// shot so it matches the framing/dimensions of the stage screenshots.
await page.evaluate(() => {
  const card = [...document.querySelectorAll(".glass-strong")].find((el) =>
    el.textContent?.includes("Turnkey clip ready"),
  );
  if (card) window.scrollTo({ top: card.getBoundingClientRect().top + window.scrollY - 24 });
});
await page.waitForTimeout(700);
await shot("ui-08-result");
await browser.close();

/* ------------------------------------------------------------------ *
 * Report
 * ------------------------------------------------------------------ */
const durations = stages.map((s, i) => ({
  stage: s.stage,
  started_at: Number(s.at.toFixed(1)),
  took: Number(((stages[i + 1]?.at ?? coldTotal) - s.at).toFixed(1)),
}));
fs.writeFileSync("/tmp/shot/timings.json", JSON.stringify({ job_id: cold.job_id, total: Number(coldTotal.toFixed(1)), durations }, null, 2));
console.log("\ncold-run stage timings:");
for (const d of durations) console.log(`  ${d.stage.padEnd(18)} ${String(d.took).padStart(6)}s`);
console.log(`  ${"total".padEnd(18)} ${coldTotal.toFixed(1)}s`);
