import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api, del, getToken, patch, post, put, setToken } from "./api";

type Job = Record<string, any>;
const COUNTRIES = ["Tanzania", "Kenya", "Uganda", "Rwanda", "Burundi"];

function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const reload = () => fn().then(setData).catch((e) => setError(e.message));
  useEffect(() => { reload(); }, deps); // eslint-disable-line
  return { data, error, reload };
}
const Badge = ({ v }: { v?: string | null }) => <span className={`badge b-${v}`}>{v || "—"}</span>;
const fmt = (d?: string | null) => (d ? new Date(d).toLocaleString() : "—");

function Login() {
  const nav = useNavigate();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [err, setErr] = useState("");
  return (
    <div className="login"><form className="card" onSubmit={async (e) => {
      e.preventDefault(); setErr("");
      try { const r = await post("/auth/login", { email, password }); setToken(r.access_token); nav("/"); } catch (x: any) { setErr(x.message); }
    }}>
      <h2>Kazi Robot</h2><p className="muted">Sign in to the admin dashboard</p>
      <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
      <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
      {err && <p className="err">{err}</p>}
      <button style={{ width: "100%" }}>Sign in</button>
    </form></div>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const { data: me } = useLoad(() => api("/auth/me"));
  const links: [string, string][] = [["/", "Dashboard"], ["/jobs", "All Jobs"], ["/jobs/published", "Published Jobs"], ["/jobs/rejected", "Rejected Jobs"],
    ["/jobs/expired", "Expired Jobs"], ["/sources", "Job Sources"], ["/wordpress", "WordPress Settings"], ["/automation", "Automation Settings"], ["/logs", "Logs & Errors"], ["/users", "Admin Users"]];
  return (
    <div className="layout">
      <nav className="side">
        <div className="logo"><span>KR</span> Kazi Robot</div>
        {links.map(([to, l]) => <NavLink key={to} to={to} end>{l}</NavLink>)}
        <div style={{ marginTop: 20, fontSize: 13, padding: "0 10px" }}>
          {me && <div>{me.email}<br /><small>{me.role}</small></div>}
          <a href="#" onClick={() => { setToken(null); location.href = "/login"; }}>Sign out</a>
        </div>
      </nav>
      <main className="main">{children}</main>
    </div>
  );
}

function Dashboard() {
  const { data: s, error } = useLoad(() => api("/stats"));
  if (error) return <p className="err">{error}</p>;
  if (!s) return <p>Loading…</p>;
  const total = s.publish_success + s.publish_failure;
  const cards = [["Total collected", s.total], ["Published", s.published], ["Waiting to publish", s.pending], ["Rejected", s.rejected],
    ["Expired", s.expired], ["Active sources", `${s.active_sources}/${s.total_sources}`], ["Publish success", s.publish_success], ["Publish failures", s.publish_failure]];
  return (<>
    <div className="top"><h1>Dashboard</h1></div>
    <div className="grid">{cards.map(([l, v]) => <div className="card stat" key={l}><small>{l}</small><b>{v}</b></div>)}</div>
    <div className="grid">
      <div className="card"><h3>Publishing success rate</h3><b style={{ font: "700 34px Space Grotesk" }}>{total ? Math.round((s.publish_success / total) * 100) : 0}%</b><p className="muted">{total} publish attempts recorded</p></div>
      <div className="card"><h3>Jobs by country</h3>{Object.entries(s.by_country).map(([c, n]: any) => <div key={c} className="row" style={{ justifyContent: "space-between" }}><span>{c}</span><b>{n}</b></div>)}</div>
    </div>
  </>);
}

function JobModal({ id, onClose }: { id: number; onClose: () => void }) {
  const { data: j, reload } = useLoad<Job>(() => api(`/jobs/${id}`), [id]);
  const [msg, setMsg] = useState("");
  if (!j) return null;
  const act = async (fn: () => Promise<any>) => { setMsg("Working…"); try { const r = await fn(); setMsg(JSON.stringify(r.result ?? r)); reload(); } catch (e: any) { setMsg(e.message); } };
  const F = ({ k, l }: { k: string; l: string }) => <p><b>{l}:</b> {j[k] ? String(j[k]) : <span className="muted">not provided</span>}</p>;
  return (
    <div className="modal" onClick={onClose}><div className="card" onClick={(e) => e.stopPropagation()}>
      <div className="top"><h2>{j.title}</h2><button className="ghost" onClick={onClose}>Close</button></div>
      <p><Badge v={j.status} /> {j.rejection_reasons?.length > 0 && <span className="err">{j.rejection_reasons.join(", ")}</span>}</p>
      <F k="employer" l="Employer" /><F k="country" l="Country" /><F k="location" l="Location" /><F k="category" l="Category" />
      <F k="published_at" l="Published" /><F k="deadline" l="Deadline" /><F k="apply_url" l="Application URL" />
      <p><b>Source:</b> <a href={j.source_url} target="_blank" rel="noreferrer">{j.source_url}</a></p>
      {j.wp_link && <p><b>WordPress:</b> <a href={j.wp_link} target="_blank" rel="noreferrer">{j.wp_link}</a></p>}
      {j.last_error && <p className="err">Last error: {j.last_error}</p>}
      <h3>Description</h3><pre>{j.description || "—"}</pre>
      <h3>Qualifications</h3><pre>{j.qualifications || "—"}</pre>
      <h3>How to apply</h3><pre>{j.how_to_apply || "—"}</pre>
      <div className="row">
        {!j.wp_post_id && ["validated", "failed"].includes(j.status) && <button onClick={() => act(() => post(`/jobs/${id}/publish`))}>Publish now</button>}
        {!j.wp_post_id && j.status === "rejected" && <button onClick={() => act(() => post(`/jobs/${id}/publish?force=true`))}>Publish anyway</button>}
        {!j.wp_post_id && ["failed", "rejected"].includes(j.status) && <button className="ghost" onClick={() => act(() => post(`/jobs/${id}/requeue`))}>Mark as valid & requeue</button>}
        <button className="danger" onClick={() => confirm("Delete job?") && del(`/jobs/${id}`).then(onClose)}>Delete</button>
      </div>
      {msg && <pre>{msg}</pre>}
    </div></div>
  );
}

function Jobs({ status, title }: { status?: string; title: string }) {
  const [q, setQ] = useState(""); const [country, setCountry] = useState(""); const [page, setPage] = useState(1); const [open, setOpen] = useState<number | null>(null);
  const params = new URLSearchParams({ page: String(page), ...(status ? { status } : {}), ...(q ? { q } : {}), ...(country ? { country } : {}) });
  const { data, error, reload } = useLoad<any>(() => api(`/jobs?${params}`), [status, q, country, page]);
  return (<>
    <div className="top"><h1>{title}</h1>
      <div className="row"><input placeholder="Search title, employer, location" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} style={{ width: 260 }} />
        <select value={country} onChange={(e) => setCountry(e.target.value)} style={{ width: 150 }}><option value="">All countries</option>{COUNTRIES.map((c) => <option key={c}>{c}</option>)}</select></div></div>
    {error && <p className="err">{error}</p>}
    <div className="wrap"><table><thead><tr><th>Title</th><th>Employer</th><th>Country</th><th>Category</th><th>Deadline</th><th>Status</th><th>Collected</th></tr></thead>
      <tbody>{data?.items.map((j: Job) => (
        <tr key={j.id} onClick={() => setOpen(j.id)} style={{ cursor: "pointer" }}>
          <td>{j.title}{j.rejection_reasons?.length > 0 && <div className="err" style={{ fontSize: 12 }}>{j.rejection_reasons.join(", ")}</div>}</td>
          <td>{j.employer || "—"}</td><td>{j.country || "—"}</td><td>{j.category || "—"}</td><td>{j.deadline || "—"}</td><td><Badge v={j.status} /></td><td>{fmt(j.created_at)}</td></tr>))}
        {data?.items.length === 0 && <tr><td colSpan={7} className="muted">No jobs.</td></tr>}</tbody></table></div>
    <div className="row" style={{ marginTop: 12 }}><button className="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
      <span className="muted">Page {page} · {data?.total ?? 0} jobs</span><button className="ghost" disabled={!data || page * 25 >= data.total} onClick={() => setPage(page + 1)}>Next</button></div>
    {open && <JobModal id={open} onClose={() => { setOpen(null); reload(); }} />}
  </>);
}

