import { useState } from "react";
import { asRecord, recordString } from "@/lib/records";

export interface BrowseItem {
  name: string;
  path: string;
  is_dir: boolean;
}

function parseBrowseItems(value: unknown): BrowseItem[] {
  if (!Array.isArray(value)) {
    throw new Error("Malformed directory browser payload: items must be an array");
  }
  return value.map((item, index) => {
    const record = asRecord(item);
    if (!record || typeof record.is_dir !== "boolean") {
      throw new Error(`Malformed directory browser payload: items[${index}]`);
    }
    const name = recordString(record, "name");
    const path = recordString(record, "path");
    if (!name || !path) {
      throw new Error(`Malformed directory browser payload: items[${index}]`);
    }
    return { name, path, is_dir: record.is_dir };
  });
}

function parseBrowsePayload(value: unknown, requestedPath: string): { currentPath: string; parentPath: string | null; items: BrowseItem[] } {
  const payload = asRecord(value);
  if (!payload) {
    throw new Error("Malformed directory browser payload: expected object");
  }
  const currentPath = recordString(payload, "current_path") ?? requestedPath;
  const rawParentPath = payload.parent_path;
  let parentPath: string | null = null;
  if (rawParentPath !== null && rawParentPath !== undefined) {
    const parsedParentPath = recordString(payload, "parent_path");
    if (parsedParentPath === undefined) {
      throw new Error("Malformed directory browser payload: parent_path must be a string or null");
    }
    parentPath = parsedParentPath;
  }
  return {
    currentPath,
    parentPath,
    items: parseBrowseItems(payload.items),
  };
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
      const res = await fetch(buildUrl(path));
      if (!res.ok) {
        const errorPayload = asRecord(await res.json().catch(() => null));
        const detail = errorPayload ? recordString(errorPayload, "detail") : undefined;
        throw new Error(detail || "加载失败");
      }
      const data = parseBrowsePayload(await res.json(), path);
      setCurrentPath(data.currentPath);
      setParentPath(data.parentPath);
      setItems(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  return { currentPath, parentPath, items, loading, error, loadPath };
}
