import { useFileList } from '@/hooks/useFileList';

interface FileBrowserProps {
  threadId: string;
}

export function FileBrowser({ threadId }: FileBrowserProps) {
  const { files, loading, error } = useFileList(threadId);

  if (loading) return <div>Loading files...</div>;
  if (error) return <div>Error: {error}</div>;
  if (files.length === 0) return <div>No files uploaded</div>;

  return (
    <div className="space-y-2">
      {files.map((file) => (
        <div key={file.relative_path} className="flex items-center justify-between p-2 border rounded">
          <span>{file.relative_path}</span>
          <span className="text-sm text-gray-500">{(file.size_bytes / 1024).toFixed(1)} KB</span>
        </div>
      ))}
    </div>
  );
}
