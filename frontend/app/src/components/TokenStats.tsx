import type { StreamStatus } from "../api";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function formatCost(c: number): string {
  if (c < 0.01) return "<$0.01";
  return `$${c.toFixed(2)}`;
}

interface TokenStatsProps {
  runtimeStatus: StreamStatus | null;
}

export default function TokenStats({ runtimeStatus }: TokenStatsProps) {
  const tokens = runtimeStatus?.tokens;
  const context = runtimeStatus?.context;

  if (!tokens) {
    return null;
  }

  return (
    <div className="bg-background pb-3">
      <div className="max-w-3xl mx-auto px-6">
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
          {context && (
            <>
              <span>上下文: {formatTokens(context.estimated_tokens)} ({context.usage_percent}%)</span>
              {context.near_limit && (
                <span className="text-amber-500 font-medium">接近上限</span>
              )}
            </>
          )}
          <span>费用: {formatCost(tokens.cost)}</span>
          <span className="text-muted-foreground/60">累计: {formatTokens(tokens.total_tokens)}</span>
        </div>
      </div>
    </div>
  );
}
