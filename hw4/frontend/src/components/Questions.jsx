/*
 * The question list and everything inside a question card:
 * vote button, topic chip, written answer, lecturer tools (mark answered, write answer,
 * change topic), author tools (edit, delete).
 *
 * mode: "audience" (lecture page) | "screen" (projector, read-only, big text) | "list" (my questions)
 */

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "./Toasts";
import { fmtTime, topicIndex } from "../utils";

export function TopicChip({ q, topics }) {
  if (!q.topic_id) return null;
  const auto = q.tag_source === "auto";
  const score = (q.tag_score || 0).toFixed(2);
  return (
    <span className={`pill topic t${topicIndex(topics, q.topic_id)}`}
      title={auto ? `Topic suggested automatically (score ${score})` : "Topic chosen by a person"}>
      {q.topic_title || "topic"}
      {auto && <span className="auto" title={`Tagged by the model, confidence ${score}`}>·auto</span>}
    </span>
  );
}

// <select> that re-tags the question (lecturer / admin): PATCH topic_id; "" = no topic
function TopicPicker({ q, topics, onChange }) {
  const toast = useToast();
  const change = async (e) => {
    const value = e.target.value;
    try { await api(`/api/questions/${q.id}/`, { method: "PATCH", body: { topic_id: value ? Number(value) : null } }); await onChange(); }
    catch (err) { toast(err.message, "error"); }
  };
  return (
    <select className="sm topic-select" title="Change the topic" value={q.topic_id || ""} onChange={change}>
      <option value="">— no topic —</option>
      {topics.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
    </select>
  );
}

function AnswerEditor({ q, onChange, onClose }) {
  const toast = useToast();
  const [text, setText] = useState(q.answer ? q.answer.text : "");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try { await api(`/api/questions/${q.id}/answer/`, { method: "PUT", body: { text } }); toast("Answer published", "ok"); onClose(); await onChange(); }
    catch (err) { toast(err.message, "error"); }
    setBusy(false);
  };
  const remove = async () => {
    if (!window.confirm("Remove the written answer? The question will be reopened.")) return;
    try { await api(`/api/questions/${q.id}/answer/`, { method: "DELETE" }); toast("Answer removed"); onClose(); await onChange(); }
    catch (err) { toast(err.message, "error"); }
  };

  return (
    <form className="answer-form" onSubmit={submit}>
      <textarea maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} autoFocus
        placeholder="Your written answer — the audience sees it under the question" />
      <div className="row">
        <button className="sm primary fixed" type="submit" disabled={busy || !text.trim()}>{q.answer ? "Save answer" : "Publish answer"}</button>
        {q.answer && <button className="sm danger ghost fixed" type="button" onClick={remove}>Remove</button>}
        <button className="sm ghost fixed" type="button" onClick={onClose}>Cancel</button>
      </div>
    </form>
  );
}

