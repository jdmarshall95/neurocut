import { useEffect, useRef, useState } from "react";
import {
  CheckBadgeIcon,
  CheckIcon,
  ExclamationTriangleIcon,
  LanguageIcon,
  PlusIcon,
  SparklesIcon,
  TrashIcon,
} from "@heroicons/react/24/outline";
import { GlassCard } from "./ui/GlassCard";
import { Button } from "./ui/Button";
import {
  ensureSubtitleFontsLoaded,
  getSubtitleFonts,
  previewSubtitleChunks,
  proofreadSubtitles,
  type SubtitleFont,
} from "../lib/api";
import { formatTimestamp, parseTimestamp } from "../lib/format";
import type { EditableSegment, TranscriptResult } from "../lib/types";

export interface SubtitleConfirmOptions {
  autoChunk: boolean;
  maxWords: number;
  fontName: string;
  primaryColor: string;
  outlineColor: string;
  maskSize: number;
  borderStyle: number;
}

// ASS colours are &HAABBGGRR (00 alpha = opaque).
const WHITE = "&H00FFFFFF";
const BLACK = "&H00000000";

interface ColorPreset {
  id: string;
  label: string;
  primary: string;
  outline: string;
}

const COLOR_PRESETS: ColorPreset[] = [
  { id: "wb", label: "W/B", primary: WHITE, outline: BLACK },
  { id: "bw", label: "B/W", primary: BLACK, outline: WHITE },
];

const FALLBACK_FONTS: SubtitleFont[] = [
  { name: "Manrope", label: "Manrope" },
  { name: "Unbounded", label: "Unbounded" },
  { name: "Bebas Neue", label: "Bebas Neue" },
  { name: "Coolvetica", label: "Coolvetica" },
  { name: "Days One", label: "Days One" },
  { name: "Playfair Display", label: "Playfair Display" },
  { name: "AngelicaC", label: "Angelica" },
];

interface SubtitleEditorProps {
  jobId: string;
  transcript: TranscriptResult;
  busy?: boolean;
  onConfirm: (segments: EditableSegment[], options: SubtitleConfirmOptions) => void;
}

const cleanSegments = (segments: EditableSegment[]): EditableSegment[] =>
  segments
    .filter((s) => s.text.trim().length > 0)
    .map((s) => ({
      start: s.start,
      end: s.end > s.start ? s.end : s.start + 0.5,
      text: s.text.trim(),
    }))
    .sort((a, b) => a.start - b.start);

