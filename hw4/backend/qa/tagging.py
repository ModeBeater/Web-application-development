"""
Automatic topic tagging and "similar question" search.

The model is deliberately small and explainable — it runs offline inside the container
and gives the same answer on every machine:

1. **TF-IDF over character n-grams** (scikit-learn `TfidfVectorizer`, `analyzer="char_wb"`,
   3–5 characters). Character n-grams work across Russian / Kazakh / English, survive typos
   and different word endings ("виджет", "виджеты", "виджетов" share most n-grams) and need
   no language-specific tokenizer or stemmer.
2. Every topic becomes one document: its title, keywords and description (the section of
   the uploaded lecture text). A new question is vectorized with the same vocabulary and
   compared with every topic by **cosine similarity**.
3. **Keyword hits** (the lecturer's own words) add a bonus, so an explicit keyword match
   wins even when the n-gram overlap is small.
4. The best topic is used only when its score reaches `TAGGING_THRESHOLD` (settings, default
   0.18); otherwise the question stays untagged — a wrong tag is worse than no tag.

The same vectorizer, built over the questions of a lecture, powers "someone already asked
this": the top matches above `SIMILAR_THRESHOLD` are shown while a student types.

`TAGGING_BACKEND=keywords` (settings) switches the TF-IDF part off and keeps only the keyword
rule — handy for a quick comparison during a defense.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from django.conf import settings

from .models import Lecture, Question, Topic

WORD_RE = re.compile(r"[\w\-+#.]+", re.UNICODE)
KEYWORD_BONUS = 0.25        # added per matched keyword (capped below)
KEYWORD_BONUS_CAP = 0.6


def _settings(name: str, default):
    return getattr(settings, name, default)


def tokens(text: str) -> list[str]:
    return [token.lower().strip(".") for token in WORD_RE.findall(text or "") if len(token.strip(".")) > 1]


def keyword_list(keywords: str) -> list[str]:
    return [word.strip().lower() for word in (keywords or "").split(",") if word.strip()]


def keyword_hits(text: str, keywords: Sequence[str]) -> int:
    """How many of the topic's keywords occur in the text (whole words or phrases)."""
    lowered = f" {' '.join(tokens(text))} "
    return sum(1 for word in keywords if f" {word} " in lowered or (len(word) > 3 and word in lowered))


def topic_document(topic: Topic) -> str:
    """The text a topic is represented by. The title counts twice: it is the strongest signal."""
    return " ".join(part for part in (topic.title, topic.title, topic.keywords, topic.description[:4000]) if part)


def _cosine_rows(documents: Sequence[str], queries: Sequence[str]):
    """Cosine similarity matrix (queries × documents) over char n-gram TF-IDF. Empty when sklearn is off."""
    if _settings("TAGGING_BACKEND", "tfidf") != "tfidf" or not documents or not queries:
        return None
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True, sublinear_tf=True, min_df=1)
    matrix = vectorizer.fit_transform(list(documents))
    return cosine_similarity(vectorizer.transform(list(queries)), matrix)


@dataclass
class Suggestion:
    topic: Topic | None
    score: float
    scores: list[tuple[int, float]]  # (topic id, score) for every topic, best first

    @property
    def tagged(self) -> bool:
        return self.topic is not None


def suggest_topics(lecture: Lecture, texts: Sequence[str], topics: Iterable[Topic] | None = None) -> list[Suggestion]:
    """One Suggestion per text. Topics default to the lecture's plan (query done once)."""
    topics = list(topics if topics is not None else lecture.topics.all())
    if not topics or not texts:
        return [Suggestion(None, 0.0, []) for _ in texts]

    documents = [topic_document(topic) for topic in topics]
    keywords = [keyword_list(topic.keywords) for topic in topics]
    similarity = _cosine_rows(documents, texts)
    threshold = float(_settings("TAGGING_THRESHOLD", 0.18))

    suggestions = []
    for row, text in enumerate(texts):
        scored = []
        for column, topic in enumerate(topics):
            cosine = float(similarity[row, column]) if similarity is not None else 0.0
            bonus = min(KEYWORD_BONUS_CAP, KEYWORD_BONUS * keyword_hits(text, keywords[column]))
            scored.append((topic, round(min(1.0, cosine + bonus), 4)))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        best_topic, best_score = scored[0]
        chosen = best_topic if best_score >= threshold else None
        suggestions.append(Suggestion(chosen, best_score, [(topic.id, score) for topic, score in scored]))
    return suggestions


def suggest_topic(lecture: Lecture, text: str) -> Suggestion:
    return suggest_topics(lecture, [text])[0]


def tag_question(question: Question, *, force: bool = False, save: bool = True) -> Suggestion:
    """
    Tag one question automatically. Manual tags are kept unless `force`.
    Returns the suggestion; with `save` the question row is updated.
    """
    if question.tag_source == Question.TagSource.MANUAL and question.topic_id is not None and not force:
        return Suggestion(question.topic, question.tag_score or 0.0, [])
    suggestion = suggest_topic(question.lecture, question.text)
    question.topic = suggestion.topic
    question.tag_score = suggestion.score if suggestion.tagged else None
    question.tag_source = Question.TagSource.AUTO if suggestion.tagged else Question.TagSource.NONE
    if save:
        question.save(update_fields=["topic", "tag_score", "tag_source"])
    return suggestion


def retag_lecture(lecture: Lecture, *, include_manual: bool = False) -> dict:
    """Re-run the model over the lecture's questions (after the plan changed). Returns counts."""
    queryset = lecture.questions.all()
    if not include_manual:  # a manual tag whose topic was deleted (topic is NULL) is re-tagged as well
        queryset = queryset.exclude(tag_source=Question.TagSource.MANUAL, topic__isnull=False)
    questions = list(queryset)
    topics = list(lecture.topics.all())
    suggestions = suggest_topics(lecture, [q.text for q in questions], topics)
    tagged = 0
    for question, suggestion in zip(questions, suggestions):
        question.topic = suggestion.topic
        question.tag_score = suggestion.score if suggestion.tagged else None
        question.tag_source = Question.TagSource.AUTO if suggestion.tagged else Question.TagSource.NONE
        tagged += suggestion.tagged
    Question.objects.bulk_update(questions, ["topic", "tag_score", "tag_source"])
    return {"processed": len(questions), "tagged": tagged, "untagged": len(questions) - tagged, "topics": len(topics)}


def similar_questions(lecture: Lecture, text: str, limit: int = 3) -> list[tuple[Question, float]]:
    """Existing questions of the lecture that look like `text`, best first, above SIMILAR_THRESHOLD."""
    text = (text or "").strip()
    if len(text) < 4:
        return []
    questions = list(lecture.questions.select_related("author").all())
    if not questions:
        return []
    similarity = _cosine_rows([q.text for q in questions], [text])
    threshold = float(_settings("SIMILAR_THRESHOLD", 0.35))
    if similarity is None:  # keyword-only backend: fall back to shared words
        query_words = set(tokens(text))
        scored = []
        for question in questions:
            words = set(tokens(question.text))
            overlap = len(query_words & words) / max(1, len(query_words | words))
            scored.append((question, round(overlap, 4)))
    else:
        scored = [(question, round(float(similarity[0, index]), 4)) for index, question in enumerate(questions)]
    scored = [pair for pair in scored if pair[1] >= threshold]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]
