# Legacy Monitor Shell Revival PR-C1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the first stage of the legacy monitor frontend by replacing the current top-nav/dark single-file shell with a unified left-sidebar monitor shell for the currently backed monitor routes on `dev`.

**Architecture:** This plan keeps backend contracts unchanged and focuses only on frontend shell structure. The work is split into focused tasks: first add a minimal monitor frontend test harness, then extract the current giant `App.tsx` into route adapters and page modules, then introduce `MonitorShell`/`MonitorNav`, and finally switch the visual chrome from the old dark top-nav layout to a light sidebar console for the current route set (`dashboard`, `threads`, `resources`, `leases`, `diverged`, `events`). Evaluation runtime activation is intentionally not folded into this plan; it remains a mandatory later lane that must be coordinated with the upstream owner.

**Tech Stack:** React 19, React Router 7, TypeScript, Vite, Vitest, Testing Library, CSS

---

## Mandatory Boundary

- This plan restores shell/navigation only for the route surfaces that currently exist on `dev`.
- It does not claim that the evaluation system is fully restored.
- Getting evaluation to run for real again remains a required later lane, but that lane must not be smuggled into `PR-C1`.
- If implementation work discovers eval placeholders or dead links, record them as follow-up debt instead of widening this shell PR.

### Task 1: Add Minimal Monitor Frontend Test Harness

**Files:**
- Modify: `frontend/monitor/package.json`
- Create: `frontend/monitor/vitest.config.ts`
- Create: `frontend/monitor/src/test/setup.ts`
- Create: `frontend/monitor/src/app/routes.test.tsx`
- Test: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MonitorRoutes } from "./routes";

