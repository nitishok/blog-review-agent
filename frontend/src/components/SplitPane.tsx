import { useCallback, useRef, useState } from "react";

interface Props {
  left: React.ReactNode;
  right: React.ReactNode;
}

export default function SplitPane({ left, right }: Props) {
  const [splitPct, setSplitPct] = useState(50);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const onMouseDown = useCallback(() => {
    dragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const pct = ((e.clientX - rect.left) / rect.width) * 100;
    setSplitPct(Math.min(80, Math.max(20, pct)));
  }, []);

  const onMouseUp = useCallback(() => {
    dragging.current = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }, []);

  return (
    <div
      className="split-pane"
      ref={containerRef}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
    >
      <div className="split-left" style={{ width: `${splitPct}%` }}>
        {left}
      </div>
      <div className="split-handle" onMouseDown={onMouseDown} />
      <div className="split-right" style={{ width: `${100 - splitPct}%` }}>
        {right}
      </div>
    </div>
  );
}
