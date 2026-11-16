"""Markdown export of a lecture: topics -> questions (votes, author) -> written answers."""

from __future__ import annotations

from django.utils import timezone

from .lookup import questions_for, topics_for
from .models import Lecture


def _author(question) -> str:
    author = question.author
    return author.display_name if author is not None else "Anonymous"


def lecture_markdown(lecture: Lecture) -> str:
    questions = list(questions_for(lecture))
    topics = list(topics_for(lecture))
    by_topic: dict[int | None, list] = {None: []}
    for topic in topics:
        by_topic[topic.id] = []
    for question in questions:
        by_topic.setdefault(question.topic_id, []).append(question)

    lines = [
        f"# {lecture.title}",
        "",
        f"Join code **{lecture.code}** · {'open' if lecture.is_open else 'closed'} · "
        f"{len(questions)} questions, {sum(1 for q in questions if q.is_answered)} answered · "
        f"exported {timezone.localtime().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]
    if topics:
        lines += ["## Topics", ""]
        for topic in topics:
            lines.append(f"- **{topic.title}** — {len(by_topic.get(topic.id, []))} question(s)"
                         + (f"; keywords: {topic.keywords}" if topic.keywords else ""))
        lines.append("")

    def render(title: str, items: list) -> None:
        if not items:
            return
        lines.extend([f"## {title}", ""])
        for question in items:
            mark = "x" if question.is_answered else " "
            lines.append(f"- [{mark}] **{question.text}** — {_author(question)}, {question.votes} vote(s)")
            answer = getattr(question, "answer", None)
            if answer is not None:
                who = answer.author.display_name if answer.author is not None else "lecturer"
                lines.append(f"  - *Answer ({who}):* {answer.text}")
        lines.append("")

    for topic in topics:
        render(topic.title, by_topic.get(topic.id, []))
    render("No topic" if topics else "Questions", by_topic.get(None, []))
    return "\n".join(lines).rstrip() + "\n"
