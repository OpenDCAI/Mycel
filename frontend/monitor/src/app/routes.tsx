import { Route, Routes } from "react-router-dom";

import ResourcesPage from "../ResourcesPage";
import DashboardPage from "../pages/DashboardPage";
import DivergedPage from "../pages/DivergedPage";
import EvaluationPage from "../pages/EvaluationPage";
import EventDetailPage from "../pages/EventDetailPage";
import EventsPage from "../pages/EventsPage";
import LeaseDetailPage from "../pages/LeaseDetailPage";
import LeasesPage from "../pages/LeasesPage";
import ThreadDetailPage from "../pages/ThreadDetailPage";
import ThreadsPage from "../pages/ThreadsPage";
import { MonitorShell } from "./MonitorShell";

export function MonitorRoutes() {
  return (
    <MonitorShell>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/resources" element={<ResourcesPage />} />
        <Route path="/threads" element={<ThreadsPage />} />
        <Route path="/thread/:threadId" element={<ThreadDetailPage />} />
        <Route path="/leases" element={<LeasesPage />} />
        <Route path="/lease/:leaseId" element={<LeaseDetailPage />} />
        <Route path="/evaluation" element={<EvaluationPage />} />
        <Route path="/diverged" element={<DivergedPage />} />
        <Route path="/events" element={<EventsPage />} />
        <Route path="/event/:eventId" element={<EventDetailPage />} />
      </Routes>
    </MonitorShell>
  );
}
