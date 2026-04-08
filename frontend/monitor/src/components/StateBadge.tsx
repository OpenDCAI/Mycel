export default function StateBadge({ badge }: { badge: any }) {
  const className = `state-badge state-${badge.color}`;
  const text = badge.text || badge.observed;
  const tooltip = badge.hours_diverged
    ? `Diverged for ${badge.hours_diverged}h`
    : badge.converged
      ? "Converged"
      : `${badge.observed} → ${badge.desired}`;

  return (
    <span className={className} title={tooltip}>
      {text}
    </span>
  );
}
