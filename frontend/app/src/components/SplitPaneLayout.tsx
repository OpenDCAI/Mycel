import { Outlet } from "react-router-dom";
import { useIsMobile } from "@/hooks/use-mobile";
import type { ReactNode } from "react";

interface SplitPaneLayoutProps {
  sidebar: ReactNode;
  hasDetail: boolean;
  emptyMessage?: string;
  outletContext?: unknown;
}

export default function SplitPaneLayout({ sidebar, hasDetail, emptyMessage = "选择一项查看详情", outletContext }: SplitPaneLayoutProps) {
  const isMobile = useIsMobile();

  if (isMobile) {
    return (
      <div className="h-full w-full min-h-0 overflow-hidden">
        {hasDetail ? (
          <div className="h-full w-full min-h-0 flex flex-col overflow-hidden">
            <Outlet context={outletContext} />
          </div>
        ) : (
          sidebar
        )}
      </div>
    );
  }

  return (
    <div className="h-full w-full flex overflow-hidden">
      <div className="w-72 shrink-0 h-full">{sidebar}</div>
      <div className="flex-1 min-w-0 h-full min-h-0 flex flex-col overflow-hidden">
        {hasDetail ? (
          <Outlet context={outletContext} />
        ) : (
          <div className="h-full flex items-center justify-center">
            <p className="text-sm text-muted-foreground">{emptyMessage}</p>
          </div>
        )}
      </div>
    </div>
  );
}
