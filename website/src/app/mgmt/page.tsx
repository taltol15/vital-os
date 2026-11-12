import { AdminFrame } from "@/components/admin-frame";
import { LoginForm } from "@/components/login-form";
import { currentAdmin, loadDashboard } from "@/lib/admin-read";
import { previewEnabled } from "@/lib/preview";

export const dynamic = "force-dynamic";

export default async function MgmtHome() {
  const preview = previewEnabled();
  const admin = await currentAdmin();
  if (!admin && !preview) {
    return (
      <div className="shell">
        <LoginForm />
      </div>
    );
  }
  const { stats } = await loadDashboard();
  const max = Math.max(...stats.heartbeats, 1);
  return (
    <AdminFrame current="overview" email={admin?.email} preview={preview}>
      <header className="page-head">
        <p className="eyebrow">Overview</p>
        <h1>Counts</h1>
        <p className="lede">Anonymous installs, machines that checked in, versions, and catalog items reported after a Marketplace install. No addresses are stored.</p>
      </header>
      <section className="metrics">
        <article className="card"><h2>Downloads</h2><div className="metric">{stats.downloads}</div><p>ISO link hits. No cookies.</p></article>
        <article className="card"><h2>Installs</h2><div className="metric">{stats.installs}</div><p>Distinct ids that reported an install.</p></article>
        <article className="card"><h2>Live</h2><div className="metric">{stats.live}</div><p>Heartbeats in the last {stats.liveDays} days.</p></article>
        <article className="card"><h2>Unread</h2><div className="metric">{stats.unreadMessages}</div><p>Contact messages not marked read.</p></article>
      </section>
      <section className="card" style={{ marginTop: "0.8rem" }}>
        <h2>Active machines, last 7 days</h2>
        <div className="chart" role="img" aria-label="Distinct heartbeats for each of the last seven days">
          {stats.heartbeats.map((value, index) => (
            <div key={stats.days[index] ?? index} className="bar" style={{ height: `${Math.max(8, (value / max) * 100)}%` }}>
              <span>{stats.days[index]} {value}</span>
            </div>
          ))}
        </div>
        <p className="facts">{stats.days.map((day, index) => `${day.slice(5)} ${stats.heartbeats[index] ?? 0}`).join(" · ")}</p>
      </section>
      <div className="cols">
        <section className="card">
          <h2>Versions</h2>
          {stats.versions.length === 0 ? <p>No machines yet.</p> : (
            <table>
              <thead><tr><th>OS version</th><th>Machines</th></tr></thead>
              <tbody>
                {stats.versions.map((row) => (
                  <tr key={row.os_version}><td className="mono">{row.os_version}</td><td>{row.count}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
        <section className="card">
          <h2>Package installs</h2>
          {stats.packages.length === 0 ? <p>No catalog items reported yet.</p> : (
            <table>
              <thead><tr><th>Catalog id</th><th>Machines</th></tr></thead>
              <tbody>
                {stats.packages.map((row) => (
                  <tr key={row.package_id}><td className="mono">{row.package_id}</td><td>{row.count}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </AdminFrame>
  );
}
