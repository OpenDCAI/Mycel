import { Link, useParams } from "react-router-dom";

import Breadcrumb from "../components/Breadcrumb";
import ErrorState from "../components/ErrorState";
import { useMonitorData } from "../app/fetch";

export default function EventDetailPage() {
  const { eventId } = useParams();
  const { data, error } = useMonitorData<any>(`/event/${eventId}`);

  if (error) return <ErrorState title="Event detail" error={error} />;
  if (!data) return <div>Loading...</div>;

  return (
    <div className="page">
      <Breadcrumb items={data.breadcrumb} />
      <h1>Event: {data.event_id}</h1>

      <section className="info-grid">
        <div>
          <strong>Type:</strong> {data.info.event_type}
        </div>
        <div>
          <strong>Source:</strong> {data.info.source}
        </div>
        <div>
          <strong>Provider:</strong> {data.info.provider}
        </div>
        <div>
          <strong>Time:</strong> {data.info.created_ago}
        </div>
      </section>

      {data.error && (
        <section>
          <h2>Error</h2>
          <pre className="json-payload error">{data.error}</pre>
        </section>
      )}

      {data.related_lease.lease_id && (
        <section>
          <h2>Related Lease</h2>
          <Link to={data.related_lease.lease_url}>{data.related_lease.lease_id}</Link>
        </section>
      )}

      <section>
        <h2>Payload</h2>
        <pre className="json-payload">{JSON.stringify(data.payload, null, 2)}</pre>
      </section>
    </div>
  );
}
