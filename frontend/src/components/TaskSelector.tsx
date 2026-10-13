import { Radio, RadioGroup } from "@headlessui/react";
import {
  DocumentTextIcon,
  FilmIcon,
  DevicePhoneMobileIcon,
  SparklesIcon,
  LanguageIcon,
} from "@heroicons/react/24/outline";
import clsx from "clsx";
import type { TaskId } from "../lib/types";

interface TaskOption {
  id: TaskId;
  label: string;
  description: string;
  icon: typeof FilmIcon;
}

export const TASKS: TaskOption[] = [
  {
    id: "transcribe",
    label: "Transcription",
    description: "Speech recognition with timecodes. Export TXT / SRT / JSON.",
    icon: DocumentTextIcon,
  },
  {
    id: "render_clip",
    label: "Turnkey clip",
    description: "AI edits and stitches a finished MP4 from your editing brief.",
    icon: SparklesIcon,
  },
  {
    id: "subtitles",
    label: "Subtitles",
    description: "Recognize speech, review text, and burn subtitles into video.",
    icon: LanguageIcon,
  },
  {
    id: "cut_xml",
    label: "NLE edit",
    description: "FCP7 XML + source video in a ZIP for Premiere Pro / DaVinci.",
    icon: FilmIcon,
  },
  {
    id: "cut_clips",
    label: "Mobile clips",
    description: "FFmpeg splits ready MP4 clips and packs them into a ZIP.",
    icon: DevicePhoneMobileIcon,
  },
];

interface TaskSelectorProps {
  value: TaskId;
  onChange: (value: TaskId) => void;
  disabled?: boolean;
}

export function TaskSelector({ value, onChange, disabled }: TaskSelectorProps) {
  return (
    <RadioGroup
      value={value}
      onChange={onChange}
      disabled={disabled}
      className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
    >
      {TASKS.map((task) => {
        const Icon = task.icon;
        return (
          <Radio
            key={task.id}
            value={task.id}
            className={clsx(
              "group relative cursor-pointer rounded-2xl p-4 transition-all duration-200 focus:outline-none",
              "glass-soft hover:-translate-y-0.5 hover:border-white/20",
              "data-[checked]:border-violet-400/50 data-[checked]:bg-violet-500/10 data-[checked]:shadow-glow",
              "data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50",
            )}
          >
            <div className="flex items-start gap-3">
              <span
                className={clsx(
                  "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors",
                  "bg-white/5 text-slate-300",
                  "group-data-[checked]:bg-gradient-to-br group-data-[checked]:from-indigo-500 group-data-[checked]:to-fuchsia-500 group-data-[checked]:text-white",
                )}
              >
                <Icon className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <div className="font-semibold text-slate-100">{task.label}</div>
                <div className="mt-1 text-xs leading-relaxed text-slate-400">
                  {task.description}
                </div>
              </div>
            </div>
            <span className="pointer-events-none absolute right-3 top-3 h-2.5 w-2.5 rounded-full bg-white/10 transition-all group-data-[checked]:bg-gradient-to-r group-data-[checked]:from-violet-400 group-data-[checked]:to-fuchsia-400 group-data-[checked]:shadow-glow" />
          </Radio>
        );
      })}
    </RadioGroup>
  );
}
