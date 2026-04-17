import { Link, useLocation } from "react-router-dom";

import { cx } from "./classes";
import { monitorNav, resolveMonitorNav } from "./monitor-nav";

export function MonitorNav({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const location = useLocation();
  const current = resolveMonitorNav(location.pathname);

  return (
    <nav
      aria-label="Monitor sections"
      className={cx("monitor-sidebar", collapsed && "monitor-sidebar--collapsed")}
    >
      <div className="monitor-sidebar__brand">
        <div className="monitor-sidebar__brand-row">
          <div>
            <span className="monitor-sidebar__eyebrow">Leon Ops</span>
            <h1>{collapsed ? "LM" : "Leon Sandbox Monitor"}</h1>
          </div>
          <button
            type="button"
            className="monitor-sidebar__toggle"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={onToggle}
          >
            <span aria-hidden="true">{collapsed ? "›" : "‹"}</span>
          </button>
        </div>
        {!collapsed && <p>Resource state, sandbox workbench, and evaluation.</p>}
      </div>

      <div className="monitor-sidebar__group">
        {!collapsed && <span className="monitor-sidebar__group-label">Surfaces</span>}
        <div className="monitor-sidebar__links">
          {monitorNav.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              aria-current={current.to === item.to ? "page" : undefined}
              aria-label={collapsed ? item.label : undefined}
              title={collapsed ? item.label : undefined}
              className={cx("monitor-sidebar__link", current.to === item.to && "active")}
            >
              <span className="monitor-sidebar__link-icon" aria-hidden="true">
                {item.label.slice(0, 1)}
              </span>
              <span className="monitor-sidebar__link-copy">
                <span className="monitor-sidebar__link-eyebrow">{item.eyebrow}</span>
                <span className="monitor-sidebar__link-label">{item.label}</span>
              </span>
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
