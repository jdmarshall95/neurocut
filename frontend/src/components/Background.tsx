export function Background() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-ink-950"
    >
      {/* Base radial vignette */}
      <div className="absolute inset-0 bg-[radial-gradient(120%_120%_at_50%_-10%,#1a1533_0%,#0b0b16_45%,#070711_100%)]" />

      {/* Aurora gradient blobs */}
      <div className="absolute -left-32 -top-40 h-[42rem] w-[42rem] rounded-full bg-violet-600/30 blur-[120px] animate-aurora-drift" />
      <div className="absolute -right-40 top-10 h-[38rem] w-[38rem] rounded-full bg-fuchsia-500/25 blur-[130px] animate-aurora-drift-slow animate-delay-2000" />
      <div className="absolute bottom-[-18rem] left-1/3 h-[44rem] w-[44rem] rounded-full bg-cyan-500/20 blur-[140px] animate-aurora-drift animate-delay-4000" />
      <div className="absolute left-1/2 top-1/3 h-[26rem] w-[26rem] -translate-x-1/2 rounded-full bg-indigo-500/20 blur-[110px] animate-aurora-drift-slow" />

      {/* Fine grid */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.03)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.03)_1px,transparent_1px)] bg-[length:56px_56px] [mask-image:radial-gradient(80%_60%_at_50%_0%,#000_20%,transparent_80%)]" />

      {/* Noise / film grain */}
      <div className="absolute inset-0 bg-noise opacity-[0.18] mix-blend-soft-light" />
    </div>
  );
}
