// @@@waterline — visual separator when owner steers into an external run
export function WaterlineDivider() {
  return (
    <div className="flex items-center gap-3 py-2">
      <div className="flex-1 h-px bg-border" />
      <span className="text-[10px] text-muted-foreground/50 uppercase tracking-wider shrink-0">
        owner intervention
      </span>
      <div className="flex-1 h-px bg-border" />
    </div>
  );
}
