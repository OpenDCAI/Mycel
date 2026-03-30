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
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => loadPath("~")}
          title="返回主目录"
          className="h-7 px-2"
        >
          <Home className="h-3 w-3" />
        </Button>
        <div className="flex-1 text-xs text-muted-foreground truncate">
          {currentPath}
        </div>
      </div>

      <ScrollArea className="h-[220px]">
        <div className="space-y-0.5">
          {loading && (
            <div className="py-4 text-center text-xs text-muted-foreground">
              加载中...
            </div>
          )}

          {error && (
            <div className="py-4 text-center text-xs text-red-500">{error}</div>
          )}

          {!loading && !error && items.length === 0 && (
            <div className="py-4 text-center text-xs text-muted-foreground">
              此目录为空
            </div>
          )}

          {!loading && !error && parentPath && (
            <button
              onClick={() => loadPath(parentPath)}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-xs hover:bg-accent"
            >
              <Folder className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="flex-1 text-left">..</span>
            </button>
          )}

          {!loading &&
            !error &&
            items.map((item) => (
              <button
                key={item.path}
                onClick={() => loadPath(item.path)}
                className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-xs hover:bg-accent"
              >
                <Folder className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="flex-1 text-left truncate">{item.name}</span>
                <ChevronRight className="h-3 w-3 text-muted-foreground" />
              </button>
            ))}
        </div>
      </ScrollArea>

      <Button onClick={() => onSelect(currentPath)} className="h-8 w-full text-xs" disabled={loading}>
        选择此目录
      </Button>
    </div>
  );
}
