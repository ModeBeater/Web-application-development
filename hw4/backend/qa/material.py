"""
Turn an uploaded lecture (plain text, Markdown or PDF) into a topic plan.

    text  --split_sections-->  [Section(title, body)]  --extract_keywords-->  topics

Headings are recognised in this order:
  * Markdown headings (`# Title`, `## Title`)
  * numbered headings (`1. Title`, `2.3 Title`, `Глава 2. Title`)
  * short ALL-CAPS lines (`STATE MANAGEMENT`)
  * for PDFs: the first short line of every page (slide titles); consecutive pages with the
    same title are merged
  * fallback when nothing matches: the text is split into paragraph groups of roughly equal
    size and each group is titled with its first words

Keywords for every section are the words with the highest TF-IDF weight across the sections
(scikit-learn, word level, a small Russian/English stop list), so the words that distinguish
a section from the rest of the lecture become its keywords.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

MAX_TOPICS = 30
MAX_TITLE = 120
MAX_DESCRIPTION = 4000
KEYWORDS_PER_TOPIC = 6
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

MARKDOWN_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
NUMBERED_HEADING = re.compile(r"^\s*(?:(?:глава|часть|chapter|part|lecture|лекция|тема|topic)\s+)?\d+(?:[.)]\d+)*[.)]?\s+([^\s].{2,100})$", re.IGNORECASE)
CAPS_HEADING = re.compile(r"^[A-ZА-ЯЁІҢҒҮҰҚӨҺ0-9][A-ZА-ЯЁІҢҒҮҰҚӨҺ0-9 \-–—:,/&()+#.]{3,80}$")
WORD = re.compile(r"[^\W\d_][\w\-]{2,}", re.UNICODE)

STOP_WORDS = set(
    """
    the a an and or of to in on for with is are be as at by from that this these those it its
    we you they he she i not no yes can will would should could do does did have has had was were
    what which who how when where why than then there here into over under about also just only
    use used using today first second third next last
    и в во на с со к ко о об от для по из за не но а как что это этот эта эти то те так же или
    если при до без через над под между при про бы ли же уже ещё еще все всё при них нас вас его её
    ее их там тут где когда почему зачем который которые которая какой какие чем чему тоже также
    есть был была были быть может можно нужно надо
    первый второй третий четвёртый четвертый пятый абзац далее итак
    """.split()
)


@dataclass
class Section:
    title: str
    body: str = ""
    keywords: list[str] = field(default_factory=list)
    level: int = 2  # 1 = document-level heading (`# Title`, `Лекция 4. ...`), 2 = section heading

    def document(self) -> str:
        return f"{self.title}\n{self.body}"


# ---------------------------------------------------------------------------
# Reading the upload
# ---------------------------------------------------------------------------


def read_upload(name: str, data: bytes) -> tuple[str, list[str] | None]:
    """Return (text, pages). `pages` is set for PDFs so slide titles can be used as headings."""
    lowered = (name or "").lower()
    if lowered.endswith(".pdf") or data[:5] == b"%PDF-":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        return "\n\n".join(pages), pages
    for encoding in ("utf-8-sig", "utf-8", "cp1251", "latin-1"):
        try:
            return data.decode(encoding), None
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), None


# ---------------------------------------------------------------------------
# Splitting into sections
# ---------------------------------------------------------------------------


DOCUMENT_PREFIX = re.compile(r"^\s*(?:лекция|lecture|глава|chapter|тема|topic)\s+\d+", re.IGNORECASE)


def _heading(line: str) -> tuple[str, int] | None:
    """(title, level) when the line is a heading, else None."""
    stripped = line.strip()
    if not stripped or len(stripped) > MAX_TITLE + 40:
        return None
    match = MARKDOWN_HEADING.match(stripped)
    if match:
        return match.group(1).strip(), (1 if stripped.lstrip().startswith("# ") else 2)
    match = NUMBERED_HEADING.match(stripped)
    if match and len(stripped) <= 70 and not stripped.endswith((";", ",", "!", "?")):
        return match.group(1).strip().rstrip(".:"), (1 if DOCUMENT_PREFIX.match(stripped) else 2)
    if CAPS_HEADING.match(stripped) and sum(ch.isalpha() for ch in stripped) >= 4:
        return (stripped.title() if stripped.isupper() else stripped), 2
    return None


def _clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip(" -–—:*_#")
    return title[:MAX_TITLE]


def split_sections(text: str, pages: list[str] | None = None) -> list[Section]:
    """Sections in reading order; see the module docstring for the heuristics."""
    sections = _split_by_headings(text)
    if len(sections) >= 2:
        return _merge_small(_drop_document_title(sections))
    if pages:
        by_pages = _split_by_pages(pages)
        if len(by_pages) >= 2:
            return _merge_small(_drop_document_title(by_pages))
    return _split_by_paragraphs(text)


def _drop_document_title(sections: list[Section]) -> list[Section]:
    """
    The first heading is the lecture's own title, not a topic, when it is a document-level heading
    (`# Title`, `Лекция 4. ...`) with only an intro under it, or when it has (almost) no text at all.
    """
    if len(sections) < 3:
        return sections
    first = sections[0]
    others_are_sections = all(section.level >= 2 for section in sections[1:])
    if len(first.body) < 40 or (first.level == 1 and others_are_sections and len(first.body) < 400):
        return sections[1:]
    return sections


def _split_by_headings(text: str) -> list[Section]:
    sections: list[Section] = []
    current: Section | None = None
    preamble: list[str] = []
    for line in text.splitlines():
        heading = _heading(line)
        if heading:
            title, level = heading
            if current is not None:
                sections.append(current)
            current = Section(title=_clean_title(title), level=level)
        elif current is not None:
            current.body += line + "\n"
        else:
            preamble.append(line)
    if current is not None:
        sections.append(current)
    for section in sections:
        section.body = section.body.strip()
    return [s for s in sections if s.title]


def _split_by_pages(pages: list[str]) -> list[Section]:
    sections: list[Section] = []
    for page in pages:
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        if not lines:
            continue
        title, body = lines[0], "\n".join(lines[1:])
        if len(title) > 80 or len(lines) == 1 and len(title) > 60:
            title, body = "", page
        title = _clean_title(title) or _first_words(body)
        if sections and sections[-1].title.lower() == title.lower():
            sections[-1].body += "\n" + body
        else:
            sections.append(Section(title=title, body=body))
    return sections


def _split_by_paragraphs(text: str, target_sections: int = 6) -> list[Section]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return []
    size = max(1, round(len(paragraphs) / target_sections))
    sections = []
    for index in range(0, len(paragraphs), size):
        chunk = paragraphs[index : index + size]
        sections.append(Section(title=_first_words(chunk[0]), body="\n\n".join(chunk)))
    return sections


def _first_words(text: str, count: int = 6) -> str:
    words = text.split()
    title = " ".join(words[:count])
    return _clean_title(title + ("…" if len(words) > count else "")) or "Untitled"


def _merge_small(sections: list[Section], min_body: int = 40) -> list[Section]:
    """Headings with (almost) no text under them are sub-headings: fold them into the previous section."""
    merged: list[Section] = []
    for section in sections:
        if merged and len(section.body) < min_body and len(merged[-1].body) < MAX_DESCRIPTION:
            merged[-1].body += f"\n{section.title}\n{section.body}".rstrip()
        else:
            merged.append(section)
    return merged[:MAX_TOPICS]


# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------


def extract_keywords(sections: list[Section], per_section: int = KEYWORDS_PER_TOPIC) -> None:
    """Fill `section.keywords` with the terms that best distinguish each section (TF-IDF, in place)."""
    documents = [section.document() for section in sections]
    if not documents:
        return
    if len(documents) == 1:
        sections[0].keywords = _top_terms_by_frequency(documents[0], per_section)
        return
    from sklearn.feature_extraction.text import TfidfVectorizer

    vectorizer = TfidfVectorizer(
        analyzer="word", token_pattern=WORD.pattern, lowercase=True, stop_words=list(STOP_WORDS),
        sublinear_tf=True, max_df=0.8,
    )
    try:
        matrix = vectorizer.fit_transform(documents)
    except ValueError:  # only stop words
        return
    terms = vectorizer.get_feature_names_out()
    for row, section in enumerate(sections):
        weights = matrix.getrow(row).toarray().ravel()
        order = weights.argsort()[::-1]
        section.keywords = [terms[i] for i in order[: per_section * 2] if weights[i] > 0][:per_section]


def _top_terms_by_frequency(text: str, count: int) -> list[str]:
    frequency: dict[str, int] = {}
    for word in WORD.findall(text.lower()):
        if word not in STOP_WORDS:
            frequency[word] = frequency.get(word, 0) + 1
    return [word for word, _ in sorted(frequency.items(), key=lambda pair: (-pair[1], pair[0]))[:count]]


def plan_from_text(text: str, pages: list[str] | None = None) -> list[Section]:
    """The whole pipeline: text -> sections with keywords."""
    sections = split_sections(text, pages)
    extract_keywords(sections)
    return sections
