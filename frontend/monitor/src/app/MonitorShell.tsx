import React from "react";
import { useLocation } from "react-router-dom";

import { cx } from "./classes";
import { MonitorNav } from "./MonitorNav";
import { resolveMonitorNav } from "./monitor-nav";

export function MonitorShell({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const current = resolveMonitorNav(location.pathname);
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false);

  return (
    <div className={cx("monitor-shell", sidebarCollapsed && "monitor-shell--sidebar-collapsed")}>
      <MonitorNav collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed((value) => !value)} />
      <main className="monitor-shell__main">
        <header className="monitor-shell__header">
          <div>
            <p className="monitor-shell__eyebrow">{current.eyebrow}</p>
            <h2 className="monitor-shell__title">{current.label}</h2>
          </div>
          <p className="monitor-shell__path">{location.pathname}</p>
        </header>
        <section className="monitor-shell__content">{children}</section>
      </main>
    </div>
  );
}
