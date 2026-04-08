import { Link, Route, Routes } from "react-router-dom";

import ResourcesPage from "../ResourcesPage";
import DashboardPage from "../pages/DashboardPage";
import DivergedPage from "../pages/DivergedPage";
import EventDetailPage from "../pages/EventDetailPage";
import EventsPage from "../pages/EventsPage";
import LeaseDetailPage from "../pages/LeaseDetailPage";
import LeasesPage from "../pages/LeasesPage";
import ThreadDetailPage from "../pages/ThreadDetailPage";
import ThreadsPage from "../pages/ThreadsPage";

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app">
      <nav className="top-nav">
        <h1 className="logo">Leon Sandbox Monitor</h1>
        <div className="nav-links">
          <Link to="/dashboard">Dashboard</Link>
          <Link to="/threads">Threads</Link>
          <Link to="/resources">Resources</Link>
          <Link to="/leases">Leases</Link>
          <Link to="/diverged">Diverged</Link>
          <Link to="/events">Events</Link>
        </div>
      </nav>
      <main className="content">{children}</main>
    </div>
  );
}

export function MonitorRoutes() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/resources" element={<ResourcesPage />} />
        <Route path="/threads" element={<ThreadsPage />} />
        <Route path="/thread/:threadId" element={<ThreadDetailPage />} />
        <Route path="/leases" element={<LeasesPage />} />
        <Route path="/lease/:leaseId" element={<LeaseDetailPage />} />
        <Route path="/diverged" element={<DivergedPage />} />
        <Route path="/events" element={<EventsPage />} />
        <Route path="/event/:eventId" element={<EventDetailPage />} />
      </Routes>
    </Layout>
  );
}
