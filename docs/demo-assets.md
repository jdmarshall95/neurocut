# Demo assets

README media lives in [`docs/assets/`](assets/):

| File | Role |
|------|------|
| `neurocut-demo.gif` / `neurocut-demo.mp4` | Pipeline walkthrough |
| `ui-01-*.png` … `ui-08-*.png` | Stage screenshots |

## Regenerate UI screenshots

Requires `docker compose up`, Playwright + Chromium, and `ffmpeg` on `PATH`:

```bash
node scripts/capture-ui-demo.mjs
```

Screenshots are written to `docs/assets/`. To rebuild the GIF, make a local (gitignored) ffmpeg concat list such as `scripts/capture-ui-demo.frames.txt`, then:

```bash
ffmpeg -y -v error -f concat -safe 0 -i scripts/capture-ui-demo.frames.txt \
  -vf "scale=960:-2:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4" \
  -loop 0 docs/assets/neurocut-demo.gif
```

Do not commit private client footage or capture intermediates (`*.frames.txt`).
