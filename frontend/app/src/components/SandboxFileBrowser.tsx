import { File, Folder, Home, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useDirectoryBrowser } from "../hooks/use-directory-browser";
import { ScrollArea } from "./ui/scroll-area";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "./ui/resizable";

interface SandboxFileBrowserProps {
  leaseId: string;
  providerType: string;
  className?: string;
}

export function SandboxFileBrowser({ leaseId, providerType, className = "h-[300px]" }: SandboxFileBrowserProps) {
  const isLocal = providerType === "local" || !leaseId;
  const defaultPath = isLocal ? "~" : "/";

  const buildBrowseUrl = (path: string) =>
    isLocal
      ? `/api/settings/browse?path=${encodeURIComponent(path)}&include_files=true`
      : `/api/monitor/sandbox/${leaseId}/browse?path=${encodeURIComponent(path)}`;

  const buildReadUrl = (path: string) =>
    isLocal
      ? `/api/settings/read?path=${encodeURIComponent(path)}`
      : `/api/monitor/sandbox/${leaseId}/read?path=${encodeURIComponent(path)}`;

  const { currentPath, parentPath, items, loading, error, loadPath } =
    useDirectoryBrowser(buildBrowseUrl, defaultPath);

  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);

  useEffect(() => {
    void loadPath(defaultPath);
    setSelectedFile(null);
    setFileContent(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leaseId]);

  async function openFile(path: string) {
    if (selectedFile === path) {
      setSelectedFile(null);
      setFileContent(null);
      return;
    }
    setSelectedFile(path);
    setFileContent(null);
    setFileError(null);
    setFileLoading(true);
    try {
      const resp = await fetch(buildReadUrl(path));
      if (!resp.ok) throw new Error(`${resp.status}`);
      const data = await resp.json() as { content: string; truncated: boolean };
      setFileContent(data.content);
      if (data.truncated) setFileError("(内容已截断至 100 KB)");
    } catch (e) {
      setFileError(e instanceof Error ? e.message : "读取失败");
    } finally {
      setFileLoading(false);
    }
  }

  return (
    <div className={`text-xs ${className}`}>
      <ResizablePanelGroup orientation="horizontal" className="h-full border rounded border-border/30">
        {/* Left: File list */}
        <ResizablePanel defaultSize={50} minSize={30}>
          <div className="h-full flex flex-col">
            {/* Path bar */}
            <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-border/20 bg-muted/5">
              <button
                onClick={() => { void loadPath(defaultPath); setSelectedFile(null); setFileContent(null); }}
                className="text-muted-foreground hover:text-foreground transition-colors duration-fast"
                title="返回根目录"
              >
                <Home className="w-3 h-3" />
              </button>
              <span className="font-mono text-muted-foreground truncate flex-1 text-[10px]">{currentPath}</span>
            </div>

            {/* File list */}
            <ScrollArea className="flex-1">
              <div className="p-1 space-y-0.5">
                {parentPath && (
                  <button
                    onClick={() => loadPath(parentPath)}
                    className="w-full flex items-center gap-1.5 px-2 py-1 hover:bg-muted/50 rounded text-muted-foreground"
                  >
                    <Folder className="w-3 h-3 shrink-0" />
                    <span>..</span>
                  </button>
                )}

                {loading && (
                  <div className="text-center py-6 text-muted-foreground">加载中...</div>
                )}
                {error && (
                  <div className="text-center py-6 text-destructive text-[11px]">{error}</div>
                )}

                {!loading && !error && items.length === 0 && (
                  <div className="text-center py-6 text-muted-foreground">此目录为空</div>
                )}

                {!loading && !error && items.map((item) =>
                  item.is_dir ? (
                    <button
                      key={item.path}
                      onClick={() => loadPath(item.path)}
                      className="w-full flex items-center gap-1.5 px-2 py-1 hover:bg-muted/50 rounded"
                    >
                      <Folder className="w-3 h-3 text-muted-foreground shrink-0" />
                      <span className="flex-1 text-left truncate">{item.name}</span>
                    </button>
                  ) : (
                    <button
                      key={item.path}
                      onClick={() => { void openFile(item.path); }}
                      className={`w-full flex items-center gap-1.5 px-2 py-1 hover:bg-muted/50 rounded text-left ${
                        selectedFile === item.path ? "bg-muted/40 text-foreground" : "text-muted-foreground"
                      }`}
                    >
                      <File className="w-3 h-3 shrink-0" />
                      <span className="truncate">{item.name}</span>
                    </button>
                  )
                )}
              </div>
            </ScrollArea>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Right: File content */}
        <ResizablePanel defaultSize={50} minSize={30}>
          <div className="h-full flex flex-col bg-muted/5">
            {selectedFile ? (
              <>
                {/* File header */}
                <div className="flex items-center justify-between px-2 py-1.5 border-b border-border/20 bg-muted/10">
                  <span className="text-[10px] font-mono text-muted-foreground truncate flex-1">
                    {selectedFile.split("/").pop()}
                  </span>
                  <button
                    onClick={() => { setSelectedFile(null); setFileContent(null); setFileError(null); }}
                    className="ml-2 text-muted-foreground hover:text-foreground shrink-0"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>

                {/* File content */}
                <ScrollArea className="flex-1">
                  <div className="p-2">
                    {fileLoading && (
                      <div className="text-center py-6 text-muted-foreground text-[11px]">加载中...</div>
                    )}
                    {!fileLoading && fileError && !fileContent && (
                      <div className="text-center py-6 text-destructive text-[11px]">{fileError}</div>
                    )}
                    {fileContent != null && (
                      <>
                        <pre className="text-[10px] font-mono text-foreground whitespace-pre-wrap break-all leading-relaxed">
                          {fileContent}
                        </pre>
                        {fileError && (
                          <p className="text-[10px] text-muted-foreground mt-1 italic">{fileError}</p>
                        )}
                      </>
                    )}
                  </div>
                </ScrollArea>
              </>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground text-[11px]">
                选择文件以查看内容
              </div>
            )}
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
