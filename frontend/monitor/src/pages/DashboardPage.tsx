import ErrorState from "../components/ErrorState";
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
