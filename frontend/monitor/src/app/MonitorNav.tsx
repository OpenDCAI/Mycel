import { Link, useLocation } from "react-router-dom";

import { monitorNav, resolveMonitorNav } from "./monitor-nav";

export function MonitorNav() {
  const location = useLocation();
  const current = resolveMonitorNav(location.pathname);

  return (
    <nav aria-label="Monitor sections" className="monitor-sidebar">
      <div className="monitor-sidebar__brand">
        <span className="monitor-sidebar__eyebrow">Leon Ops</span>
        <h1>Leon Sandbox Monitor</h1>
        <p>Current monitor routes, unified under one console shell.</p>
      </div>

      <div className="monitor-sidebar__group">
        <span className="monitor-sidebar__group-label">Surfaces</span>
        <div className="monitor-sidebar__links">
          {monitorNav.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              aria-current={current.to === item.to ? "page" : undefined}
              className={["monitor-sidebar__link", current.to === item.to ? "active" : ""].join(" ").trim()}
            >
              <span className="monitor-sidebar__link-eyebrow">{item.eyebrow}</span>
              <span className="monitor-sidebar__link-label">{item.label}</span>
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
