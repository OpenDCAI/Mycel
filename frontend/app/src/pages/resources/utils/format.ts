/**
 * Shared formatting utilities for resource metrics
 */

export function formatNumber(value: number | null | undefined, nullText: string = "--"): string {
  if (value == null) {
    return nullText;
  }
  if (Number.isInteger(value)) {
    return String(value);
  }
  return value.toFixed(1).replace(/\.0$/, "");
}

export function formatMetric(value: number | null | undefined, unit: string): string {
  if (value == null) return "--";
  // Auto-scale GB to MB for sub-1GB values (e.g. 0.03 GB → "31MB" instead of "0GB")
  if (unit === "GB" && value > 0 && value < 1) {
    return `${Math.round(value * 1024)}MB`;
  }
  return `${formatNumber(value)}${unit}`;
}

export function formatLimit(limit: number | null | undefined, unit: string, nullText: string = "--"): string {
  if (limit == null) {
    return `limit: ${nullText} ${unit}`;
  }
  return `limit: ${formatNumber(limit)} ${unit}`;
}
