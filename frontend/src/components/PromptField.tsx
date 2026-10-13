import { Field, Label, Textarea } from "@headlessui/react";
import { SparklesIcon } from "@heroicons/react/24/outline";

const EXAMPLES = [
  "Punchy ~60s clip — cut pauses and filler",
  "Keep only key points, add zoom markers",
  "Cut Reels highlights, vertical pacing",
];

interface PromptFieldProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function PromptField({ value, onChange, disabled }: PromptFieldProps) {
  return (
    <Field disabled={disabled} className="space-y-3">
      <Label className="flex items-center gap-2 text-sm font-semibold text-slate-200">
        <SparklesIcon className="h-4 w-4 text-violet-300" />
        Editing brief
      </Label>
      <Textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={5}
        placeholder="Describe the edit: target length, what to keep or cut, where to place markers…"
        className="w-full resize-y rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm leading-relaxed text-slate-100 outline-none transition-colors placeholder:text-slate-500 focus:border-violet-400/50 focus:bg-white/10 data-[disabled]:opacity-50"
      />
      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            disabled={disabled}
            onClick={() => onChange(example)}
            className="glass-soft rounded-full px-3 py-1.5 text-xs text-slate-300 transition-colors hover:border-white/20 hover:text-slate-100 disabled:opacity-50"
          >
            {example}
          </button>
        ))}
      </div>
    </Field>
  );
}
