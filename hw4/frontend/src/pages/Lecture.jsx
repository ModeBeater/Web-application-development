/*
 * Audience page (/l/{code}/, public): the live question board, the "ask" form with
 * hints from the tagging model while typing (similar questions + the topic the model
 * would pick), a topic filter, and the lecturer tools inside the cards.
 */

import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import QuestionList, { TopicFilterBar } from "../components/Questions";
import { useToast } from "../components/Toasts";
import { useDebounced, useLecturePolling, useTitle } from "../hooks";
import { plural } from "../utils";

// Live hints under the question field: similar questions already asked + the topic the model would pick
function AskAssistant({ code, text, onChange }) {
  const { isAuthed } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const query = useDebounced(text.trim(), 450);
  const [hints, setHints] = useState(null);

  useEffect(() => {
    if (query.length < 6) { setHints(null); return undefined; }
    let cancelled = false;
    const q = encodeURIComponent(query);
    Promise.all([
      api(`/api/lectures/${code}/similar/?text=${q}`, { auth: false }),
      api(`/api/lectures/${code}/suggest/?text=${q}`, { auth: false }),
    ]).then(([similar, suggestion]) => { if (!cancelled) setHints({ similar, suggestion }); })
      .catch(() => { if (!cancelled) setHints(null); });
    return () => { cancelled = true; };
  }, [code, query]);

  if (!hints || (!hints.suggestion.topic_title && !hints.similar.length)) return null;

  const vote = async (q) => {
    if (!isAuthed) { navigate(`/login/?next=${encodeURIComponent(window.location.pathname)}`); return; }
    try { await api(`/api/questions/${q.id}/upvote/`, { method: "POST" }); toast(q.voted ? "Vote removed" : "Voted", "ok"); await onChange(); }
    catch (e) { toast(e.message, "error"); }
  };

  return (
    <div className="assistant">
      {hints.suggestion.topic_title && (
        <div className="hint-line">
          Will be filed under <span className="pill topic">{hints.suggestion.topic_title}</span>
          <span className="muted small"> (confidence {hints.suggestion.score.toFixed(2)}) — or pick a topic below</span>
        </div>
      )}
      {hints.similar.length > 0 && (
        <div className="hint-line"><strong>Already asked?</strong> Upvote instead of posting a duplicate:</div>
      )}
      {hints.similar.map(({ question: q, similarity }) => (
        <div className="similar" key={q.id}>
          <button className={`vote sm${q.voted ? " on" : ""}`} type="button" onClick={() => vote(q)}>
            <span>{q.votes}</span><small>me too</small>
          </button>
          <span className="sim-text">{q.text}</span>
          <span className="muted small">{Math.round(similarity * 100)}%</span>
        </div>
      ))}
    </div>
  );
}

export default function Lecture() {
  const { code } = useParams();
  const { isAuthed } = useAuth();
  const toast = useToast();
  const { lecture, error, status, refresh } = useLecturePolling(code);
  useTitle(lecture ? lecture.title : code);
  const [text, setText] = useState("");
  const [topicId, setTopicId] = useState("");
  const [topicFilter, setTopicFilter] = useState(null);
  const [posting, setPosting] = useState(false);

  if (error && error.status === 404) {
    return (
      <main>
        <div className="card empty"><div className="big">🔍</div>No lecture with code <code>{code}</code>.<br /><Link to="/">Back to the lectures</Link></div>
      </main>
    );
  }
  if (!lecture) return <main><div className="status">{status}</div></main>;

  const topics = lecture.topics || [];

  const ask = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    setPosting(true);
    const body = { text };
    if (topicId) body.topic_id = Number(topicId);
    try {
      const created = await api(`/api/lectures/${code}/questions/`, { method: "POST", body });
      setText(""); setTopicId("");
      toast(created.topic_title ? `Posted under “${created.topic_title}”${created.tag_source === "auto" ? " (auto)" : ""}` : "Question posted", "ok");
      await refresh();
    } catch (err) { toast(err.message, "error"); }
    setPosting(false);
  };

  return (
    <main>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1>{lecture.title}</h1>
          <p className="sub">
            code <code>{lecture.code}</code> · {lecture.owner.display_name} · {plural(lecture.question_count, "question")}
            {lecture.topic_count ? ` · ${plural(lecture.topic_count, "topic")}` : ""} ·{" "}
            <span className={`pill ${lecture.is_open ? "open" : "closed"}`}>{lecture.is_open ? "open" : "closed"}</span>
          </p>
        </div>
        <div className="row fixed" style={{ gap: 8 }}>
          {lecture.can_manage && <Link className="btn ghost fixed" to={`/l/${code}/plan/`}>Topics &amp; summary</Link>}
          <Link className="btn ghost fixed" to={`/l/${code}/screen/`}>Projector screen</Link>
        </div>
      </div>

      {isAuthed && lecture.is_open && (
        <div className="card">
          <form onSubmit={ask} noValidate>
            <div className="field" style={{ marginBottom: 0 }}>
              <label htmlFor="text" className="sr-only">Your question</label>
              <textarea id="text" maxLength={500} placeholder="Your question…" required value={text} onChange={(e) => setText(e.target.value)} />
            </div>
            <AskAssistant code={code} text={text} onChange={refresh} />
            <div className="ask-options">
              {topics.length > 0 && (
                <>
                  <label htmlFor="topic" className="small muted" style={{ margin: 0 }}>Topic</label>
                  <select id="topic" value={topicId} onChange={(e) => setTopicId(e.target.value)}>
                    <option value="">auto — let the model decide</option>
                    {topics.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
                  </select>
                </>
              )}
              <span className="spacer" />
              <button className="primary fixed" type="submit" disabled={posting || !text.trim()}>{posting ? "Posting…" : "Ask"}</button>
            </div>
            <div className="small muted" style={{ marginTop: 8 }}>
              Short and specific questions get answered first. Similar questions appear while you type — upvote them instead of asking twice.
            </div>
          </form>
        </div>
      )}

      {!isAuthed && (
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div><strong>Sign in to ask and upvote.</strong><div className="muted small">Creating an account takes ten seconds.</div></div>
            <div className="row fixed" style={{ gap: 8 }}>
              <Link className="btn" to={`/login/?next=${encodeURIComponent(`/l/${code}/`)}`}>Sign in</Link>
              <Link className="btn primary" to={`/register/?next=${encodeURIComponent(`/l/${code}/`)}`}>Create account</Link>
            </div>
          </div>
        </div>
      )}

      {isAuthed && !lecture.is_open && (
        <div className="card"><strong>This lecture is closed for new questions.</strong> <span className="muted">You can still read and upvote.</span></div>
      )}

      <h2>Questions</h2>
      <TopicFilterBar topics={topics} questions={lecture.questions} current={topicFilter} onSelect={setTopicFilter} />
      <QuestionList questions={lecture.questions} mode="audience" topics={topics} topicFilter={topicFilter} onChange={refresh} />
      <div className={`status${error ? " error" : ""}`} style={{ marginTop: 10 }}>{status}</div>
    </main>
  );
}
