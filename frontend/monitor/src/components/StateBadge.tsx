type Badge = {
  color?: "green" | "yellow";
  converged?: boolean;
  desired?: string | null;
  observed?: string | null;
  text?: string | null;
};

export default function StateBadge({ badge }: { badge: Badge }) {
  const className = `state-badge state-${badge.color}`;
  const text = badge.text || badge.observed;
  const tooltip = badge.converged ? "Converged" : `${badge.observed} -> ${badge.desired}`;

  return (
    <span className={className} title={tooltip}>
      {text}
    </span>
  );
}
