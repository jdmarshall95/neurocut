"""Karaoke-style subtitle chunking.

Splits phrase-level transcript segments into short on-screen chunks
(at most 1–3 words) whose timing follows the moment each word is spoken.

Word-level timestamps are not available from every STT engine (GigaAM /
Silero produce phrase-level VAD segments). To stay engine-agnostic we
distribute each phrase's speech interval [start, end] across its words in
proportion to their length. The VAD interval already bounds *when* speech
happens, so each chunk is shown precisely while those words are voiced.

The number of words per chunk is derived from the video frame width so a
narrow (vertical) frame shows fewer words than a wide one, capped at
``max_words``.

Readability rules applied while grouping:
- A chunk never crosses a sentence boundary: a word that ends a sentence
  (``. ! ? …``) always closes the current chunk. This prevents lines that mix
  the end of one sentence and the capitalized start of the next.
- Words of a single sentence are distributed as evenly as possible so we do
  not leave a dangling one-word tail (e.g. avoid ``[3][1]`` in favour of
  ``[2][2]``).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.services.subtitle_burner import SubtitleSegment

_WORD_RE = re.compile(r"\S+")
_SENTENCE_END_CHARS = ".!?…"
_TRAILING_WRAP = "\"')»”„“"


def _ceil_div(a: int, b: int) -> int:
    return -(-a // max(1, b))


def char_budget(
    frame_width: int, font_size: int, *, char_ratio: float, side_margin: int
) -> int:
    """Approximate how many characters fit on one subtitle line."""
    usable = max(1, frame_width - 2 * max(0, side_margin))
    approx_char_px = max(1.0, font_size * char_ratio)
    return max(1, int(usable / approx_char_px))


def _ends_sentence(word: str) -> bool:
    stripped = word.rstrip(_TRAILING_WRAP)
    return stripped.endswith(tuple(_SENTENCE_END_CHARS))


def _word_bounds(segment: "SubtitleSegment", words: list[str]) -> list[tuple[float, float]]:
    """Per-word [start, end] distributed across the segment by word length."""
    weights = [len(word) + 1 for word in words]
    total_weight = sum(weights) or 1
    span = max(0.001, segment.end - segment.start)
    bounds: list[tuple[float, float]] = []
    acc = 0
    for weight in weights:
        start = segment.start + (acc / total_weight) * span
        acc += weight
        end = segment.start + (acc / total_weight) * span
        bounds.append((start, end))
    return bounds


def _sentence_groups(words: list[str]) -> list[list[int]]:
    """Group word indices into sentences (break after sentence punctuation)."""
    groups: list[list[int]] = []
    current: list[int] = []
    for index, word in enumerate(words):
        current.append(index)
        if _ends_sentence(word):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _even_chunks(indices: list[int], words: list[str], budget: int, max_words: int) -> list[list[int]]:
    """Split one sentence's word indices into balanced chunks.

    The chunk count is the minimum needed to satisfy both the word cap and the
    width budget; words are then spread evenly to avoid orphan one-word tails.
    """
    n = len(indices)
    if n == 0:
        return []
    total_chars = sum(len(words[i]) for i in indices) + (n - 1)
    k_words = _ceil_div(n, max_words)
    k_chars = _ceil_div(total_chars, budget)
    k = min(n, max(1, k_words, k_chars))

    base, remainder = divmod(n, k)
    chunks: list[list[int]] = []
    pos = 0
    for c in range(k):
        size = base + (1 if c < remainder else 0)
        chunks.append(indices[pos : pos + size])
        pos += size
    return chunks


def chunk_subtitle_segments(
    segments: list["SubtitleSegment"],
    *,
    frame_width: int,
    font_size: int,
    char_ratio: float = 0.6,
    side_margin: int = 40,
    max_words: int = 3,
) -> list["SubtitleSegment"]:
    """Split phrase segments into width-aware, sentence-aware chunks.

    Each returned chunk carries the sub-interval of the original segment
    during which its words are spoken (proportional to word length).
    """
    from app.services.subtitle_burner import SubtitleSegment

    max_words = max(1, max_words)
    budget = char_budget(
        frame_width, font_size, char_ratio=char_ratio, side_margin=side_margin
    )

    result: list[SubtitleSegment] = []
    for segment in segments:
        words = _WORD_RE.findall(segment.text)
        if not words:
            continue
        bounds = _word_bounds(segment, words)
        for sentence in _sentence_groups(words):
            for chunk in _even_chunks(sentence, words, budget, max_words):
                result.append(
                    SubtitleSegment(
                        start=bounds[chunk[0]][0],
                        end=bounds[chunk[-1]][1],
                        text=" ".join(words[i] for i in chunk),
                    )
                )

    return result


def split_segments_into_sentences(
    segments: list["SubtitleSegment"],
) -> list["SubtitleSegment"]:
    """Break each segment at sentence boundaries (period -> new line).

    Timings are distributed across the segment proportionally to word length.
    Used after proofreading so a full stop starts a new subtitle line and no
    line mixes two sentences.
    """
    from app.services.subtitle_burner import SubtitleSegment

    result: list[SubtitleSegment] = []
    for segment in segments:
        words = _WORD_RE.findall(segment.text)
        if not words:
            continue
        bounds = _word_bounds(segment, words)
        for sentence in _sentence_groups(words):
            result.append(
                SubtitleSegment(
                    start=bounds[sentence[0]][0],
                    end=bounds[sentence[-1]][1],
                    text=" ".join(words[i] for i in sentence),
                )
            )
    return result
