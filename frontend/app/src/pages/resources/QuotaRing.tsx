interface QuotaRingProps {
  used: number;
  limit: number;
  size?: number;
}

export default function QuotaRing({ used, limit, size = 48 }: QuotaRingProps) {
  const pct = Math.min(Math.round((used / limit) * 100), 100);
  const r = (size - 6) / 2;
  const circumference = 2 * Math.PI * r;
  const offset = circumference - (pct / 100) * circumference;

  const strokeColor =
    pct > 80
      ? "hsl(var(--destructive))"
      : pct > 50
        ? "hsl(var(--warning))"
        : "hsl(var(--foreground))";

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="hsl(var(--border))"
          strokeWidth={3}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={strokeColor}
          strokeWidth={3}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-deliberate ease-out-expo"
        />
      </svg>
      <span className="absolute text-xs font-mono font-bold text-foreground">
        {pct}
      </span>
    </div>
  );
}