function QuestionCard({ q, mode, topics, onChange }) {
  const { isAuthed } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(q.text);
  const [answering, setAnswering] = useState(false);
  const screen = mode === "screen";

  const requireAuth = () => {
    if (isAuthed) return true;
    navigate(`/login/?next=${encodeURIComponent(window.location.pathname)}`);
    return false;
  };
  const call = async (fn, okMessage) => {
    try { await fn(); if (okMessage) toast(okMessage, "ok"); await onChange(); }
    catch (err) { toast(err.message, "error"); }
  };

  const vote = async () => {
    if (!requireAuth()) return;
    await call(() => api(`/api/questions/${q.id}/upvote/`, { method: "POST" }));
  };
  const toggleAnswered = () => call(() => api(`/api/questions/${q.id}/answered/`, { method: "POST" }));
  const saveEdit = () => call(async () => { await api(`/api/questions/${q.id}/`, { method: "PATCH", body: { text: draft } }); setEditing(false); }, "Question updated");
  const remove = async () => {
    if (!window.confirm("Delete this question?")) return;
    await call(() => api(`/api/questions/${q.id}/`, { method: "DELETE" }), "Question deleted");
  };

  return (
    <article className={`q${q.is_answered ? " answered" : ""}${screen ? " big" : ""}`}>
      <button className={`vote${q.voted ? " on" : ""}`} type="button" disabled={screen} onClick={screen ? undefined : vote}
        title={screen ? undefined : !isAuthed ? "Sign in to vote" : q.voted ? "Remove my vote" : "I have the same question"}>
        <span>{q.votes}</span>
        <small>{screen ? "votes" : q.voted ? "voted" : "me too"}</small>
      </button>

      <div>
        {editing
          ? <textarea className="edit" maxLength={500} value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus />
          : <p className="text">{q.text}</p>}
        <div className="who">
          <span>{q.author.display_name}</span>
          <span>·</span>
          <span>{fmtTime(q.created_at)}</span>
          {mode === "list" && q.lecture_title && <Link to={`/l/${q.lecture_code}/`}>{q.lecture_title}</Link>}
          <TopicChip q={q} topics={topics} />
          {q.is_answered && <span className="pill answered">answered</span>}
        </div>
        {q.answer && (
          <div className="answer">
            <div className="answer-label">Answer<span className="muted"> · {q.answer.author ? q.answer.author.display_name : "lecturer"}</span></div>
            <div className="answer-text">{q.answer.text}</div>
          </div>
        )}

        {editing ? (
          <div className="tools">
            <button className="sm primary" type="button" onClick={saveEdit}>Save</button>
            <button className="sm ghost" type="button" onClick={() => { setEditing(false); setDraft(q.text); }}>Cancel</button>
          </div>
        ) : (q.can_answer || q.can_edit) && (
          <div className="tools">
            {q.can_answer && <button className="sm" type="button" onClick={toggleAnswered}>{q.is_answered ? "Reopen" : "Mark answered"}</button>}
            {q.can_answer && !screen && <button className="sm ghost" type="button" onClick={() => setAnswering(true)}>{q.answer ? "Edit answer" : "Write answer"}</button>}
            {q.can_answer && !screen && topics.length > 0 && <TopicPicker q={q} topics={topics} onChange={onChange} />}
            {q.can_edit && !screen && <button className="sm ghost" type="button" onClick={() => setEditing(true)}>Edit</button>}
            {q.can_edit && <button className="sm danger ghost" type="button" onClick={remove}>Delete</button>}
          </div>
        )}
        {answering && <AnswerEditor q={q} onChange={onChange} onClose={() => setAnswering(false)} />}
      </div>
    </article>
  );
}

export default function QuestionList({ questions, mode = "audience", topics = [], topicFilter = null, onChange = async () => {} }) {
  let list = questions;
  if (topicFilter !== null && topicFilter !== undefined) {
    list = list.filter((q) => (topicFilter === "none" ? !q.topic_id : q.topic_id === topicFilter));
  }
  if (!list.length) {
    return (
      <div className="empty">
        <div className="big">🙋</div>
        {topicFilter ? "No questions on this topic yet." : mode === "screen" ? "No questions yet — scan the code and ask one." : "No questions yet. Be the first!"}
      </div>
    );
  }
  return (
    <div className="list">
      {list.map((q) => <QuestionCard key={q.id} q={q} mode={mode} topics={topics} onChange={onChange} />)}
    </div>
  );
}

// Chip row "All · topic (n) · No topic (n)"; onSelect(id | "none" | null)
export function TopicFilterBar({ topics, questions, current, onSelect }) {
  if (!topics.length) return null;
  const count = (id) => questions.filter((q) => (id === "none" ? !q.topic_id : q.topic_id === id)).length;
  const Chip = ({ label, value, n, extra = "" }) => (
    <button className={`chip${current === value ? " active" : ""} ${extra}`} type="button" onClick={() => onSelect(current === value ? null : value)}>
      {label}{n !== null && <span className="n">{n}</span>}
    </button>
  );
  return (
    <div className="chips topic-filter">
      <Chip label="All" value={null} n={questions.length} />
      {topics.map((t, i) => <Chip key={t.id} label={t.title} value={t.id} n={count(t.id)} extra={`t${i % 8}`} />)}
      {count("none") > 0 && <Chip label="No topic" value="none" n={count("none")} />}
    </div>
  );
}
