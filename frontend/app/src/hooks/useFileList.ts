import { useState, useEffect } from 'react';

interface FileEntry {
  relative_path: string;
  size_bytes: number;
  updated_at: string;
}

export function useFileList(threadId: string | undefined) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchFiles = async () => {
    if (!threadId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/threads/${threadId}/workspace/channel-files`);
      if (!res.ok) throw new Error('Failed to fetch files');
      const data = await res.json();
      setFiles(data.entries || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles();
  }, [threadId]);

  return { files, loading, error, refetch: fetchFiles };
}
