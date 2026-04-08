import { NavLink } from "react-router-dom";

import { monitorNav } from "./monitor-nav";

export function MonitorNav() {
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
            <NavLink key={item.to} to={item.to} className="monitor-sidebar__link">
              <span className="monitor-sidebar__link-eyebrow">{item.eyebrow}</span>
              <span className="monitor-sidebar__link-label">{item.label}</span>
            </NavLink>
          ))}
        </div>
      </div>
    </nav>
  );
}
