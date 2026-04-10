import { useLocation } from "react-router-dom";

import { MonitorNav } from "./MonitorNav";
import { resolveMonitorNav } from "./monitor-nav";

export function MonitorShell({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const current = resolveMonitorNav(location.pathname);

  return (
    <div className="monitor-shell">
      <MonitorNav />
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
