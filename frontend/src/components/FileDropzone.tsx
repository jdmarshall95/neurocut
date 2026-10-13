import { useCallback, useRef, useState } from "react";
import {
  ArrowUpTrayIcon,
  FilmIcon,
  PlusIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import clsx from "clsx";

const ACCEPT = ".mp4,.mov,.mkv,.avi,.webm";
const ACCEPT_TYPES = ["mp4", "mov", "mkv", "avi", "webm"];

interface FileDropzoneProps {
  files: File[];
  onChange: (files: File[]) => void;
  disabled?: boolean;
}

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function fileKey(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function isAccepted(file: File): boolean {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  return ACCEPT_TYPES.includes(ext);
}

function mergeFiles(existing: File[], incoming: File[]): File[] {
  const map = new Map<string, File>();
  for (const file of existing) map.set(fileKey(file), file);
  for (const file of incoming) {
    if (isAccepted(file)) map.set(fileKey(file), file);
  }
  return Array.from(map.values());
}

export function FileDropzone({ files, onChange, disabled }: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const addFiles = useCallback(
    (incoming: FileList | null) => {
      if (!incoming || incoming.length === 0) return;
      onChange(mergeFiles(files, Array.from(incoming)));
    },
    [files, onChange],
  );

  const removeFile = (target: File) => {
    onChange(files.filter((f) => fileKey(f) !== fileKey(target)));
  };

  if (files.length > 0) {
    return (
      <div className="space-y-3">
        <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
          {files.map((file) => (
            <div
              key={fileKey(file)}
              className="glass-soft flex items-center gap-4 rounded-2xl p-4"
            >
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white">
                <FilmIcon className="h-6 w-6" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate font-semibold text-slate-100">
                  {file.name}
                </div>
                <div className="text-xs text-slate-400">
                  {formatSize(file.size)}
                </div>
              </div>
              {!disabled && (
                <button
                  onClick={() => removeFile(file)}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-slate-400 transition-colors hover:bg-white/10 hover:text-slate-100"
                  aria-label={`Remove ${file.name}`}
                >
                  <XMarkIcon className="h-5 w-5" />
                </button>
              )}
            </div>
          ))}
        </div>

        {!disabled && (
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-white/15 bg-white/[0.03] px-4 py-3 text-sm font-medium text-slate-300 transition-colors hover:border-white/25 hover:bg-white/[0.06] hover:text-slate-100"
          >
            <PlusIcon className="h-4 w-4" />
            Add more clips
          </button>
        )}

        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="hidden"
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = "";
          }}
        />

        <p className="text-center text-xs text-slate-500">
          {files.length} {files.length === 1 ? "clip" : "clips"} — each runs as
          a separate job
        </p>
      </div>
    );
  }

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (!disabled) addFiles(e.dataTransfer.files);
      }}
      className={clsx(
        "group flex w-full flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-all duration-200",
        dragging
          ? "border-violet-400/70 bg-violet-500/10"
          : "border-white/15 bg-white/[0.03] hover:border-white/25 hover:bg-white/[0.06]",
        disabled && "cursor-not-allowed opacity-50",
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        multiple
        className="hidden"
        onChange={(e) => {
          addFiles(e.target.files);
          e.target.value = "";
        }}
      />
      <span
        className={clsx(
          "flex h-14 w-14 items-center justify-center rounded-2xl transition-all duration-200",
          dragging
            ? "scale-110 bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white"
            : "bg-white/5 text-slate-300 group-hover:scale-105",
        )}
      >
        <ArrowUpTrayIcon className="h-6 w-6" />
      </span>
      <div>
        <div className="font-semibold text-slate-100">
          Drop video here or click to browse
        </div>
        <div className="mt-1 text-xs text-slate-400">
          MP4 · MOV · MKV · AVI · WebM · multiple files supported
        </div>
      </div>
    </button>
  );
}
