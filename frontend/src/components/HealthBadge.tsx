import { useEffect, useState } from "react";
import { Button, Description, Dialog, DialogPanel, DialogTitle } from "@headlessui/react";
import { Cog6ToothIcon, SignalIcon, SignalSlashIcon } from "@heroicons/react/24/outline";
import clsx from "clsx";
import { checkHealth, getApiBaseUrl, setApiBaseUrl } from "../lib/api";

export function HealthBadge() {
  const [online, setOnline] = useState<boolean | null>(null);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(getApiBaseUrl());
  const [baseUrl, setBaseUrl] = useState(getApiBaseUrl());

  useEffect(() => {
    let active = true;
    const ping = async () => {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 3000);
      const ok = await checkHealth(controller.signal);
      clearTimeout(timeout);
      if (active) setOnline(ok);
    };
    ping();
    const interval = setInterval(ping, 15_000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [baseUrl]);

  const save = () => {
    setApiBaseUrl(draft);
    setBaseUrl(getApiBaseUrl());
    setOnline(null);
    setOpen(false);
  };

  const statusColor =
    online === null ? "bg-amber-400" : online ? "bg-emerald-400" : "bg-rose-400";
  const statusLabel =
    online === null ? "Checking…" : online ? "API online" : "API offline";

  return (
    <>
      <button
        onClick={() => {
          setDraft(getApiBaseUrl());
          setOpen(true);
        }}
        className="glass-soft group flex items-center gap-2.5 rounded-full py-1.5 pl-2.5 pr-3 text-sm transition-all hover:border-white/20"
      >
        <span className="relative flex h-2.5 w-2.5">
          {online && (
            <span
              className={clsx(
                "absolute inline-flex h-full w-full animate-ping rounded-full opacity-75",
                statusColor,
              )}
            />
          )}
          <span
            className={clsx("relative inline-flex h-2.5 w-2.5 rounded-full", statusColor)}
          />
        </span>
        <span className="font-medium text-slate-200">{statusLabel}</span>
        {online ? (
          <SignalIcon className="h-4 w-4 text-slate-400" />
        ) : (
          <SignalSlashIcon className="h-4 w-4 text-slate-400" />
        )}
        <Cog6ToothIcon className="h-4 w-4 text-slate-500 transition-transform group-hover:rotate-45" />
      </button>

      <Dialog open={open} onClose={setOpen} className="relative z-50">
        <div className="fixed inset-0 bg-ink-950/70 backdrop-blur-sm" aria-hidden />
        <div className="fixed inset-0 flex items-center justify-center p-4">
          <DialogPanel className="glass-strong w-full max-w-md rounded-3xl p-6 animate-fade-in-up">
            <DialogTitle className="text-lg font-bold text-slate-50">
              Connection settings
            </DialogTitle>
            <Description className="mt-1 text-sm text-slate-400">
              FastAPI server URL. Requests run from the browser, so this is usually
              <code className="mx-1 rounded bg-white/10 px-1.5 py-0.5 text-xs">
                http://127.0.0.1:8000
              </code>
              .
            </Description>
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="http://127.0.0.1:8000"
              className="mt-4 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-100 outline-none transition-colors placeholder:text-slate-500 focus:border-violet-400/50 focus:bg-white/10"
            />
            <div className="mt-5 flex justify-end gap-2">
              <Button
                onClick={() => setOpen(false)}
                className="rounded-2xl px-4 py-2.5 text-sm font-semibold text-slate-300 transition-colors hover:bg-white/10"
              >
                Cancel
              </Button>
              <Button
                onClick={save}
                className="btn-gradient rounded-2xl px-5 py-2.5 text-sm font-semibold text-white shadow-glow transition-transform hover:-translate-y-0.5"
              >
                Save
              </Button>
            </div>
          </DialogPanel>
        </div>
      </Dialog>
    </>
  );
}