const emptySource = { name: "", type: "rss", url: "", country: "Tanzania", enabled: true, reliability: 80, interval_minutes: "", config: "{}" };
function Sources() {
  const { data, error, reload } = useLoad<any[]>(() => api("/sources"));
  const [edit, setEdit] = useState<any>(null); const [out, setOut] = useState<any>(null); const [err, setErr] = useState("");
  const save = async () => {
    setErr("");
    try {
      const body = { ...edit, interval_minutes: edit.interval_minutes ? Number(edit.interval_minutes) : null, reliability: Number(edit.reliability), config: JSON.parse(edit.config || "{}"), country: edit.country || null };
      edit.id ? await put(`/sources/${edit.id}`, body) : await post("/sources", body);
      setEdit(null); reload();
    } catch (e: any) { setErr(e.message); }
  };
  const run = async (id: number, kind: "test" | "run") => { setOut({ loading: true }); try { setOut(await post(`/sources/${id}/${kind}`)); reload(); } catch (e: any) { setOut({ error: e.message }); } };
  return (<>
    <div className="top"><h1>Job Sources</h1><button onClick={() => setEdit({ ...emptySource })}>Add source</button></div>
    <p className="muted">Only add RSS feeds, official APIs, or websites whose terms and robots.txt allow automated collection. The robot never bypasses logins or CAPTCHAs.</p>
    {error && <p className="err">{error}</p>}
    <div className="wrap"><table><thead><tr><th>Name</th><th>Type</th><th>Country</th><th>Reliability</th><th>Last run</th><th>Enabled</th><th></th></tr></thead>
      <tbody>{data?.map((s) => (<tr key={s.id}>
        <td><b>{s.name}</b><div className="muted" style={{ fontSize: 12, wordBreak: "break-all" }}>{s.url}</div></td><td>{s.type}</td><td>{s.country || "—"}</td><td>{s.reliability}</td>
        <td><Badge v={s.last_status} /> <div style={{ fontSize: 12 }}>{fmt(s.last_run_at)}</div><div className="muted" style={{ fontSize: 12 }}>{s.last_message}</div></td>
        <td><input type="checkbox" style={{ width: "auto" }} checked={s.enabled} onChange={async () => { await put(`/sources/${s.id}`, { ...s, enabled: !s.enabled }); reload(); }} /></td>
        <td><div className="row"><button className="ghost" onClick={() => run(s.id, "test")}>Test</button><button className="ghost" onClick={() => run(s.id, "run")}>Collect now</button>
          <button className="ghost" onClick={() => setEdit({ ...s, interval_minutes: s.interval_minutes ?? "", config: JSON.stringify(s.config, null, 2) })}>Edit</button>
          <button className="danger" onClick={() => confirm("Delete source?") && del(`/sources/${s.id}`).then(reload)}>Delete</button></div></td></tr>))}</tbody></table></div>
    {out && <div className="card" style={{ marginTop: 14 }}><div className="top"><h3>Result</h3><button className="ghost" onClick={() => setOut(null)}>Close</button></div><pre>{out.loading ? "Running…" : JSON.stringify(out, null, 2)}</pre></div>}
    {edit && <div className="modal"><div className="card">
      <h2>{edit.id ? "Edit source" : "Add source"}</h2>
      <div className="form">
        <label>Name<input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></label>
        <label>Type<select value={edit.type} onChange={(e) => setEdit({ ...edit, type: e.target.value })}><option value="rss">RSS feed</option><option value="api">JSON API</option><option value="html">Website (permitted)</option></select></label>
        <label>URL<input value={edit.url} onChange={(e) => setEdit({ ...edit, url: e.target.value })} /></label>
        <label>Default country<select value={edit.country || ""} onChange={(e) => setEdit({ ...edit, country: e.target.value })}><option value="">Auto-detect</option>{COUNTRIES.map((c) => <option key={c}>{c}</option>)}</select></label>
        <label>Reliability (0-100)<input type="number" value={edit.reliability} onChange={(e) => setEdit({ ...edit, reliability: e.target.value })} /></label>
        <label>Interval minutes (blank = global)<input type="number" value={edit.interval_minutes} onChange={(e) => setEdit({ ...edit, interval_minutes: e.target.value })} /></label>
      </div>
      <label>Config (JSON) <span className="muted">— field mappings / selectors, see README</span><textarea rows={7} value={edit.config} onChange={(e) => setEdit({ ...edit, config: e.target.value })} style={{ fontFamily: "monospace" }} /></label>
      <label className="row"><input type="checkbox" style={{ width: "auto" }} checked={edit.enabled} onChange={(e) => setEdit({ ...edit, enabled: e.target.checked })} /> Enabled</label>
      {err && <p className="err">{err}</p>}
      <div className="row"><button onClick={save}>Save</button><button className="ghost" onClick={() => setEdit(null)}>Cancel</button></div>
    </div></div>}
  </>);
}

