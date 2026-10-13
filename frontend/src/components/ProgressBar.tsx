import clsx from "clsx";

interface ProgressBarProps {
  percent: number;
  failed?: boolean;
}

export function ProgressBar({ percent, failed }: ProgressBarProps) {
  const value = Math.max(0, Math.min(100, percent));
  return (
    <div className="h-2.5 w-full overflow-hidden rounded-full bg-white/5">
      <div
        className={clsx(
          "h-full rounded-full transition-[width] duration-500 ease-out",
          failed
            ? "bg-gradient-to-r from-rose-500 to-red-600"
            : "bg-gradient-to-r from-indigo-400 via-violet-400 to-fuchsia-400",
        )}
        style={{
          width: `${value}%`,
          backgroundSize: failed ? undefined : "200% 100%",
        }}
      >
        {!failed && value < 100 && (
          <div className="h-full w-full animate-shimmer bg-gradient-to-r from-transparent via-white/30 to-transparent bg-[length:200%_100%]" />
        )}
      </div>
    </div>
  );
}
