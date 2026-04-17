import { Route, Routes } from "react-router-dom";

import ResourcesPage from "../ResourcesPage";
import EvaluationBatchDetailPage from "../pages/EvaluationBatchDetailPage";
import DashboardPage from "../pages/DashboardPage";
import EvaluationPage from "../pages/EvaluationPage";
import EvaluationRunDetailPage from "../pages/EvaluationRunDetailPage";
import OperationDetailPage from "../pages/OperationDetailPage";
import ProviderDetailPage from "../pages/ProviderDetailPage";
import RuntimeDetailPage from "../pages/RuntimeDetailPage";
import SandboxDetailPage from "../pages/SandboxDetailPage";
import SandboxConfigsPage from "../pages/SandboxConfigsPage";
import SandboxesPage from "../pages/SandboxesPage";
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
        <Route path="/sandbox-configs" element={<SandboxConfigsPage />} />
        <Route path="/providers/:providerId" element={<ProviderDetailPage />} />
        <Route path="/sandboxes" element={<SandboxesPage />} />
        <Route path="/sandboxes/:sandboxId" element={<SandboxDetailPage />} />
        <Route path="/operations/:operationId" element={<OperationDetailPage />} />
        <Route path="/runtimes/:runtimeSessionId" element={<RuntimeDetailPage />} />
        <Route path="/threads" element={<ThreadsPage />} />
        <Route path="/threads/:threadId" element={<ThreadDetailPage />} />
        <Route path="/evaluation" element={<EvaluationPage />} />
        <Route path="/evaluation/batches/:batchId" element={<EvaluationBatchDetailPage />} />
        <Route path="/evaluation/runs/:runId" element={<EvaluationRunDetailPage />} />
      </Routes>
    </MonitorShell>
  );
}