function SettingsForm({ keys }: { keys: [string, string, "bool" | "num" | "list" | "text" | "select", string[]?][] }) {
  const { data, reload } = useLoad<any>(() => api("/settings"));
  const [form, setForm] = useState<any>(null); const [msg, setMsg] = useState("");
  useEffect(() => { if (data) setForm(data); }, [data]);
  if (!form) return <p>Loading…</p>;
  const save = async () => {
    const body: any = {};
    for (const [k, , t] of keys) body[k] = t === "num" ? Number(form[k]) : t === "list" ? (Array.isArray(form[k]) ? form[k] : String(form[k]).split(",").map((x) => x.trim()).filter(Boolean)) : form[k];
    try { await put("/settings", body); setMsg("Saved."); reload(); } catch (e: any) { setMsg(e.message); }
  };
  return (<div className="card"><div className="form">{keys.map(([k, l, t, opts]) => t === "bool"
    ? <label key={k} className="row"><input type="checkbox" style={{ width: "auto" }} checked={!!form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.checked })} />{l}</label>
    : t === "select" ? <label key={k}>{l}<select value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })}>{opts!.map((o) => <option key={o}>{o}</option>)}</select></label>
    : <label key={k}>{l}<input type={t === "num" ? "number" : "text"} value={Array.isArray(form[k]) ? form[k].join(", ") : form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></label>)}
  </div><div className="row"><button onClick={save}>Save settings</button><span className="okt">{msg}</span></div></div>);
}

