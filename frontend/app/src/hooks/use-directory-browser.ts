import { useState } from "react";
import { authFetch } from "../store/auth-store";

export interface BrowseItem {
  name: string;
  path: string;
  is_dir: boolean;
}

/**
 * Shared state machine for directory browsing.
 * Caller provides a URL-builder so the hook stays generic.
 */
export function useDirectoryBrowser(buildUrl: (path: string) => string, initialPath: string) {
  const [currentPath, setCurrentPath] = useState(initialPath);
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [items, setItems] = useState<BrowseItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadPath(path: string) {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(buildUrl(path));
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error((d as { detail?: string }).detail || "加载失败");
      }
      const data = await res.json();
      setCurrentPath((data.current_path as string) ?? path);
      setParentPath((data.parent_path as string | null) ?? null);
      setItems((data.items as BrowseItem[]) ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  return { currentPath, parentPath, items, loading, error, loadPath };
}
