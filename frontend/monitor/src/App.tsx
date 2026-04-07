import React from 'react';
import { BrowserRouter, Routes, Route, Link, useParams, useNavigate } from 'react-router-dom';
import './styles.css';

const API_BASE = '/api/monitor';

// Utility: Fetch JSON from API
async function fetchAPI(path: string) {
  const res = await fetch(`${API_BASE}${path}`);
  return res.json();
}

// Component: Breadcrumb navigation
function Breadcrumb({ items }: { items: Array<{ label: string; url: string }> }) {
  return (
    <div className="breadcrumb">
      {items.map((item, i) => (
        <React.Fragment key={i}>
          {i > 0 && <span> / </span>}
          <Link to={item.url}>{item.label}</Link>
        </React.Fragment>
      ))}
    </div>
  );
}

// Component: State badge
function StateBadge({ badge }: { badge: any }) {
  const className = `state-badge state-${badge.color}`;
  const text = badge.text || badge.observed;
  const tooltip = badge.hours_diverged
    ? `Diverged for ${badge.hours_diverged}h`
    : badge.converged
    ? 'Converged'
    : `${badge.observed} → ${badge.desired}`;

  return <span className={className} title={tooltip}>{text}</span>;
}

// Page: Threads List
function ThreadsPage() {
  const [data, setData] = React.useState<any>(null);

  React.useEffect(() => {
    fetchAPI('/threads').then(setData);
  }, []);

  if (!data) return <div>Loading...</div>;

  return (
    <div className="page">
      <h1>{data.title}</h1>
      <p className="count">Total: {data.count}</p>
      <table>
        <thead>
          <tr>
            <th>Thread ID</th>
            <th>Sessions</th>
            <th>Last Active</th>
            <th>Lease</th>
            <th>Provider</th>
            <th>State</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item: any) => (
            <tr key={item.thread_id}>
              <td><Link to={item.thread_url}>{item.thread_id.slice(0, 8)}</Link></td>
              <td>{item.session_count}</td>
              <td>{item.last_active_ago}</td>
              <td>
                {item.lease.lease_id ? (
                  <Link to={item.lease.lease_url}>{item.lease.lease_id}</Link>
                ) : '-'}
              </td>
              <td>{item.lease.provider || '-'}</td>
              <td><StateBadge badge={item.state_badge} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Page: Thread Detail
function ThreadDetailPage() {
  const { threadId } = useParams();
  const [data, setData] = React.useState<any>(null);

  React.useEffect(() => {
    fetchAPI(`/thread/${threadId}`).then(setData);
  }, [threadId]);

  if (!data) return <div>Loading...</div>;

  return (
    <div className="page">
      <Breadcrumb items={data.breadcrumb} />
      <h1>Thread: {data.thread_id.slice(0, 8)}</h1>

      <section>
        <h2>{data.sessions.title} ({data.sessions.count})</h2>
        <table>
          <thead>
            <tr>
              <th>Session ID</th>
              <th>Status</th>
              <th>Started</th>
              <th>Ended</th>
              <th>Lease</th>
              <th>State</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            {data.sessions.items.map((s: any) => (
              <tr key={s.session_id}>
                <td><Link to={s.session_url}>{s.session_id.slice(0, 8)}</Link></td>
                <td>{s.status}</td>
                <td>{s.started_ago}</td>
                <td>{s.ended_ago || '-'}</td>
                <td>
                  {s.lease.lease_id ? (
                    <Link to={s.lease.lease_url}>{s.lease.lease_id}</Link>
                  ) : '-'}
                </td>
                <td><StateBadge badge={s.state_badge} /></td>
                <td className="error">{s.error || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2>{data.related_leases.title}</h2>
        <ul>
          {data.related_leases.items.map((l: any) => (
            <li key={l.lease_id}>
              <Link to={l.lease_url}>{l.lease_id}</Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

// Page: Leases List
function LeasesPage() {
  const [data, setData] = React.useState<any>(null);

  React.useEffect(() => {
    fetchAPI('/leases').then(setData);
  }, []);

  if (!data) return <div>Loading...</div>;

  return (
    <div className="page">
      <h1>{data.title}</h1>
      <p className="count">Total: {data.count}</p>
      <table>
        <thead>
          <tr>
            <th>Lease ID</th>
            <th>Provider</th>
            <th>Instance ID</th>
            <th>Thread</th>
            <th>State</th>
            <th>Updated</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item: any) => (
            <tr key={item.lease_id}>
              <td><Link to={item.lease_url}>{item.lease_id}</Link></td>
              <td>{item.provider}</td>
              <td className="mono">{item.instance_id?.slice(0, 12) || '-'}</td>
              <td>
                {item.thread.thread_id ? (
                  <Link to={item.thread.thread_url}>{item.thread.thread_id.slice(0, 8)}</Link>
                ) : (
                  <span className="orphan">orphan</span>
                )}
              </td>
              <td><StateBadge badge={item.state_badge} /></td>
              <td>{item.updated_ago}</td>
              <td className="error">{item.error || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Page: Lease Detail
function LeaseDetailPage() {
  const { leaseId } = useParams();
  const [data, setData] = React.useState<any>(null);

  React.useEffect(() => {
    fetchAPI(`/lease/${leaseId}`).then(setData);
  }, [leaseId]);

  if (!data) return <div>Loading...</div>;

  return (
    <div className="page">
      <Breadcrumb items={data.breadcrumb} />
      <h1>Lease: {data.lease_id}</h1>

      <section className="info-grid">
        <div>
          <strong>Provider:</strong> {data.info.provider}
        </div>
        <div>
          <strong>Instance ID:</strong> <span className="mono">{data.info.instance_id || '-'}</span>
        </div>
        <div>
          <strong>Created:</strong> {data.info.created_ago}
        </div>
        <div>
          <strong>Updated:</strong> {data.info.updated_ago}
        </div>
      </section>

      <section>
        <h2>State</h2>
        <div className="state-info">
          <div>
            <strong>Desired:</strong> {data.state.desired}
          </div>
          <div>
            <strong>Observed:</strong> {data.state.observed}
          </div>
          <div>
            <strong>Status:</strong> <StateBadge badge={data.state} />
          </div>
          {data.state.error && (
            <div className="error">
              <strong>Error:</strong> {data.state.error}
            </div>
          )}
        </div>
      </section>

      <section>
        <h2>{data.related_threads.title}</h2>
        <ul>
          {data.related_threads.items.map((t: any) => (
            <li key={t.thread_id}>
              <Link to={t.thread_url}>{t.thread_id}</Link>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>{data.lease_events.title} ({data.lease_events.count})</h2>
        <table>
          <thead>
            <tr>
              <th>Event ID</th>
              <th>Type</th>
              <th>Source</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {data.lease_events.items.map((e: any) => (
              <tr key={e.event_id}>
                <td><Link to={e.event_url}>{e.event_id}</Link></td>
                <td>{e.event_type}</td>
                <td>{e.source}</td>
                <td>{e.created_ago}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

// Page: Diverged Leases
function DivergedPage() {
  const [data, setData] = React.useState<any>(null);

  React.useEffect(() => {
    fetchAPI('/diverged').then(setData);
  }, []);

  if (!data) return <div>Loading...</div>;

  return (
    <div className="page">
      <h1>{data.title}</h1>
      <p className="description">{data.description}</p>
      <p className="count">Total: {data.count}</p>
      <table>
        <thead>
          <tr>
            <th>Lease ID</th>
            <th>Provider</th>
            <th>Thread</th>
            <th>Desired</th>
            <th>Observed</th>
            <th>Hours Diverged</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item: any) => (
            <tr key={item.lease_id}>
              <td><Link to={item.lease_url}>{item.lease_id}</Link></td>
              <td>{item.provider}</td>
              <td>
                {item.thread.thread_id ? (
                  <Link to={item.thread.thread_url}>{item.thread.thread_id.slice(0, 8)}</Link>
                ) : (
                  <span className="orphan">orphan</span>
                )}
              </td>
              <td>{item.state_badge.desired}</td>
              <td>{item.state_badge.observed}</td>
              <td className={item.state_badge.color === 'red' ? 'error' : ''}>
                {item.state_badge.hours_diverged}h
              </td>
              <td className="error">{item.error || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Page: Events List
function EventsPage() {
  const [data, setData] = React.useState<any>(null);

  React.useEffect(() => {
    fetchAPI('/events?limit=100').then(setData);
  }, []);

  if (!data) return <div>Loading...</div>;

  return (
    <div className="page">
      <h1>{data.title}</h1>
      <p className="description">{data.description}</p>
      <p className="count">Total: {data.count}</p>
      <table>
        <thead>
          <tr>
            <th>Type</th>
            <th>Source</th>
            <th>Provider</th>
            <th>Lease</th>
            <th>Error</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item: any) => (
            <tr key={item.event_id}>
              <td><Link to={item.event_url}>{item.event_type}</Link></td>
              <td>{item.source}</td>
              <td>{item.provider}</td>
              <td>
                {item.lease.lease_id ? (
                  <Link to={item.lease.lease_url}>{item.lease.lease_id}</Link>
                ) : '-'}
              </td>
              <td className="error">{item.error || '-'}</td>
              <td>{item.created_ago}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Page: Event Detail
function EventDetailPage() {
  const { eventId } = useParams();
  const [data, setData] = React.useState<any>(null);

  React.useEffect(() => {
    fetchAPI(`/event/${eventId}`).then(setData);
  }, [eventId]);

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

// Layout: Top navigation
function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app">
      <nav className="top-nav">
        <h1 className="logo">Leon Sandbox Monitor</h1>
        <div className="nav-links">
          <Link to="/threads">Threads</Link>
          <Link to="/leases">Leases</Link>
          <Link to="/diverged">Diverged</Link>
          <Link to="/events">Events</Link>
        </div>
      </nav>
      <main className="content">
        {children}
      </main>
    </div>
  );
}

// Main App
export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<DivergedPage />} />
          <Route path="/threads" element={<ThreadsPage />} />
          <Route path="/thread/:threadId" element={<ThreadDetailPage />} />
          <Route path="/leases" element={<LeasesPage />} />
          <Route path="/lease/:leaseId" element={<LeaseDetailPage />} />
          <Route path="/diverged" element={<DivergedPage />} />
          <Route path="/events" element={<EventsPage />} />
          <Route path="/event/:eventId" element={<EventDetailPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
