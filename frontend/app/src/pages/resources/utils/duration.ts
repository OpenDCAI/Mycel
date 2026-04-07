export function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 0) return `${days}天${hours % 24}小时`;
  if (hours > 0) return `${hours}小时${minutes % 60}分`;
  if (minutes > 0) return `${minutes}分${seconds % 60}秒`;
  return `${seconds}秒`;
}

export function calculateDuration(createdAt: string): number | null {
  const startedAt = new Date(createdAt).getTime();
  if (Number.isNaN(startedAt)) {
    return null;
  }

  const elapsed = Date.now() - startedAt;
  return elapsed >= 0 ? elapsed : null;
}

export function formatStartedAtDuration(createdAt: string | null | undefined): string | null {
  if (!createdAt) {
    return null;
  }

  const elapsed = calculateDuration(createdAt);
  return elapsed == null ? "时间异常" : formatDuration(elapsed);
}
