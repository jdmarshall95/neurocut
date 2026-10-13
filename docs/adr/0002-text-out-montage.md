# ADR 0002: Text-out LLM montage by default

## Status

Accepted (2026-07, refined 2026-10)

## Context

Uploading proxy video to Gemini is expensive, hits free-tier quotas, and many current Flash models are billed/available as **text-out**. Visual claims (“no blur”) from text-only models are hallucinations.

## Decision

- Default `USE_VIDEO_FOR_LLM=false`
- Always run **scene detection** on a cheap low-FPS proxy
- Feed LLM: brief + transcript + shot boundaries (+ sources manifest)
- Prompt explicitly forbids inventing visual quality

## Consequences

- Faster, more quota-friendly montage
- Better alignment to shot cuts than transcript-only slicing
- True “stable / no blur” quality still needs heuristics or vision models later
