# Launch & community plan

## Channels (priority order)

| Channel | Why | When |
|---------|-----|------|
| **Hacker News** Show HN | Eng / OSS audience | Day 0 (weekday morning US) |
| **Reddit** r/opensource, r/SelfHosted | Docker-first users | Day 0–1 |
| **Reddit** r/videoediting, r/editors | Practitioners | Day 1 (less hype, more demo) |
| **Reddit** r/MachineLearning | Only if technical depth (STT/LLM pipeline) | Day 2 |
| **Dev.to / Hashnode** | Evergreen tutorial | Week 1 |
| **Product Hunt** | Optional — need polish + GIF | After demo assets ready |
| **X / LinkedIn** | Short clip + repo link | Day 0 |
| **Telegram / RU communities** | RU STT (GigaAM) angle | Day 0 |

Avoid spam: one thoughtful post per community; engage replies for 48h.

## Post templates

### Show HN

**Title:** `Show HN: NeuroCut – open-source AI rough cut to FCP7 XML / MP4`

**Body (short):**

> I built NeuroCut to turn “video + text brief” into a Premiere/DaVinci-friendly rough cut.
>
> Pipeline: FFmpeg proxy → Whisper/Silero/GigaAM → scene detection → Gemini edit plan → FCP7 XML or MP4 clips. There’s also a Premiere CEP plugin that works from a local path.
>
> `docker compose up --build` — UI on :8501.
>
> Repo: https://github.com/jdmarshall95/neurocut
>
> Looking for feedback from editors and people who’ve tried LLM-assisted cutting.

### Reddit (r/videoediting)

Focus on **workflow**, not model hype. Ask: “Would you trust an AI rough cut if you can tweak the plan before export?”

### Dev.to article outline

1. Problem (rough cut time)
2. Architecture diagram
3. Why text-out + scene proxy
4. Docker quick start
5. Extending STT / export
6. Call for contributors

## Keywords / hashtags

`#OpenSource` `#AIvideo` `#VideoEditing` `#Whisper` `#FFmpeg` `#PremierePro` `#FCP7` `#SelfHosted`  
SEO phrases: AI video editing, automatic video cutting, FCP7 XML, Whisper transcription.

## First contributors

1. Label issues: `good first issue`, `docs`, `help wanted`
2. Seed 5–10 issues (typos, badge links, sample STT test, screenshot PR)
3. Thank first PRs publicly; add names to Acknowledgments
4. Offer a clear “add export format” / “add STT engine” path in CONTRIBUTING
5. Host a short Loom walkthrough of the codebase

## Pre-launch checklist

- [ ] Public GitHub repo + Apache-2.0 LICENSE
- [ ] README with GIF placeholder filled
- [ ] CI green on `main`
- [ ] Security policy + CoC
- [ ] At least 3 `good first issue` tickets
- [x] Replace `<your-org>` placeholders in docs
