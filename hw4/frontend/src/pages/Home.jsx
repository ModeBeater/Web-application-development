/* Public home page: totals, the list of lectures with search and filters, "start a lecture" for lecturers. */

import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "../components/Toasts";
import { useDebounced, useTitle } from "../hooks";
import { fmtDate, plural } from "../utils";

const TILES = [["lectures", "lectures"], ["questions", "questions"], ["answered", "answered"], ["upvotes", "upvotes"], ["users", "users"]];

function LectureCard({ l, onChange }) {
  const toast = useToast();
  const toggle = async () => {
    try { await api(`/api/lectures/${l.id}/toggle/`, { method: "POST" }); await onChange(); }
    catch (e) { toast(e.message, "error"); }
  };
  const remove = async () => {
    if (!window.confirm(`Delete "${l.title}" with its ${l.question_count} questions?`)) return;
    try { await api(`/api/lectures/${l.id}/`, { method: "DELETE" }); toast("Lecture deleted"); await onChange(); }
    catch (e) { toast(e.message, "error"); }
  };
  return (
    <article className="card lecture-card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span className="code fixed">{l.code}</span>
        <span className={`pill fixed ${l.is_open ? "open" : "closed"}`}>{l.is_open ? "open" : "closed"}</span>
      </div>
      <div className="title"><Link to={`/l/${l.code}/`} style={{ color: "inherit" }}>{l.title}</Link></div>
      <div className="meta">
        <span>{l.owner.display_name}</span><span>·</span>
        <span>{plural(l.question_count, "question")}</span><span>·</span>
        <span>{fmtDate(l.created_at)}</span>
      </div>
      <div className="actions">
        <Link className="btn sm" to={`/l/${l.code}/`}>Join</Link>
        <Link className="btn sm ghost" to={`/l/${l.code}/screen/`}>Screen</Link>
        {l.can_manage && <button className="sm ghost" type="button" onClick={toggle}>{l.is_open ? "Close" : "Reopen"}</button>}
        {l.can_manage && <button className="sm danger ghost" type="button" onClick={remove}>Delete</button>}
      </div>
    </article>
  );
}

export default function Home() {
  useTitle("");
  const { isAuthed, canCreateLectures } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [filter, setFilter] = useState("");
  const [query, setQuery] = useState("");
  const search = useDebounced(query.trim(), 250);
  const [page, setPage] = useState({ results: [], next: null, count: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [title, setTitle] = useState("");

  const loadStats = useCallback(async () => {
    try { setStats(await api("/api/stats/", { auth: false })); } catch (e) { setError(e.message); }
  }, []);

  const load = useCallback(async (url = null) => {
    setLoading(true);
    const params = new URLSearchParams({ limit: 12 });
    if (search) params.set("search", search);
    if (filter === "open") params.set("is_open", "true");
    if (filter === "closed") params.set("is_open", "false");
    if (filter === "mine") params.set("owner", "me");
    try {
      const data = await api(url || `/api/lectures/?${params}`);
      setPage((prev) => ({ results: url ? [...prev.results, ...data.results] : data.results, next: data.next, count: data.count }));
      setError(null);
    } catch (e) { setError(e.message); }
    setLoading(false);
  }, [search, filter]);

  useEffect(() => { loadStats(); }, [loadStats]);
  useEffect(() => { load(); }, [load]);

  const reload = async () => { await Promise.all([load(), loadStats()]); };

  const createLecture = async (e) => {
    e.preventDefault();
    try {
      const lecture = await api("/api/lectures/", { method: "POST", body: { title } });
      toast(`Lecture ${lecture.code} created`, "ok");
      navigate(`/l/${lecture.code}/screen/`);
    } catch (err) { toast(err.message, "error"); }
  };

  const filters = [["", "All"], ["open", "Open"], ["closed", "Closed"], ...(isAuthed ? [["mine", "Mine"]] : [])];

  return (
    <main className="wide">
      <section className="hero">
        <h1>Questions from the audience, sorted by how many people want them answered.</h1>
        <p>Start a lecture, put the screen page on the projector, and let the audience ask and upvote from their phones.</p>
      </section>

      <div className="tiles">
        {TILES.map(([key, label]) => (
          <div className="tile" key={key}>
            <div className={`num${stats ? "" : " skeleton"}`}>{stats ? stats[key] : " "}</div>
            <div className="label">{label}</div>
          </div>
        ))}
      </div>

      {canCreateLectures && (
        <div className="card">
          <h3>Start a lecture</h3>
          <form className="row" onSubmit={createLecture}>
            <div className="field" style={{ margin: 0 }}>
              <label htmlFor="title" className="sr-only">Lecture title</label>
              <input type="text" id="title" maxLength={120} required value={title} onChange={(e) => setTitle(e.target.value)}
                placeholder="Lecture title, e.g. Flutter 1 · Lecture 09 · State management" />
            </div>
            <button className="primary fixed" type="submit">Start lecture</button>
          </form>
          <p className="small muted" style={{ margin: "8px 0 0" }}>You will get a join code and a QR code for the projector.</p>
        </div>
      )}

      <div className="toolbar">
        <input type="search" placeholder="Search lectures by title, code or lecturer…" aria-label="Search lectures"
          value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="chips">
          {filters.map(([value, label]) => (
            <button key={value} className={`chip${filter === value ? " active" : ""}`} type="button" onClick={() => setFilter(value)}>{label}</button>
          ))}
        </div>
      </div>

      <div className="grid">
        {!loading && !page.results.length && (
          <div className="empty" style={{ gridColumn: "1 / -1" }}><div className="big">📚</div>No lectures match.</div>
        )}
        {page.results.map((l) => <LectureCard key={l.id} l={l} onChange={reload} />)}
      </div>
      <div style={{ textAlign: "center", marginTop: 18 }}>
        {page.next && <button type="button" disabled={loading} onClick={() => load(page.next)}>Load more</button>}
        <div className={`status${error ? " error" : ""}`}>
          {error ? error : loading ? "Loading…" : page.count !== null ? plural(page.count, "lecture") : ""}
        </div>
      </div>
    </main>
  );
}
