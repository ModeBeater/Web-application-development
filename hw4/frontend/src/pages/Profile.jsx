/*
 * Personal cabinet (/me/, protected): who I am, my lectures and questions,
 * edit the profile (username, name, email), change the password, inspect the JWT.
 */

import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { RolePill } from "../components/Layout";
import QuestionList from "../components/Questions";
import { useToast } from "../components/Toasts";
import { useTitle } from "../hooks";
import { fieldErrors, fmtDate, fmtDateTime, initials, plural } from "../utils";

const TABS = [["lectures", "My lectures"], ["questions", "My questions"], ["profile", "Profile"], ["security", "Security"], ["session", "Session"]];
const STATS = [["lectures", "my lectures"], ["questions", "my questions"], ["upvotes_given", "upvotes given"], ["upvotes_received", "upvotes received"]];

function Field({ name, label, help, errors, children }) {
  return (
    <div className={`field${errors[name] ? " invalid" : ""}`}>
      <label htmlFor={name}>{label}</label>
      {children}
      {errors[name] ? <div className="error">{errors[name]}</div> : help ? <div className="help">{help}</div> : null}
    </div>
  );
}

function MyLectures({ onChange }) {
  const toast = useToast();
  const { canCreateLectures } = useAuth();
  const [lectures, setLectures] = useState(null);
  const [title, setTitle] = useState("");

  const load = useCallback(async () => {
    try { setLectures((await api("/api/lectures/?owner=me&limit=50")).results); }
    catch (e) { toast(e.message, "error"); }
  }, [toast]);
  useEffect(() => { load(); }, [load]);

  const create = async (e) => {
    e.preventDefault();
    try {
      const l = await api("/api/lectures/", { method: "POST", body: { title } });
      toast(`Lecture ${l.code} created`, "ok"); setTitle("");
      await Promise.all([load(), onChange()]);
    } catch (err) { toast(err.message, "error"); }
  };
  const toggle = async (l) => {
    try { await api(`/api/lectures/${l.id}/toggle/`, { method: "POST" }); await load(); } catch (e) { toast(e.message, "error"); }
  };
  const remove = async (l) => {
    if (!window.confirm(`Delete "${l.title}"?`)) return;
    try { await api(`/api/lectures/${l.id}/`, { method: "DELETE" }); toast("Lecture deleted"); await Promise.all([load(), onChange()]); }
    catch (e) { toast(e.message, "error"); }
  };

  return (
    <>
      {canCreateLectures ? (
        <div className="card" style={{ marginBottom: 14 }}>
          <form className="row" onSubmit={create}>
            <div className="field" style={{ margin: 0 }}>
              <input type="text" maxLength={120} placeholder="New lecture title" required value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <button className="primary fixed" type="submit">Start lecture</button>
          </form>
        </div>
      ) : (
        <p className="muted small">Only lecturers run lectures. Your account is a student account — an admin can change the role.</p>
      )}
      <div className="grid">
        {lectures === null && <div className="status">Loading…</div>}
        {lectures && !lectures.length && <div className="empty" style={{ gridColumn: "1 / -1" }}><div className="big">🎤</div>No lectures yet.</div>}
        {(lectures || []).map((l) => (
          <article className="card lecture-card" key={l.id}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <span className="code fixed">{l.code}</span>
              <span className={`pill fixed ${l.is_open ? "open" : "closed"}`}>{l.is_open ? "open" : "closed"}</span>
            </div>
            <div className="title">{l.title}</div>
            <div className="meta">{plural(l.question_count, "question")} · {fmtDate(l.created_at)}</div>
            <div className="actions">
              <Link className="btn sm" to={`/l/${l.code}/screen/`}>Screen</Link>
              <Link className="btn sm ghost" to={`/l/${l.code}/`}>Audience</Link>
              <Link className="btn sm ghost" to={`/l/${l.code}/plan/`}>Topics{l.topic_count ? ` (${l.topic_count})` : ""}</Link>
              <button className="sm ghost" type="button" onClick={() => toggle(l)}>{l.is_open ? "Close" : "Reopen"}</button>
              <button className="sm danger ghost" type="button" onClick={() => remove(l)}>Delete</button>
            </div>
          </article>
        ))}
      </div>
    </>
  );
}