export function SubtitleEditor({
  jobId,
  transcript,
  busy,
  onConfirm,
}: SubtitleEditorProps) {
  const initialPhrases = useRef<EditableSegment[]>(
    transcript.transcript.map((s) => ({ start: s.start, end: s.end, text: s.text })),
  );
  const [segments, setSegments] = useState<EditableSegment[]>(initialPhrases.current);
  const [autoChunk, setAutoChunk] = useState(true);
  const [maxWords, setMaxWords] = useState(3);
  // Phrase-level snapshot to re-chunk from when max words changes / karaoke off.
  const [phrases, setPhrases] = useState<EditableSegment[] | null>(null);
  const [charBudget, setCharBudget] = useState<number | null>(null);
  const [chunkBusy, setChunkBusy] = useState(false);
  const [chunkError, setChunkError] = useState<string | null>(null);
  const [fonts, setFonts] = useState<SubtitleFont[]>(FALLBACK_FONTS);
  const [selectedFont, setSelectedFont] = useState<string>(FALLBACK_FONTS[0].name);
  const [colorPreset, setColorPreset] = useState<string>(COLOR_PRESETS[0].id);
  const [maskStyle, setMaskStyle] = useState<number>(1);
  const [maskSize, setMaskSize] = useState<number>(2);
  const [proofBusy, setProofBusy] = useState(false);
  const [proofNote, setProofNote] = useState<string | null>(null);
  const requestSeq = useRef(0);
  const inited = useRef(false);

  useEffect(() => {
    void ensureSubtitleFontsLoaded(FALLBACK_FONTS);
    getSubtitleFonts()
      .then((list) => {
        if (list.length > 0) {
          setFonts(list);
          void ensureSubtitleFontsLoaded(list);
          setSelectedFont((prev) =>
            list.some((f) => f.name === prev) ? prev : list[0].name,
          );
        }
      })
      .catch(() => {
        /* keep fallback fonts */
      });
  }, []);

  const chunkFrom = async (base: EditableSegment[], words: number) => {
    const cleaned = cleanSegments(base);
    if (cleaned.length === 0) {
      setSegments([]);
      return;
    }
    const seq = ++requestSeq.current;
    setChunkBusy(true);
    setChunkError(null);
    try {
      const result = await previewSubtitleChunks(jobId, cleaned, words);
      if (seq !== requestSeq.current) return;
      setSegments(
        result.segments.map((s) => ({ start: s.start, end: s.end, text: s.text })),
      );
      setCharBudget(result.char_budget);
    } catch (error) {
      if (seq !== requestSeq.current) return;
      setChunkError(
        error instanceof Error ? error.message : "Could not split text into words",
      );
    } finally {
      if (seq === requestSeq.current) setChunkBusy(false);
    }
  };

  // Karaoke is on by default: split the transcript into words on mount.
  useEffect(() => {
    if (inited.current) return;
    inited.current = true;
    if (autoChunk) {
      const snap = initialPhrases.current;
      setPhrases(snap);
      void chunkFrom(snap, maxWords);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleKaraoke = (checked: boolean) => {
    setAutoChunk(checked);
    if (checked) {
      const snap = phrases ?? segments;
      setPhrases(snap);
      void chunkFrom(snap, maxWords);
    } else {
      requestSeq.current++;
      setChunkBusy(false);
      setCharBudget(null);
      if (phrases) setSegments(phrases);
      setPhrases(null);
    }
  };

  const changeMaxWords = (n: number) => {
    setMaxWords(n);
    if (autoChunk && phrases) void chunkFrom(phrases, n);
  };

  const runProofread = async () => {
    const source = autoChunk ? phrases ?? segments : segments;
    const cleaned = cleanSegments(source);
    if (cleaned.length === 0) return;
    setProofBusy(true);
    setProofNote(null);
    try {
      const result = await proofreadSubtitles(cleaned, transcript.language);
      const corrected = result.segments.map((s) => ({
        start: s.start,
        end: s.end,
        text: s.text,
      }));
      if (autoChunk) {
        setPhrases(corrected);
        await chunkFrom(corrected, maxWords);
      } else {
        setSegments(corrected);
      }
      setProofNote(
        result.changed ? "Spelling and punctuation updated" : "No issues found",
      );
    } catch (error) {
      setProofNote(
        error instanceof Error ? error.message : "Could not proofread text",
      );
    } finally {
      setProofBusy(false);
    }
  };

  const updateText = (index: number, text: string) => {
    setSegments((prev) =>
      prev.map((segment, i) => (i === index ? { ...segment, text } : segment)),
    );
  };

  const updateTime = (index: number, field: "start" | "end", raw: string) => {
    const parsed = parseTimestamp(raw);
    if (parsed === null) return;
    setSegments((prev) =>
      prev.map((segment, i) => (i === index ? { ...segment, [field]: parsed } : segment)),
    );
  };

  const removeSegment = (index: number) => {
    setSegments((prev) => prev.filter((_, i) => i !== index));
  };

  const insertAfter = (index: number) => {
    setSegments((prev) => {
      const base = index >= 0 && prev[index] ? prev[index].end : 0;
      const next = prev[index + 1];
      const end = next ? Math.max(base + 0.5, (base + next.start) / 2) : base + 2;
      const created: EditableSegment = { start: base, end, text: "" };
      const copy = [...prev];
      copy.splice(index + 1, 0, created);
      return copy;
    });
  };

  const isOverflow = (text: string) =>
    charBudget !== null && text.trim().length > charBudget;

  const nonEmpty = segments.filter((s) => s.text.trim().length > 0);
  const overflowCount = nonEmpty.filter((s) => isOverflow(s.text)).length;

  const handleConfirm = () => {
    const preset =
      COLOR_PRESETS.find((p) => p.id === colorPreset) ?? COLOR_PRESETS[0];
    // The segments shown here ARE the approved text — burn them as-is.
    onConfirm(cleanSegments(segments), {
      autoChunk: false,
      maxWords,
      fontName: selectedFont,
      primaryColor: preset.primary,
      outlineColor: preset.outline,
      maskSize,
      borderStyle: maskStyle,
    });
  };

  if (transcript.transcript.length === 0 && segments.length === 0) {
    return (
      <GlassCard tone="strong" className="space-y-4 p-6 animate-fade-in-up sm:p-8">
        <div className="flex items-center gap-3">
          <LanguageIcon className="h-7 w-7 text-amber-400" />
          <div>
            <h3 className="text-lg font-bold text-slate-50">No speech detected</h3>
            <p className="text-sm text-slate-400">
              The audio track has no recognizable speech. Add lines manually or
              choose another video.
            </p>
          </div>
        </div>
        <Button
          variant="outline"
          icon={<PlusIcon className="h-4 w-4" />}
          onClick={() => insertAfter(-1)}
        >
          Add line
        </Button>
      </GlassCard>
    );
  }

  return (
    <GlassCard tone="strong" className="space-y-5 p-6 animate-fade-in-up sm:p-8">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white">
            <LanguageIcon className="h-5 w-5" />
          </span>
          <div>
            <h3 className="text-lg font-bold text-slate-50">Review text</h3>
            <p className="text-sm text-slate-400">
              Edit timings and lines, add or remove rows. {nonEmpty.length}{" "}
              {nonEmpty.length === 1 ? "line" : "lines"}.
            </p>
          </div>
        </div>
        {chunkBusy && (
          <span className="mt-1 h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-white/20 border-t-fuchsia-400" />
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="outline"
          loading={proofBusy}
          disabled={busy || proofBusy || nonEmpty.length === 0}
          icon={<CheckBadgeIcon className="h-4 w-4" />}
          onClick={runProofread}
        >
          Check spelling and punctuation
        </Button>
        {proofNote && <span className="text-xs text-slate-400">{proofNote}</span>}
      </div>

      {chunkError && (
        <p className="rounded-xl bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          {chunkError}
        </p>
      )}

      {overflowCount > 0 && (
        <div className="flex items-center gap-2 rounded-xl bg-amber-500/10 px-3 py-2 text-xs text-amber-300 ring-1 ring-amber-400/30">
          <ExclamationTriangleIcon className="h-4 w-4 shrink-0" />
          {overflowCount} {overflowCount === 1 ? "line doesn't" : "lines don't"}{" "}
          fit the frame width — shorten the text or reduce words per screen.
        </div>
      )}

      <div className="max-h-[28rem] space-y-2 overflow-y-auto pr-1">
        {segments.map((segment, index) => {
          const overflow = isOverflow(segment.text);
          return (
            <div
              key={index}
              className={`glass-soft rounded-2xl p-3 ${
                overflow ? "ring-1 ring-amber-400/40" : ""
              }`}
            >
              <div className="flex items-center gap-2">
                <input
                  key={`start-${index}-${segment.start}`}
                  defaultValue={formatTimestamp(segment.start)}
                  onBlur={(e) => updateTime(index, "start", e.target.value)}
                  disabled={busy}
                  className="w-28 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-center font-mono text-xs text-violet-200 outline-none focus:border-violet-400/50 focus:bg-white/10 disabled:opacity-50"
                />
                <span className="text-slate-500">→</span>
                <input
                  key={`end-${index}-${segment.end}`}
                  defaultValue={formatTimestamp(segment.end)}
                  onBlur={(e) => updateTime(index, "end", e.target.value)}
                  disabled={busy}
                  className="w-28 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-center font-mono text-xs text-fuchsia-200 outline-none focus:border-fuchsia-400/50 focus:bg-white/10 disabled:opacity-50"
                />
                {overflow && (
                  <span
                    className="flex items-center gap-1 text-[11px] text-amber-300"
                    title="Does not fit frame width"
                  >
                    <ExclamationTriangleIcon className="h-4 w-4" />
                  </span>
                )}
                <div className="ml-auto flex items-center gap-1">
                  <button
                    onClick={() => insertAfter(index)}
                    disabled={busy}
                    className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-white/10 hover:text-emerald-300 disabled:opacity-50"
                    aria-label="Add line below"
                  >
                    <PlusIcon className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => removeSegment(index)}
                    disabled={busy}
                    className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-white/10 hover:text-rose-300 disabled:opacity-50"
                    aria-label="Remove line"
                  >
                    <TrashIcon className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <textarea
                value={segment.text}
                onChange={(e) => updateText(index, e.target.value)}
                disabled={busy}
                rows={2}
                placeholder="Subtitle text…"
                className="mt-2 min-h-[2.75rem] w-full resize-y rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 outline-none transition-colors placeholder:text-slate-500 focus:border-violet-400/50 focus:bg-white/10 disabled:opacity-50"
              />
            </div>
          );
        })}
      </div>

      <button
        onClick={() => insertAfter(segments.length - 1)}
        disabled={busy}
        className="flex w-full items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-white/15 py-3 text-sm font-medium text-slate-300 transition-colors hover:border-white/30 hover:bg-white/[0.04] disabled:opacity-50"
      >
        <PlusIcon className="h-4 w-4" />
        Add line
      </button>

      <div className="glass-soft space-y-4 rounded-2xl p-4">
        <label className="flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={autoChunk}
            onChange={(e) => toggleKaraoke(e.target.checked)}
            disabled={busy}
            className="mt-0.5 h-5 w-5 shrink-0 accent-fuchsia-500 disabled:opacity-50"
          />
          <span>
            <span className="flex items-center gap-1.5 text-sm font-semibold text-slate-100">
              <SparklesIcon className="h-4 w-4 text-fuchsia-300" />
              Karaoke word split
            </span>
            <span className="mt-0.5 block text-xs text-slate-400">
              Splits lines into 1–{maxWords} words synced to speech and fills
              the review list above. Word count is tuned to frame width.
            </span>
          </span>
        </label>

        {autoChunk && (
          <div className="flex items-center gap-3 pl-8">
            <span className="text-xs text-slate-400">Max words on screen:</span>
            <div className="flex gap-1.5">
              {[1, 2, 3].map((n) => (
                <button
                  key={n}
                  onClick={() => changeMaxWords(n)}
                  disabled={busy || chunkBusy}
                  className={`flex h-8 w-8 items-center justify-center rounded-lg text-sm font-semibold transition-colors disabled:opacity-50 ${
                    maxWords === n
                      ? "bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white"
                      : "bg-white/5 text-slate-300 hover:bg-white/10"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="glass-soft flex flex-wrap items-center gap-3 rounded-2xl p-4">
        <span className="text-sm font-semibold text-slate-100">Subtitle font</span>
        <div className="flex flex-wrap gap-1.5">
          {fonts.map((font) => (
            <button
              key={font.name}
              onClick={() => setSelectedFont(font.name)}
              disabled={busy}
              style={{ fontFamily: `"${font.name}", sans-serif` }}
              className={`rounded-lg px-3 py-1.5 text-base transition-colors disabled:opacity-50 ${
                selectedFont === font.name
                  ? "bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white"
                  : "bg-white/5 text-slate-300 hover:bg-white/10"
              }`}
            >
              {font.label}
            </button>
          ))}
        </div>
      </div>

      {(() => {
        const preset =
          COLOR_PRESETS.find((p) => p.id === colorPreset) ?? COLOR_PRESETS[0];
        const toCss = (c: string) => (c === WHITE ? "#ffffff" : "#000000");
        const textColor = toCss(preset.primary);
        const maskColor = toCss(preset.outline);
        const isBox = maskStyle === 3;
        const previewStyle: React.CSSProperties = {
          fontFamily: `"${selectedFont}", sans-serif`,
          color: textColor,
          lineHeight: 1.2,
          display: "inline-block",
          ...(isBox
            ? {
                backgroundColor: maskColor,
                padding: `${2 + maskSize}px ${6 + maskSize * 2}px`,
                borderRadius: 2,
              }
            : maskSize > 0
              ? {
                  WebkitTextStroke: `${maskSize}px ${maskColor}`,
                  paintOrder: "stroke fill",
                }
              : {}),
        };
        return (
          <div className="glass-soft space-y-4 rounded-2xl p-4">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm font-semibold text-slate-100">Color</span>
              <div className="flex gap-1.5">
                {COLOR_PRESETS.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => setColorPreset(p.id)}
                    disabled={busy}
                    className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors disabled:opacity-50 ${
                      colorPreset === p.id
                        ? "bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white"
                        : "bg-white/5 text-slate-300 hover:bg-white/10"
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>

              <span className="ml-2 text-sm font-semibold text-slate-100">Mask</span>
              <div className="flex gap-1.5">
                <button
                  onClick={() => setMaskStyle(1)}
                  disabled={busy}
                  className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors disabled:opacity-50 ${
                    maskStyle === 1
                      ? "bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white"
                      : "bg-white/5 text-slate-300 hover:bg-white/10"
                  }`}
                >
                  Outline
                </button>
                <button
                  onClick={() => setMaskStyle(3)}
                  disabled={busy}
                  className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors disabled:opacity-50 ${
                    maskStyle === 3
                      ? "bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white"
                      : "bg-white/5 text-slate-300 hover:bg-white/10"
                  }`}
                >
                  Box
                </button>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm font-semibold text-slate-100">
                Mask size
              </span>
              <input
                type="range"
                min={0}
                max={10}
                step={1}
                value={maskSize}
                disabled={busy}
                onChange={(e) => setMaskSize(Number(e.target.value))}
                className="h-2 w-40 cursor-pointer accent-fuchsia-500 disabled:opacity-50"
              />
              <span className="w-6 text-center text-sm text-slate-300">
                {maskSize}
              </span>
            </div>

            <div className="flex items-center justify-center rounded-xl bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2216%22 height=%2216%22><rect width=%228%22 height=%228%22 fill=%22%23334%22/><rect x=%228%22 y=%228%22 width=%228%22 height=%228%22 fill=%22%23334%22/></svg>')] p-6">
              <span
                className="text-3xl leading-none"
                style={previewStyle}
              >
                Sample subtitle text
              </span>
            </div>
          </div>
        );
      })()}

      <Button
        size="lg"
        className="w-full"
        loading={busy}
        disabled={busy || chunkBusy || nonEmpty.length === 0}
        icon={<CheckIcon className="h-5 w-5" />}
        onClick={handleConfirm}
      >
        Approve and burn subtitles
      </Button>
    </GlassCard>
  );
}
