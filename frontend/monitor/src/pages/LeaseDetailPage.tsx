import React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { useMonitorData } from "../app/fetch";
import ErrorState from "../components/ErrorState";

type LeaseDetailPayload = {
  source: string;
  lease: {
    lease_id: string;
    sandbox_id?: string | null;
    provider_name?: string | null;
    desired_state?: string | null;
    observed_state?: string | null;
    updated_at?: string | null;
  };
  triage?: {
    description?: string | null;
  } | null;
  cleanup?: {
    reason?: string | null;
  } | null;
};

export function buildLeaseDetailShell(data: Pick<LeaseDetailPayload, "source" | "lease" | "triage" | "cleanup">) {
  const sandboxId = String(data.lease.sandbox_id ?? "").trim();
  return {
    title: "Lease compatibility redirect",
    sourceLabel: `Source: ${data.source}`,
    description: "Legacy lease-shaped detail route now redirects to canonical sandbox detail.",
    reason: data.cleanup?.reason ?? data.triage?.description ?? "Canonical sandbox detail is now the source of truth.",
    canonicalHref: sandboxId ? `/sandboxes/${sandboxId}` : null,
    compatibilityOnly: true,
  };
}

export default function LeaseDetailPage() {
  const params = useParams<{ leaseId: string }>();
  const leaseId = params.leaseId ?? "";
  const navigate = useNavigate();
  const { data, error } = useMonitorData<LeaseDetailPayload>(`/leases/${leaseId}`);

  if (error) return <ErrorState title={`Lease ${leaseId}`} error={error} />;
  if (!data) return <div>Loading...</div>;

  const shell = buildLeaseDetailShell(data);

  React.useEffect(() => {
    if (shell.canonicalHref) {
      navigate(shell.canonicalHref, { replace: true });
    }
  }, [navigate, shell.canonicalHref]);

  return (
    <div className="page">
      <h1>{shell.title}</h1>
      <p className="description">{shell.description}</p>
      <p className="count">{shell.sourceLabel}</p>
      <section className="surface-section">
        <h2>Compatibility Route</h2>
        <p className="description">{shell.reason}</p>
        <div className="surface-grid">
          <article className="surface-card">
            <p className="surface-card__eyebrow">Legacy Lease Route</p>
            <p className="surface-card__value surface-card__value--compact mono">{leaseId}</p>
            <p className="surface-card__body">This detail surface is now compatibility-only.</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Canonical Sandbox Route</p>
            <p className="surface-card__value surface-card__value--compact">
              {shell.canonicalHref ? <Link to={shell.canonicalHref}>{shell.canonicalHref}</Link> : "-"}
            </p>
            <p className="surface-card__body">Opening the sandbox detail surface instead.</p>
          </article>
        </div>
      </section>
    </div>
  );
}
