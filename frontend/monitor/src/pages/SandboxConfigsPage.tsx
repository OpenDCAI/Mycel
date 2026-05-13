import ErrorState from "../components/ErrorState";
import { useMonitorData } from "../app/fetch";

type SandboxConfigPayload = {
  source: string;
  default_local_cwd: string;
  count: number;
  providers: Array<{
    name: string;
    provider?: string | null;
    available?: boolean;
    reason?: string | null;
    capability?: {
      supports_background?: boolean;
      supports_files?: boolean;
      supports_pause?: boolean;
      supports_resume?: boolean;
      supports_metrics?: boolean;
      persistent?: boolean;
    };
  }>;
};

const CAPABILITY_LABELS: Array<[keyof NonNullable<SandboxConfigPayload["providers"][number]["capability"]>, string]> = [
  ["supports_background", "background"],
  ["supports_files", "files"],
  ["supports_pause", "pause"],
  ["supports_resume", "resume"],
  ["supports_metrics", "metrics"],
  ["persistent", "persistent"],
];

export default function SandboxConfigsPage() {
  const { data, error } = useMonitorData<SandboxConfigPayload>("/sandbox-configs");

  if (error) return <ErrorState title="Sandbox Configs" error={error} />;
  if (!data) return <div>Loading...</div>;

  return (
    <div className="page">
      <h1>Sandbox Configs</h1>
      <p className="count">Source: {data.source}</p>

      <section className="surface-section">
        <h2>Local Defaults</h2>
        <div className="surface-card">
          <p className="surface-card__eyebrow">Default local cwd</p>
          <p className="surface-card__body mono">{data.default_local_cwd}</p>
        </div>
      </section>

      <section className="surface-section">
        <h2>Provider Inventory</h2>
        <p className="count">Configured providers: {data.count}</p>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Provider</th>
              <th>Status</th>
              <th>Capabilities</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {data.providers.map((item) => (
              <tr key={item.name}>
                <td className="mono">{item.name}</td>
                <td>{item.provider ?? "-"}</td>
                <td>{item.available ? "available" : "unavailable"}</td>
                <td>
                  {CAPABILITY_LABELS.filter(([key]) => item.capability?.[key])
                    .map(([, label]) => label)
                    .join(", ") || "-"}
                </td>
                <td>{item.reason ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
