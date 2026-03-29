import { useState, useEffect, useCallback } from 'react';
import { authRequest } from '../store/auth-store';

interface FileEntry {
  relative_path: string;
  size_bytes: number;
  updated_at: string;
}

interface ChannelFilesResponse {
  thread_id: string;
  entries: FileEntry[];
}

export function useFileList(threadId: string) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchFiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await authRequest<ChannelFilesResponse>(`/api/threads/${threadId}/files/channel-files`);
      setFiles(data.entries || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [threadId]);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  return { files, loading, error, refetch: fetchFiles };
}
