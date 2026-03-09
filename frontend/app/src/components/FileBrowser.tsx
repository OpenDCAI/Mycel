import { useState } from 'react';
import { useFileList } from '@/hooks/useFileList';
import { MoreVertical } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

interface FileBrowserProps {
  threadId: string;
}

export function FileBrowser({ threadId }: FileBrowserProps) {
  const { files, loading, error, refetch } = useFileList(threadId);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const handleDownload = (path: string) => {
    const url = `/api/threads/${threadId}/workspace/download?path=${encodeURIComponent(path)}`;
    window.open(url, '_blank');
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const res = await fetch(
        `/api/threads/${threadId}/workspace/files?path=${encodeURIComponent(deleteTarget)}`,
        { method: 'DELETE' }
      );
      if (!res.ok) throw new Error('Failed to delete file');
      await refetch();
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to delete file');
    } finally {
      setDeleting(false);
      setDeleteTarget(null);
    }
  };

  if (loading) return <div>Loading files...</div>;
  if (error) return <div>Error: {error}</div>;
  if (files.length === 0) return <div>No files uploaded</div>;

  return (
    <>
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
                  <DropdownMenuItem onClick={() => handleDownload(file.relative_path)}>Download</DropdownMenuItem>
                  <DropdownMenuItem className="text-red-600" onClick={() => setDeleteTarget(file.relative_path)} disabled={deleting}>Delete</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        ))}
      </div>

      <AlertDialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete file?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete "{deleteTarget}"? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} disabled={deleting}>
              {deleting ? 'Deleting...' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