describe("MonitorRoutes", () => {
  it("renders the current monitor route set under the app router", () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(screen.getByText("Leon Sandbox Monitor")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Threads" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Resources" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Leases" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Diverged" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Events" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
Expected: FAIL because `vitest` is not configured and `src/app/routes.tsx` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```json
{
  "scripts": {
    "dev": "vite --host 0.0.0.0 --port 5174",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview --host 127.0.0.1 --port 4174",
    "test": "vitest"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "jsdom": "^26.1.0",
    "vitest": "^3.2.4"
  }
}
```

```ts
// frontend/monitor/vitest.config.ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
});
```

```ts
// frontend/monitor/src/test/setup.ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 4: Run test to verify it still fails for the right reason**

Run: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
Expected: FAIL because `MonitorRoutes` and the new shell modules do not exist yet.

- [ ] **Step 5: Commit**

```bash
git add frontend/monitor/package.json frontend/monitor/package-lock.json frontend/monitor/vitest.config.ts frontend/monitor/src/test/setup.ts frontend/monitor/src/app/routes.test.tsx
git commit -m "test: add monitor frontend shell harness"
```

### Task 2: Extract Current Page Surfaces Out Of `App.tsx`

**Files:**
- Modify: `frontend/monitor/src/App.tsx`
- Create: `frontend/monitor/src/app/fetch.ts`
- Create: `frontend/monitor/src/pages/ThreadsPage.tsx`
- Create: `frontend/monitor/src/pages/ThreadDetailPage.tsx`
- Create: `frontend/monitor/src/pages/LeasesPage.tsx`
- Create: `frontend/monitor/src/pages/LeaseDetailPage.tsx`
- Create: `frontend/monitor/src/pages/DivergedPage.tsx`
- Create: `frontend/monitor/src/pages/EventsPage.tsx`
- Create: `frontend/monitor/src/pages/EventDetailPage.tsx`
- Create: `frontend/monitor/src/pages/DashboardPage.tsx`
- Create: `frontend/monitor/src/components/Breadcrumb.tsx`
- Create: `frontend/monitor/src/components/StateBadge.tsx`
- Create: `frontend/monitor/src/components/ErrorState.tsx`
- Test: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
it("shows dashboard content for /dashboard", () => {
  render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <MonitorRoutes />
    </MemoryRouter>,
  );

  expect(screen.getByText("Leon Sandbox Monitor")).toBeInTheDocument();
  expect(screen.getByText("Dashboard")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
Expected: FAIL because route extraction and the dashboard adapter do not exist.

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/monitor/src/app/fetch.ts
export const API_BASE = "/api/monitor";
export const MONITOR_TOKEN_KEY = "leon-monitor-token";
```

```tsx
// frontend/monitor/src/pages/DashboardPage.tsx
import { useMonitorData } from "../app/fetch";

export default function DashboardPage() {
  const { data, error } = useMonitorData<any>("/dashboard");
  if (error) return <ErrorState title="Dashboard" error={error} />;
  if (!data) return <div>Loading...</div>;
  return (
    <div className="page">
      <h1>Dashboard</h1>
      <p className="count">Snapshot: {data.snapshot_at}</p>
    </div>
  );
}
```

```tsx
// frontend/monitor/src/App.tsx
import { BrowserRouter } from "react-router-dom";
import { MonitorRoutes } from "./app/routes";

export default function App() {
  return (
    <BrowserRouter>
      <MonitorRoutes />
    </BrowserRouter>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
Expected: PASS with the route tree moved out of `App.tsx`.

- [ ] **Step 5: Commit**

```bash
git add frontend/monitor/src/App.tsx frontend/monitor/src/app/fetch.ts frontend/monitor/src/pages frontend/monitor/src/components
git commit -m "refactor: extract monitor pages from app shell"
```

### Task 3: Introduce `MonitorShell`, `MonitorNav`, And Route Model

**Files:**
- Create: `frontend/monitor/src/app/monitor-nav.ts`
- Create: `frontend/monitor/src/app/MonitorNav.tsx`
- Create: `frontend/monitor/src/app/MonitorShell.tsx`
- Create: `frontend/monitor/src/app/routes.tsx`
- Modify: `frontend/monitor/src/app/routes.test.tsx`
- Test: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
it("renders the shell with a sidebar and highlights the active route", () => {
  render(
    <MemoryRouter initialEntries={["/leases"]}>
      <MonitorRoutes />
    </MemoryRouter>,
  );

  expect(screen.getByRole("navigation", { name: "Monitor sections" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Leases" })).toHaveAttribute("aria-current", "page");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
Expected: FAIL because there is no sidebar shell yet.

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/monitor/src/app/monitor-nav.ts
export const monitorNav = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/threads", label: "Threads" },
  { to: "/resources", label: "Resources" },
  { to: "/leases", label: "Leases" },
  { to: "/diverged", label: "Diverged" },
  { to: "/events", label: "Events" },
] as const;
```

```tsx
// frontend/monitor/src/app/MonitorNav.tsx
import { NavLink } from "react-router-dom";
import { monitorNav } from "./monitor-nav";

export function MonitorNav() {
  return (
    <nav aria-label="Monitor sections" className="monitor-sidebar">
      {monitorNav.map((item) => (
        <NavLink key={item.to} to={item.to}>
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
```

```tsx
// frontend/monitor/src/app/MonitorShell.tsx
import { Outlet } from "react-router-dom";
import { MonitorNav } from "./MonitorNav";

export function MonitorShell() {
  return (
    <div className="monitor-shell">
      <aside className="monitor-shell__rail">
        <h1 className="monitor-shell__brand">Leon Sandbox Monitor</h1>
        <MonitorNav />
      </aside>
      <main className="monitor-shell__content">
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
Expected: PASS with a real sidebar shell.

- [ ] **Step 5: Commit**

```bash
git add frontend/monitor/src/app/monitor-nav.ts frontend/monitor/src/app/MonitorNav.tsx frontend/monitor/src/app/MonitorShell.tsx frontend/monitor/src/app/routes.tsx frontend/monitor/src/app/routes.test.tsx
git commit -m "feat: add monitor sidebar shell and route model"
```

### Task 4: Rebind Current Monitor Routes Under The Shell

**Files:**
- Modify: `frontend/monitor/src/app/routes.tsx`
- Modify: `frontend/monitor/src/app/routes.test.tsx`
- Modify: `frontend/monitor/src/pages/DashboardPage.tsx`
- Test: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
it("routes the current monitor surfaces under the shell", () => {
  render(
    <MemoryRouter initialEntries={["/events"]}>
      <MonitorRoutes />
    </MemoryRouter>,
  );

  expect(screen.getByRole("navigation", { name: "Monitor sections" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Events" })).toHaveAttribute("aria-current", "page");
});
```

```tsx
it("uses /dashboard as the explicit landing route", () => {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <MonitorRoutes />
    </MemoryRouter>,
  );

  expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
Expected: FAIL because `/` does not yet redirect to `/dashboard` under the shell.

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/monitor/src/app/routes.tsx
import { Navigate, Route, Routes } from "react-router-dom";

export function MonitorRoutes() {
  return (
    <Routes>
      <Route element={<MonitorShell />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/threads" element={<ThreadsPage />} />
        <Route path="/thread/:threadId" element={<ThreadDetailPage />} />
        <Route path="/resources" element={<ResourcesPage />} />
        <Route path="/leases" element={<LeasesPage />} />
        <Route path="/lease/:leaseId" element={<LeaseDetailPage />} />
        <Route path="/diverged" element={<DivergedPage />} />
        <Route path="/events" element={<EventsPage />} />
        <Route path="/event/:eventId" element={<EventDetailPage />} />
      </Route>
    </Routes>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
Expected: PASS with all current monitor surfaces mounted inside the shell.

- [ ] **Step 5: Commit**

```bash
git add frontend/monitor/src/app/routes.tsx frontend/monitor/src/app/routes.test.tsx frontend/monitor/src/pages/DashboardPage.tsx
git commit -m "feat: mount current monitor surfaces under unified shell"
```

### Task 5: Replace The Old Dark Top-Nav Chrome With The New Light Sidebar Layout

**Files:**
- Modify: `frontend/monitor/src/styles.css`
- Test: `cd frontend/monitor && npm run build`
- Test: browser proof on `http://127.0.0.1:5174/dashboard`

- [ ] **Step 1: Write the failing test**

```tsx
it("renders shell layout classes for the sidebar console", () => {
  render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <MonitorRoutes />
    </MemoryRouter>,
  );

  expect(document.querySelector(".monitor-shell")).not.toBeNull();
  expect(document.querySelector(".monitor-shell__rail")).not.toBeNull();
  expect(document.querySelector(".monitor-shell__content")).not.toBeNull();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
Expected: FAIL because the old CSS/layout does not yet define the shell structure.

- [ ] **Step 3: Write minimal implementation**

```css
:root {
  color: #18212b;
  background: #f4f1ea;
  font-family: "Segoe UI", "Helvetica Neue", sans-serif;
}

body {
  background:
    radial-gradient(circle at top right, rgba(80, 122, 92, 0.10), transparent 24%),
    linear-gradient(180deg, #f6f3ec 0%, #ece8df 100%);
  color: #18212b;
}

.monitor-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
}

.monitor-shell__rail {
  border-right: 1px solid #d8d1c4;
  background: rgba(255, 252, 247, 0.92);
  padding: 1.5rem 1rem;
}

.monitor-shell__content {
  padding: 1.75rem 2rem;
}
```

- [ ] **Step 4: Run tests and browser proof**

Run: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
Expected: PASS

Run: `cd frontend/monitor && npm run build`
Expected: PASS

Run: open `http://127.0.0.1:5174/dashboard`
Expected:
- left sidebar is visible
- current route group is obvious
- `/dashboard`, `/resources`, `/threads`, `/leases`, `/diverged`, `/events` switch inside the same shell

- [ ] **Step 5: Commit**

```bash
git add frontend/monitor/src/styles.css frontend/monitor/src/app/routes.test.tsx
git commit -m "feat: restyle monitor into light sidebar shell"
```

### Task 6: Final PR-C1 Verification And Handoff

**Files:**
- Modify: `docs/superpowers/specs/2026-04-08-legacy-monitor-shell-revival-design.md`
- Test: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
- Test: `cd frontend/monitor && npm run build`

- [ ] **Step 1: Re-read the spec and implementation**

Check:
- route set matches current real backend surfaces
- no `evaluation` / `traces` pages were silently invented
- shell work stayed frontend-only

- [ ] **Step 2: Run final verification**

Run: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
Expected: PASS

Run: `cd frontend/monitor && npm run build`
Expected: PASS

- [ ] **Step 3: Record any PR-C2 follow-ups discovered during PR-C1**

```md
- keep density tweaks for `PR-C3`
- keep deeper page restructuring for `PR-C2`
- do not fold them back into `PR-C1`
```

- [ ] **Step 4: Commit**

```bash
git add frontend/monitor docs/superpowers/specs/2026-04-08-legacy-monitor-shell-revival-design.md
git commit -m "chore: verify pr-c1 monitor shell slice"
```
