# Demo assets plan

Goal: make the GitHub README convincing in **&lt; 10 seconds** of scrolling.

## 1. Demo video / GIF (30–60s)

**Script**

| Time | On screen | VO / caption |
|------|-----------|--------------|
| 0–5s | Problem: long timeline in Premiere | “Rough cuts still take hours” |
| 5–15s | NeuroCut UI: drop video + brief | “Video + brief” |
| 15–35s | Progress: STT → scenes → AI edit | Show stages |
| 35–50s | Download XML / open in Premiere | Markers land on timeline |
| 50–60s | Optional: turnkey MP4 result | “Or export ready clips” |

**Production tips**

- 1080p screen capture → compress to GIF (&lt; 8 MB) or upload MP4 to GitHub releases / Streamable
- Use a **rights-cleared** sample (own clip or CC0)
- Blur faces / logos if needed
- End card: `github.com/<org>/neurocut` + `docker compose up`

**Output files**

```
docs/assets/demo.gif          # or demo.mp4 + GIF poster
docs/assets/demo-poster.png
```

## 2. Annotated screenshots

| File | Content |
|------|---------|
| `ui-upload.png` | Task picker + dropzone + brief field (arrows) |
| `ui-progress.png` | Pipeline steps including scene detection |
| `ui-result.png` | Downloads: XML / ZIP / render |
| `plugin-panel.png` | Premiere CEP panel |

Annotate with a simple tool (Figma, Excalidraw, cleanshot). Dark UI → light callouts for contrast.

## 3. Example input / output

```
docs/examples/
  README.md                 # how to reproduce
  sample_brief.txt          # short editing brief
  sample_edit_plan.json     # anonymized plan (no PII)
  # optional: sample_proxy_10s.mp4 if license allows
```

Do **not** commit large originals into `main`. Prefer Release attachments or Git LFS later.

## Checklist

- [ ] Record 60s walkthrough
- [ ] Export GIF + still poster
- [ ] 3 UI screenshots with captions
- [ ] Embed in root README
- [ ] Add `docs/examples/` with brief + edit_plan