function WordPressPage() {
  const { data } = useLoad<any>(() => api("/wordpress"));
  const [res, setRes] = useState<any>(null);
  return (<>
    <div className="top"><h1>WordPress Settings</h1></div>
    <div className="card" style={{ marginBottom: 16 }}>
      <h3>Connection</h3>
      <p>Status: {data?.configured ? <span className="okt">Configured</span> : <span className="err">Not configured</span>}</p>
      <p>Site: <b>{data?.url || "—"}</b> · User: <b>{data?.username || "—"}</b></p>
      <p className="muted">Credentials are stored only in the server's <code>.env</code> file (WP_URL, WP_USERNAME, WP_APP_PASSWORD) and are never sent to the browser. Edit them on the server and run <code>docker compose up -d</code>.</p>
      <button onClick={async () => { setRes({ loading: true }); setRes(await post("/wordpress/test").catch((e) => ({ error: e.message }))); }}>Test connection</button>
      {res && <pre>{res.loading ? "Testing…" : JSON.stringify(res, null, 2)}</pre>}
    </div>
    <h3>Publishing options</h3>
    <SettingsForm keys={[["wp_post_status", "Post status", "select", ["publish", "draft", "pending"]], ["wp_default_categories", "Default categories (comma separated)", "list"],
      ["wp_extra_tags", "Extra tags (comma separated)", "list"], ["use_job_category_as_wp_category", "Add job category as WP category", "bool"], ["use_country_as_tag", "Add country as tag", "bool"]]} />
  </>);
}

function AutomationPage() {
  return (<><div className="top"><h1>Automation Settings</h1></div>
    <SettingsForm keys={[["automation_enabled", "Automation enabled", "bool"], ["auto_publish", "Auto-publish validated jobs", "bool"], ["collect_interval_minutes", "Collect interval (minutes)", "num"],
      ["max_publish_attempts", "Max publish attempts", "num"], ["min_source_reliability", "Minimum source reliability", "num"], ["max_job_age_days", "Expire jobs without deadline after (days)", "num"],
      ["required_fields", "Required fields (title, employer, description, source_url, location, deadline, apply_url…)", "list"], ["require_apply_method", "Require apply URL or instructions", "bool"],
      ["allowed_countries", "Allowed countries", "list"]]} />
  </>);
}