function MyQuestions({ onChange }) {
  const toast = useToast();
  const [questions, setQuestions] = useState(null);
  const load = useCallback(async () => {
    try { setQuestions((await api("/api/questions/?author=me&limit=100")).results); }
    catch (e) { toast(e.message, "error"); }
  }, [toast]);
  useEffect(() => { load(); }, [load]);
  if (questions === null) return <div className="status">Loading…</div>;
  return <QuestionList questions={questions} mode="list" onChange={async () => { await Promise.all([load(), onChange()]); }} />;
}

function ProfileForm({ user, onSaved }) {
  const toast = useToast();
  const [form, setForm] = useState({ username: user.username, first_name: user.first_name || "", last_name: user.last_name || "", email: user.email || "" });
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { setForm({ username: user.username, first_name: user.first_name || "", last_name: user.last_name || "", email: user.email || "" }); }, [user]);
  const set = (name) => (e) => setForm((f) => ({ ...f, [name]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErrors({});
    try {
      await api("/api/auth/me/", { method: "PATCH", body: form });
      toast("Profile saved", "ok");
      await onSaved();
    } catch (err) {
      const fields = fieldErrors(err.data, Object.keys(form));
      if (Object.keys(fields).length) setErrors(fields); else toast(err.message, "error");
    }
    setBusy(false);
  };

  return (
    <div className="card">
      <form onSubmit={submit} noValidate>
        <Field name="username" label="Username" help="Your sign-in name; must be unique. Letters, digits and @/./+/-/_ only." errors={errors}>
          <input type="text" id="username" autoComplete="username" minLength={3} maxLength={150} value={form.username} onChange={set("username")} />
        </Field>
        <div className="row">
          <Field name="first_name" label="First name" errors={errors}>
            <input type="text" id="first_name" value={form.first_name} onChange={set("first_name")} />
          </Field>
          <Field name="last_name" label="Last name" errors={errors}>
            <input type="text" id="last_name" value={form.last_name} onChange={set("last_name")} />
          </Field>
        </div>
        <Field name="email" label="Email" errors={errors}>
          <input type="email" id="email" value={form.email} onChange={set("email")} />
        </Field>
        <dl className="kv" style={{ margin: "0 0 16px" }}>
          <dt>Role</dt><dd>{user.role}</dd>
          <dt>Member since</dt><dd>{fmtDate(user.date_joined)}</dd>
          <dt>Last login</dt><dd>{user.last_login ? fmtDateTime(user.last_login) : "—"}</dd>
        </dl>
        <button className="primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button>
      </form>
    </div>
  );
}

function PasswordForm({ onChanged }) {
  const toast = useToast();
  const { saveSession } = useAuth();
  const [form, setForm] = useState({ current_password: "", new_password: "" });
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const set = (name) => (e) => setForm((f) => ({ ...f, [name]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErrors({});
    try {
      const data = await api("/api/auth/me/password/", { method: "POST", body: form });
      saveSession(data); // the API returns a fresh token pair
      setForm({ current_password: "", new_password: "" });
      toast("Password updated — new tokens issued", "ok");
      onChanged();
    } catch (err) {
      const fields = fieldErrors(err.data, Object.keys(form));
      if (Object.keys(fields).length) setErrors(fields); else toast(err.message, "error");
    }
    setBusy(false);
  };

  return (
    <div className="card">
      <h3>Change password</h3>
      <form onSubmit={submit} noValidate>
        <Field name="current_password" label="Current password" errors={errors}>
          <input type="password" id="current_password" autoComplete="current-password" required value={form.current_password} onChange={set("current_password")} />
        </Field>
        <Field name="new_password" label="New password" help="At least 8 characters, not only digits, not too common." errors={errors}>
          <input type="password" id="new_password" autoComplete="new-password" required minLength={8} value={form.new_password} onChange={set("new_password")} />
        </Field>
        <button className="primary" type="submit" disabled={busy}>{busy ? "Updating…" : "Update password"}</button>
      </form>
    </div>
  );
}

function SessionPanel({ tick }) {
  const toast = useToast();
  const navigate = useNavigate();
  const { claims, refreshTokens, logout } = useAuth();
  const [, force] = useState(0);
  const c = claims();
  useEffect(() => { force((n) => n + 1); }, [tick]);

  const refreshNow = async () => {
    if (await refreshTokens()) { toast("New access and refresh tokens received", "ok"); force((n) => n + 1); }
    else { toast("Refresh token rejected — please sign in again", "error"); navigate("/login/?next=/me/"); }
  };

  return (
    <div className="card">
      <h3>Tokens</h3>
      <p className="muted small">
        The browser keeps two JWTs in localStorage. The <strong>access</strong> token is sent with every request
        (<code>Authorization: Bearer …</code>) and lives 15 minutes; when it expires the client exchanges the{" "}
        <strong>refresh</strong> token for a new pair (rotation — the old refresh token is revoked on the server).
      </p>
      <dl className="kv">
        <dt>Access expires</dt><dd>{c ? fmtDateTime(new Date(c.exp * 1000).toISOString()) : "—"}</dd>
        <dt>Role claim</dt><dd>{c ? c.role : "—"}</dd>
        <dt>User id claim</dt><dd>{c ? c.user_id : "—"}</dd>
        <dt>Username claim</dt><dd>{c ? c.username : "—"}</dd>
      </dl>
      <div className="row" style={{ marginTop: 16 }}>
        <button className="fixed" type="button" onClick={refreshNow}>Refresh tokens now</button>
        <button className="fixed danger" type="button" onClick={async () => { await logout(); navigate("/"); }}>Sign out</button>
      </div>
    </div>
  );
}

export default function Profile() {
  useTitle("Personal cabinet");
  const { user, reload } = useAuth();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const tab = TABS.some(([key]) => key === params.get("tab")) ? params.get("tab") : "lectures";
  const [tick, setTick] = useState(0);

  const refresh = useCallback(async () => {
    try { await reload(); } catch (e) { toast(e.message, "error"); }
  }, [reload, toast]);

  if (!user) return null; // RequireAuth makes sure we never get here signed out

  return (
    <main>
      <div className="card profile-head">
        <span className="avatar">{initials(user)}</span>
        <div style={{ flex: 1 }}>
          <h1>{user.display_name}</h1>
          <div className="muted">@{user.username} · <RolePill role={user.role} /></div>
        </div>
        {user.role === "admin" && <Link className="btn" to="/users/">Manage users</Link>}
      </div>

      <div className="tiles">
        {STATS.map(([key, label]) => (
          <div className="tile" key={key}><div className="num">{user.stats ? user.stats[key] : "–"}</div><div className="label">{label}</div></div>
        ))}
      </div>

      <div className="tabs">
        {TABS.map(([key, label]) => (
          <button key={key} type="button" className={tab === key ? "active" : ""} onClick={() => setParams({ tab: key })}>{label}</button>
        ))}
      </div>

      <section className="tab-panel active">
        {tab === "lectures" && <MyLectures onChange={refresh} />}
        {tab === "questions" && <MyQuestions onChange={refresh} />}
        {tab === "profile" && <ProfileForm user={user} onSaved={refresh} />}
        {tab === "security" && <PasswordForm onChanged={() => setTick((n) => n + 1)} />}
        {tab === "session" && <SessionPanel tick={tick} />}
      </section>
    </main>
  );
}
