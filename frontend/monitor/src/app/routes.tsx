import { Route, Routes } from "react-router-dom";

import ResourcesPage from "../ResourcesPage";
import DashboardPage from "../pages/DashboardPage";
import EvaluationPage from "../pages/EvaluationPage";
import LeaseDetailPage from "../pages/LeaseDetailPage";
import LeasesPage from "../pages/LeasesPage";
import { MonitorShell } from "./MonitorShell";

export function MonitorRoutes() {
  return (
    <MonitorShell>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/resources" element={<ResourcesPage />} />
        <Route path="/leases" element={<LeasesPage />} />
        <Route path="/leases/:leaseId" element={<LeaseDetailPage />} />
        <Route path="/evaluation" element={<EvaluationPage />} />
      </Routes>
    </MonitorShell>
  );
}