function Logs() {
  const [level, setLevel] = useState(""); const [page, setPage] = useState(1);
  const { data } = useLoad<any>(() => api(`/logs?page=${page}${level ? `&level=${level}` : ""}`), [level, page]);
  return (<>
    <div className="top"><h1>Logs & Errors</h1><select style={{ width: 160 }} value={level} onChange={(e) => { setLevel(e.target.value); setPage(1); }}><option value="">All levels</option><option>INFO</option><option>WARNING</option><option>ERROR</option></select></div>
    <div className="wrap"><table><thead><tr><th>Time</th><th>Level</th><th>Event</th><th>Message</th></tr></thead>
      <tbody>{data?.items.map((l: any) => <tr key={l.id}><td style={{ whiteSpace: "nowrap" }}>{fmt(l.created_at)}</td><td><Badge v={l.level} /></td><td>{l.event}</td><td>{l.message}</td></tr>)}</tbody></table></div>
    <div className="row" style={{ marginTop: 12 }}><button className="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button><span className="muted">Page {page} · {data?.total ?? 0}</span>
      <button className="ghost" disabled={!data || page * 50 >= data.total} onClick={() => setPage(page + 1)}>Next</button></div>
  </>);
}

function Users() {
  const { data, error, reload } = useLoad<any[]>(() => api("/users"));
  const [f, setF] = useState({ email: "", full_name: "", password: "", role: "editor" }); const [err, setErr] = useState("");
  return (<>
    <div className="top"><h1>Admin Users</h1></div>
    {error && <p className="err">{error}</p>}
    <div className="wrap"><table><thead><tr><th>Email</th><th>Name</th><th>Role</th><th>Active</th><th></th></tr></thead>
      <tbody>{data?.map((u) => <tr key={u.id}><td>{u.email}</td><td>{u.full_name || "—"}</td>
        <td><select value={u.role} onChange={(e) => patch(`/users/${u.id}`, { role: e.target.value }).then(reload).catch((x) => alert(x.message))}><option>admin</option><option>editor</option><option>viewer</option></select></td>
        <td><input type="checkbox" style={{ width: "auto" }} checked={u.is_active} onChange={() => patch(`/users/${u.id}`, { is_active: !u.is_active }).then(reload).catch((x) => alert(x.message))} /></td>
        <td><div className="row"><button className="ghost" onClick={() => { const p = prompt("New password (min 10 chars)"); p && patch(`/users/${u.id}`, { password: p }).then(() => alert("Password changed")).catch((x) => alert(x.message)); }}>Reset password</button>
          <button className="danger" onClick={() => confirm("Delete user?") && del(`/users/${u.id}`).then(reload).catch((x) => alert(x.message))}>Delete</button></div></td></tr>)}</tbody></table></div>
    <div className="card" style={{ marginTop: 16 }}><h3>Add user</h3><div className="form">
      <label>Email<input value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></label>
      <label>Name<input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></label>
      <label>Password (min 10)<input type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></label>
      <label>Role<select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}><option>admin</option><option>editor</option><option>viewer</option></select></label></div>
      {err && <p className="err">{err}</p>}
      <button onClick={() => post("/users", f).then(() => { setF({ email: "", full_name: "", password: "", role: "editor" }); setErr(""); reload(); }).catch((x) => setErr(x.message))}>Create user</button>
    </div>
    <p className="muted">Roles: <b>viewer</b> can view; <b>editor</b> can manage sources, test and publish; <b>admin</b> can also change settings and users.</p>
  </>);
}

export default function App() {
  if (!getToken() && location.pathname !== "/login") return <Navigate to="/login" />;
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="*" element={<Shell><Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/jobs" element={<Jobs title="All Jobs" />} />
        <Route path="/jobs/published" element={<Jobs status="published" title="Published Jobs" />} />
        <Route path="/jobs/rejected" element={<Jobs status="rejected" title="Rejected Jobs" />} />
        <Route path="/jobs/expired" element={<Jobs status="expired" title="Expired Jobs" />} />
        <Route path="/sources" element={<Sources />} />
        <Route path="/wordpress" element={<WordPressPage />} />
        <Route path="/automation" element={<AutomationPage />} />
        <Route path="/logs" element={<Logs />} />
        <Route path="/users" element={<Users />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes></Shell>} />
    </Routes>
  );
}
