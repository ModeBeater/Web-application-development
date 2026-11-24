/* Projector page (/l/{code}/screen/, public): QR code to join, the live board (big text, read-only), questions per topic. */

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import QuestionList from "../components/Questions";
import { useToast } from "../components/Toasts";
import { useLecturePolling, useTitle } from "../hooks";
import { plural } from "../utils";

function TopicBars({ lecture }) {
  const topics = lecture.topics || [];
  if (!topics.length) return null;
  const total = Math.max(1, lecture.questions.length);
  const untagged = lecture.questions.filter((q) => !q.topic_id).length;
  const rows = topics.map((t, i) => ({ key: t.id, title: t.title, n: t.question_count, cls: `t${i % 8}` }));
  if (untagged) rows.push({ key: "none", title: "No topic", n: untagged, cls: "t7" });
  return (
    <div className="topics-panel">
      <h2 style={{ margin: "0 0 10px" }}>Questions by topic</h2>
      <div className="bars">
        {rows.map((r) => (
          <div className={`bar ${r.cls}`} key={r.key}>
            <span>{r.title}</span><strong>{r.n}</strong>
            <div className="track"><div className="fill" style={{ width: `${Math.round((100 * r.n) / total)}%` }} /></div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Screen() {
  const { code } = useParams();
  const toast = useToast();
  const { lecture, error, status, refresh } = useLecturePolling(code);
  const [join, setJoin] = useState(null);
  useTitle(lecture ? `Screen · ${lecture.title}` : "Screen");

  useEffect(() => {
    api(`/api/lectures/${code}/join/`, { auth: false }).then(setJoin).catch(() => setJoin(null));
  }, [code]);

  if (error && error.status === 404) {
    return <main className="wide"><div className="card empty"><div className="big">🔍</div>No lecture with code <code>{code}</code>.</div></main>;
  }
  if (!lecture) return <main className="wide"><div className="status">{status}</div></main>;

  const toggle = async () => {
    try { await api(`/api/lectures/${code}/toggle/`, { method: "POST" }); await refresh(); }
    catch (e) { toast(e.message, "error"); }
  };

  return (
    <main className="wide">
      <h1>{lecture.title}</h1>
      <div className="controls">
        <span className={`pill ${lecture.is_open ? "open" : "closed"}`}>{lecture.is_open ? "open" : "closed"}</span>
        <span className="muted small">{lecture.owner.display_name} · {plural(lecture.question_count, "question")}</span>
        {lecture.can_manage && <button type="button" onClick={toggle}>{lecture.is_open ? "Close questions" : "Reopen questions"}</button>}
        <Link className="btn ghost sm" to={`/l/${code}/`}>Audience page</Link>
        <span className={`status${error ? " error" : ""}`}>{status}</span>
      </div>

      <div className="screen">
        <div>
          <QuestionList questions={lecture.questions} mode="screen" topics={lecture.topics} onChange={refresh} />
        </div>
        <aside className="join card">
          {/* The QR code is an inline SVG made by the API (segno); it encodes join_url */}
          {join ? <div className="qr" dangerouslySetInnerHTML={{ __html: join.qr_svg }} /> : <div className="qr skeleton" style={{ aspectRatio: "1" }} />}
          <div className="code">{lecture.code}</div>
          <div className="url">{join ? join.join_url : lecture.join_url}</div>
          {join && join.source === "tunnel" && <div className="via">via Cloudflare tunnel · works from any network</div>}
          {join && join.local_only && (
            <div className="hint">This address works only on this computer. Start the tunnel (docker compose --profile tunnel up -d) or set PUBLIC_URL in .env to your LAN address.</div>
          )}
          <p className="small muted" style={{ margin: "12px 0 0" }}>Scan to join, sign in, ask and upvote.</p>
          <TopicBars lecture={lecture} />
        </aside>
      </div>
    </main>
  );
}
