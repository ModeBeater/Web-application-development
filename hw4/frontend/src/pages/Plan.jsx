/*
 * Topic plan and summary (/l/{code}/plan/, protected): the lecturer manages topics,
 * uploads the lecture material (topics are extracted from its headings and the
 * questions re-tagged), re-runs the tagging model, and sees the per-topic summary.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, API_BASE } from "../api/client";
import { useToast } from "../components/Toasts";
import { useTitle } from "../hooks";
import { fmtDateTime, plural } from "../utils";

function TopicRow({ t, index, canManage, onChange }) {
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ title: t.title, keywords: t.keywords || "", description: t.description || "" });

  const save = async (e) => {
    e.preventDefault();
    try { await api(`/api/topics/${t.id}/`, { method: "PATCH", body: form }); toast("Topic saved", "ok"); setEditing(false); await onChange(); }
    catch (err) { toast(err.message, "error"); }
  };
  const remove = async () => {
    if (!window.confirm(`Delete topic “${t.title}”? Its questions stay, without a topic.`)) return;
    try { await api(`/api/topics/${t.id}/`, { method: "DELETE" }); toast("Topic deleted"); await onChange(); }
    catch (err) { toast(err.message, "error"); }
  };

  return (
    <div className={`topic-row t${index % 8}`}>
      <div className="dot" />
      {editing ? (
        <form className="edit-form" onSubmit={save} noValidate>
          <input type="text" maxLength={120} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} autoFocus />
          <input type="text" maxLength={300} value={form.keywords} placeholder="keywords, comma, separated" onChange={(e) => setForm({ ...form, keywords: e.target.value })} />
          <textarea maxLength={4000} value={form.description} placeholder="What the topic covers (optional)" onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <div className="row">
            <button className="sm primary fixed" type="submit">Save</button>
            <button className="sm ghost fixed" type="button" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </form>
      ) : (
        <div>
          <div className="title">{t.title}<span className="muted small"> · {plural(t.question_count, "question")}</span></div>
          <div className="kw">{t.keywords ? `keywords: ${t.keywords}` : "no keywords"}</div>
          {t.description && <div className="kw">{t.description.slice(0, 140)}{t.description.length > 140 ? "…" : ""}</div>}
        </div>
      )}
      {canManage && !editing && (
        <div className="tools-inline">
          <button className="sm ghost" type="button" onClick={() => setEditing(true)}>Edit</button>
          <button className="sm danger ghost" type="button" onClick={remove}>Delete</button>
        </div>
      )}
    </div>
  );
}

function MaterialCard({ code, hasMaterial, onChange }) {
  const toast = useToast();
  const [info, setInfo] = useState(null);
  const [text, setText] = useState("");
  const [extract, setExtract] = useState(true);
  const [file, setFile] = useState(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const input = useRef(null);

  useEffect(() => {
    if (!hasMaterial) { setInfo(null); return; }
    api(`/api/lectures/${code}/material/`, { auth: false }).then(setInfo).catch(() => setInfo(null));
  }, [code, hasMaterial]);

  const upload = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      let res;
      if (file) {
        const form = new FormData();
        form.append("file", file);
        form.append("extract", extract ? "true" : "false");
        res = await api(`/api/lectures/${code}/material/`, { method: "POST", body: form }); // multipart
      } else {
        if (!text.trim()) { toast("Choose a file or paste the text", "error"); setBusy(false); return; }
        res = await api(`/api/lectures/${code}/material/`, { method: "POST", body: { text, title: "pasted text", extract } });
      }
      toast(`Material saved: ${res.topics_created} topic(s) created, ${res.topics_updated} updated, ${res.retag.tagged} of ${res.retag.processed} questions tagged`, "ok");
      setFile(null); setText(""); if (input.current) input.current.value = "";
      await onChange();
    } catch (err) { toast(err.message, "error"); }
    setBusy(false);
  };
  const remove = async () => {
    if (!window.confirm("Remove the uploaded material? The topics stay.")) return;
    try { await api(`/api/lectures/${code}/material/`, { method: "DELETE" }); toast("Material removed"); await onChange(); }
    catch (err) { toast(err.message, "error"); }
  };

  return (
    <section className="card">
      <h3>Lecture material</h3>
      <p className="muted small">
        Upload the lecture text (slides exported to text, Markdown notes or a PDF). Headings become topics, each topic gets
        keywords from its section, and the questions are re-tagged. One file per lecture; uploading again replaces it.
      </p>
      <div className="small muted" style={{ marginBottom: 10 }}>
        {info ? `Current: ${info.title || "untitled"} · ${info.characters} characters · uploaded by ${info.uploaded_by ? info.uploaded_by.display_name : "?"} · ${fmtDateTime(info.updated_at)}` : "No material uploaded yet."}
      </div>
      <form onSubmit={upload} noValidate>
        <div className={`drop${over ? " over" : ""}`}
          onDragEnter={(e) => { e.preventDefault(); setOver(true); }} onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={(e) => { e.preventDefault(); setOver(false); }}
          onDrop={(e) => { e.preventDefault(); setOver(false); if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]); }}>
          {file ? `Selected: ${file.name} ` : "Drop a .txt / .md / .pdf here or choose a file "}
          <input type="file" ref={input} accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
            onChange={(e) => setFile(e.target.files[0] || null)} />
        </div>
        <div className="field" style={{ margin: "10px 0 0" }}>
          <label htmlFor="material-text">…or paste the text</label>
          <textarea id="material-text" value={text} onChange={(e) => setText(e.target.value)}
            placeholder={"# Lecture title\n\n## First topic\ntext…\n\n## Second topic\ntext…"} />
        </div>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <label className="small muted" style={{ margin: 0, fontWeight: 500 }}>
            <input type="checkbox" checked={extract} onChange={(e) => setExtract(e.target.checked)} /> build topics from headings and re-tag
          </label>
          <div className="row fixed" style={{ gap: 8 }}>
            {info && <button className="sm danger ghost fixed" type="button" onClick={remove}>Remove material</button>}
            <button className="primary fixed" type="submit" disabled={busy}>{busy ? "Uploading…" : "Upload"}</button>
          </div>
        </div>
      </form>
    </section>
  );
}

export default function Plan() {
  const { code } = useParams();
  const toast = useToast();
  const [lecture, setLecture] = useState(null);
  const [summary, setSummary] = useState(null);
  const [status, setStatus] = useState({ text: "Loading…", error: false });
  const [newTopic, setNewTopic] = useState({ title: "", keywords: "" });
  useTitle(lecture ? `Topics · ${lecture.title}` : "Topics");

  const load = useCallback(async () => {
    try {
      const [data, sum] = await Promise.all([api(`/api/lectures/${code}/`), api(`/api/lectures/${code}/summary/`, { auth: false })]);
      setLecture(data); setSummary(sum);
      setStatus({ text: `Updated ${new Date().toLocaleTimeString()}`, error: false });
    } catch (e) { setStatus({ text: e.status === 404 ? "Lecture not found" : e.message, error: true }); }
  }, [code]);
  useEffect(() => { load(); }, [load]);

  const addTopic = async (e) => {
    e.preventDefault();
    try {
      await api(`/api/lectures/${code}/topics/`, { method: "POST", body: newTopic });
      setNewTopic({ title: "", keywords: "" }); toast("Topic added", "ok"); await load();
    } catch (err) { toast(err.message, "error"); }
  };
  const retag = async () => {
    try {
      const r = await api(`/api/lectures/${code}/retag/`, { method: "POST" });
      toast(`Re-tagged: ${r.tagged} of ${r.processed} questions got a topic (${r.untagged} left without)`, "ok");
      await load();
    } catch (e) { toast(e.message, "error"); }
  };

  if (!lecture) return <main><div className={`status${status.error ? " error" : ""}`}>{status.text}</div></main>;
  const manage = lecture.can_manage;
  const total = Math.max(1, summary ? summary.questions : 1);

  return (
    <main>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1>{lecture.title}</h1>
          <p className="sub">code <code>{lecture.code}</code> · topic plan and summary</p>
        </div>
        <div className="row fixed" style={{ gap: 8 }}>
          <Link className="btn ghost fixed" to={`/l/${code}/`}>Audience page</Link>
          <Link className="btn ghost fixed" to={`/l/${code}/screen/`}>Projector screen</Link>
          <a className="btn fixed" href={`${API_BASE}/api/lectures/${code}/export/`}>Export Markdown</a>
        </div>
      </div>

      {!manage && <p className="muted small">You can look, but only the lecture owner or an admin can change the plan.</p>}

      <div className="plan-grid">
        <div className="stack">
          <section className="card">
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
              <h3 style={{ margin: 0 }}>Topics</h3>
              {manage && <button className="sm ghost fixed" type="button" title="Run the tagging model again over all questions" onClick={retag}>Re-tag questions</button>}
            </div>
            <p className="muted small">
              Questions are filed under these topics — by the student, or by the tagging model when the student leaves the choice
              to it. Keywords are hints for the model; the description is the section of your lecture text.
            </p>
            <div>
              {!lecture.topics.length && <div className="empty"><div className="big">🗂️</div>No topics yet. Add them below or upload the lecture text.</div>}
              {lecture.topics.map((t, i) => <TopicRow key={t.id} t={t} index={i} canManage={manage} onChange={load} />)}
            </div>
            {manage && (
              <form style={{ marginTop: 14 }} onSubmit={addTopic} noValidate>
                <div className="row">
                  <div className="field" style={{ margin: 0 }}>
                    <input type="text" maxLength={120} placeholder="New topic title" required value={newTopic.title} onChange={(e) => setNewTopic({ ...newTopic, title: e.target.value })} />
                  </div>
                  <div className="field" style={{ margin: 0 }}>
                    <input type="text" maxLength={300} placeholder="keywords, comma, separated" value={newTopic.keywords} onChange={(e) => setNewTopic({ ...newTopic, keywords: e.target.value })} />
                  </div>
                  <button className="primary fixed" type="submit" disabled={!newTopic.title.trim()}>Add topic</button>
                </div>
              </form>
            )}
          </section>

          {manage && <MaterialCard code={code} hasMaterial={lecture.has_material} onChange={load} />}
        </div>

        <aside className="stack">
          <section className="card">
            <h3>Summary</h3>
            <div className="tiles" style={{ margin: "10px 0 14px" }}>
              {[["questions", "questions"], ["answered", "answered"], ["with_written_answer", "written answers"], ["participants", "people asked"]].map(([key, label]) => (
                <div className="tile" key={key}><div className="num">{summary ? summary[key] : "–"}</div><div className="label">{label}</div></div>
              ))}
            </div>
            <div className="bars">
              {(summary ? summary.topics : []).filter((t) => t.id !== null || t.questions).map((t, i) => (
                <div className={`bar ${t.id === null ? "t7" : `t${i % 8}`}`} key={t.id ?? "none"}>
                  <span>{t.title}<span className="muted small"> · {t.answered}/{t.questions} answered · {t.upvotes} votes</span></span>
                  <strong>{t.questions}</strong>
                  <div className="track"><div className="fill" style={{ width: `${Math.round((100 * t.questions) / total)}%` }} /></div>
                </div>
              ))}
            </div>
            {summary && (
              <p className="small muted" style={{ margin: "12px 0 0" }}>
                Tags: {summary.tagged_auto} by the model, {summary.tagged_manual} chosen by people, {summary.untagged} without a topic.
              </p>
            )}
          </section>
          <section className="card">
            <h3>How tagging works</h3>
            <p className="small muted" style={{ margin: 0 }}>
              Each topic (title + keywords + section text) is a document. A new question is compared with every topic by TF-IDF over
              character n-grams (cosine similarity) plus a bonus for matching keywords; the best topic is used when the score reaches
              the threshold, otherwise the question stays untagged. The same similarity shows “already asked” hints while a student types.
            </p>
          </section>
        </aside>
      </div>
      <div className={`status${status.error ? " error" : ""}`} style={{ marginTop: 10 }}>{status.text}</div>
    </main>
  );
}
