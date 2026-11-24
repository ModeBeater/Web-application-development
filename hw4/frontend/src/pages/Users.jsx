/* User management (/users/, admin only): roles, activation, deletion — PATCH/DELETE /api/users/{id}/ */

import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "../components/Toasts";
import { useDebounced, useTitle } from "../hooks";
import { fmtDate, plural } from "../utils";

const ROLES = [["", "All roles"], ["student", "Students"], ["lecturer", "Lecturers"], ["admin", "Admins"]];

function Row({ u, me, onDeleted }) {
  const toast = useToast();
  const [role, setRole] = useState(u.role);
  const [active, setActive] = useState(u.is_active);

  const patch = async (body, okMessage, revert) => {
    try { await api(`/api/users/${u.id}/`, { method: "PATCH", body }); toast(okMessage, "ok"); }
    catch (err) { toast(err.message, "error"); revert(); }
  };
  const remove = async () => {
    if (!window.confirm(`Delete ${u.username} with all their lectures, questions and upvotes?`)) return;
    try { await api(`/api/users/${u.id}/`, { method: "DELETE" }); toast("User deleted"); await onDeleted(); }
    catch (err) { toast(err.message, "error"); }
  };
  const s = u.stats || {};

  return (
    <tr>
      <td className="muted">{u.id}</td>
      <td><strong>{u.display_name}</strong><div className="muted small">@{u.username}</div></td>
      <td className="small">{u.email || "—"}</td>
      <td>
        <select value={role} onChange={(e) => { const prev = role; setRole(e.target.value); patch({ role: e.target.value }, `${u.username} is now ${e.target.value}`, () => setRole(prev)); }}>
          {["student", "lecturer", "admin"].map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </td>
      <td>
        <input type="checkbox" checked={active} onChange={(e) => { const v = e.target.checked; setActive(v); patch({ is_active: v }, `${u.username} ${v ? "activated" : "deactivated"}`, () => setActive(!v)); }} />
      </td>
      <td className="small muted">{s.lectures} lectures · {s.questions} questions · {s.upvotes_given} votes</td>
      <td className="small">{fmtDate(u.date_joined)}</td>
      <td><button className="sm danger ghost" type="button" disabled={u.id === me.id} onClick={remove}>Delete</button></td>
    </tr>
  );
}

export default function Users() {
  useTitle("Users");
  const { user: me } = useAuth();
  const [role, setRole] = useState("");
  const [query, setQuery] = useState("");
  const search = useDebounced(query.trim(), 250);
  const [page, setPage] = useState({ results: [], next: null, count: null });
  const [status, setStatus] = useState({ text: "Loading…", error: false });

  const load = useCallback(async (url = null) => {
    const params = new URLSearchParams({ limit: 25, ordering: "id" });
    if (search) params.set("search", search);
    if (role) params.set("role", role);
    try {
      const data = await api(url || `/api/users/?${params}`);
      setPage((prev) => ({ results: url ? [...prev.results, ...data.results] : data.results, next: data.next, count: data.count }));
      setStatus({ text: plural(data.count, "user"), error: false });
    } catch (e) {
      setPage({ results: [], next: null, count: null });
      setStatus({ text: e.status === 403 ? "Admin role required." : e.message, error: true });
    }
  }, [search, role]);
  useEffect(() => { load(); }, [load]);

  return (
    <main className="wide">
      <h1>Users</h1>
      <p className="sub">Change roles, deactivate or delete accounts. Admin only.</p>

      <div className="toolbar">
        <input type="search" placeholder="Search by username, name or email…" aria-label="Search users" value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="chips">
          {ROLES.map(([value, label]) => (
            <button key={value} className={`chip${role === value ? " active" : ""}`} type="button" onClick={() => setRole(value)}>{label}</button>
          ))}
        </div>
      </div>

      <div className="card table-wrap">
        <table className="data">
          <thead><tr><th>#</th><th>User</th><th>Email</th><th>Role</th><th>Active</th><th>Activity</th><th>Joined</th><th></th></tr></thead>
          <tbody>
            {page.results.map((u) => <Row key={u.id} u={u} me={me} onDeleted={() => load()} />)}
          </tbody>
        </table>
        <div style={{ textAlign: "center", marginTop: 12 }}>
          {page.next && <button type="button" onClick={() => load(page.next)}>Load more</button>}
          <div className={`status${status.error ? " error" : ""}`}>{status.text}</div>
        </div>
      </div>
    </main>
  );
}
