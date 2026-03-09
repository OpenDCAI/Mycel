import { useFileList } from '@/hooks/useFileList';
import { MoreVertical } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';

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
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500">{(file.size_bytes / 1024).toFixed(1)} KB</span>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" aria-label="File actions">
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem>Download</DropdownMenuItem>
                <DropdownMenuItem className="text-red-600">Delete</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      ))}
    </div>
  );
}
