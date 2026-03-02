export function DragHandle({ onMouseDown }: { onMouseDown: (e: React.MouseEvent) => void }) {
  return (
    <div
      className="w-1 flex-shrink-0 cursor-col-resize hover:bg-neutral-300 active:bg-neutral-400 transition-colors"
      onMouseDown={onMouseDown}
    />
  );
}
