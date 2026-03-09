import { ChevronRight, Folder, Home } from "lucide-react";
import { useEffect } from "react";
import { Button } from "./ui/button";
import { ScrollArea } from "./ui/scroll-area";
import { useDirectoryBrowser } from "../hooks/use-directory-browser";

interface FilesystemBrowserProps {
  onSelect: (path: string) => void;
  initialPath?: string;
}

export default function FilesystemBrowser({
  onSelect,
  initialPath = "~",
}: FilesystemBrowserProps) {
  const buildUrl = (path: string) =>
    `/api/settings/browse?path=${encodeURIComponent(path)}`;

  const { currentPath, parentPath, items, loading, error, loadPath } =
    useDirectoryBrowser(buildUrl, initialPath);

  useEffect(() => {
    void loadPath(initialPath);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPath]);

  return (
    <div className="space-y-3">
      {/* Current Path */}
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => loadPath("~")}
          title="返回主目录"
        >
          <Home className="h-3.5 w-3.5" />
        </Button>
        <div className="flex-1 text-sm text-muted-foreground truncate">
          {currentPath}
        </div>
      </div>

      {/* Parent Directory */}
      {parentPath && (
        <button
          onClick={() => loadPath(parentPath)}
          className="w-full flex items-center gap-2 px-2 py-1.5 text-sm hover:bg-accent rounded-md"
        >
          <Folder className="h-4 w-4 text-muted-foreground" />
          <span>..</span>
        </button>
      )}

      {/* Directory List */}
      <ScrollArea className="h-[300px] border rounded-md">
        <div className="p-2 space-y-1">
          {loading && (
            <div className="text-sm text-muted-foreground text-center py-4">
              加载中...
            </div>
          )}

          {error && (
            <div className="text-sm text-red-500 text-center py-4">{error}</div>
          )}

          {!loading && !error && items.length === 0 && (
            <div className="text-sm text-muted-foreground text-center py-4">
              此目录为空
            </div>
          )}

          {!loading &&
            !error &&
            items.map((item) => (
              <button
                key={item.path}
                onClick={() => loadPath(item.path)}
                className="w-full flex items-center gap-2 px-2 py-1.5 text-sm hover:bg-accent rounded-md"
              >
                <Folder className="h-4 w-4 text-muted-foreground" />
                <span className="flex-1 text-left truncate">{item.name}</span>
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
              </button>
            ))}
        </div>
      </ScrollArea>

      {/* Select Button */}
      <Button onClick={() => onSelect(currentPath)} className="w-full" disabled={loading}>
        选择此目录
      </Button>
    </div>
  );
}
