import { CheckIcon, XMarkIcon } from "@heroicons/react/24/solid";
import clsx from "clsx";
import type { Step } from "../lib/types";

interface StepperProps {
  steps: Step[];
  currentStage: string | null;
  failed?: boolean;
}

export function Stepper({ steps, currentStage, failed }: StepperProps) {
  const order = steps.map((s) => s.stage);
  const completed = currentStage === "completed";
  const currentIndex = completed
    ? steps.length
    : order.indexOf(currentStage ?? "");

  return (
    <ol className="flex flex-col gap-1 sm:flex-row sm:items-start sm:gap-0">
      {steps.map((step, index) => {
        let state: "done" | "active" | "pending" | "error" = "pending";
        if (completed) state = "done";
        else if (failed && index === Math.max(currentIndex, 0)) state = "error";
        else if (index < currentIndex) state = "done";
        else if (index === currentIndex) state = "active";

        return (
          <li key={step.stage} className="flex flex-1 items-center gap-3 sm:flex-col sm:gap-2">
            <div className="flex w-full items-center sm:flex-col">
              <div className="flex items-center gap-3 sm:w-full sm:flex-col sm:gap-0">
                <span
                  className={clsx(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border text-sm font-bold transition-all duration-300",
                    state === "done" &&
                      "border-transparent bg-gradient-to-br from-emerald-400 to-teal-500 text-white",
                    state === "active" &&
                      "border-violet-400/60 bg-violet-500/20 text-violet-200 shadow-glow",
                    state === "pending" && "border-white/10 bg-white/5 text-slate-500",
                    state === "error" &&
                      "border-transparent bg-gradient-to-br from-rose-500 to-red-600 text-white",
                  )}
                >
                  {state === "done" ? (
                    <CheckIcon className="h-5 w-5" />
                  ) : state === "error" ? (
                    <XMarkIcon className="h-5 w-5" />
                  ) : state === "active" ? (
                    <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-violet-300" />
                  ) : (
                    index + 1
                  )}
                </span>
              </div>
              {index < steps.length - 1 && (
                <span
                  className={clsx(
                    "mx-2 hidden h-0.5 flex-1 rounded-full transition-colors duration-500 sm:block",
                    index < currentIndex
                      ? "bg-gradient-to-r from-emerald-400/70 to-teal-500/40"
                      : "bg-white/10",
                  )}
                />
              )}
            </div>
            <span
              className={clsx(
                "text-xs font-medium transition-colors sm:mt-1 sm:text-center",
                state === "active"
                  ? "text-slate-100"
                  : state === "done"
                    ? "text-slate-300"
                    : state === "error"
                      ? "text-rose-300"
                      : "text-slate-500",
              )}
            >
              {step.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
