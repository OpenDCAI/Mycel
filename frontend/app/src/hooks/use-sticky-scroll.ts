import { useCallback, useEffect, useRef, useState } from "react";

const THRESHOLD = 50;

export function useStickyScroll<T extends HTMLElement>() {
  const [el, setEl] = useState<T | null>(null);
  const stuckRef = useRef(true);
  const ref = useCallback((node: T | null) => setEl(node), []);

  useEffect(() => {
    if (!el) return;
    const onScroll = () => {
      stuckRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < THRESHOLD;
    };
    const onMutate = () => {
      if (stuckRef.current) el.scrollTop = el.scrollHeight;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    const mo = new MutationObserver(onMutate);
    mo.observe(el, { childList: true, subtree: true });
    return () => { el.removeEventListener("scroll", onScroll); mo.disconnect(); };
  }, [el]);

  return ref;
}
