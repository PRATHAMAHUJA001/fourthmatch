"""Parse a receiving-policy markdown document into a PolicyRead. Pure Python.

The document format is the one produced by seed/policy_template.py:
``# Title``, bold header lines (Document No., Version, Effective Date),
``## N Section`` headings and ``**N.N** clause text`` clauses.
"""

from __future__ import annotations

import re

from app.domain.schemas.dashboard import PolicyClause, PolicyRead

_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$")
_SECTION_RE = re.compile(r"^##\s+\d+\s+(.+?)\s*$")
_CLAUSE_RE = re.compile(r"^\*\*(\d+\.\d+)\*\*\s+(.*)$")
_DOC_NO_RE = re.compile(r"Document No\.\s*([A-Za-z0-9\-/]+)")
_VERSION_RE = re.compile(r"\*\*Version\s+([0-9][0-9A-Za-z.\-]*)\*\*", re.IGNORECASE)
_EFFECTIVE_RE = re.compile(r"Effective Date:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")


def parse_policy(markdown: str, *, policy_id: int = 1) -> PolicyRead:
    """Markdown -> PolicyRead. Clause text is verbatim (continuation lines joined)."""
    title = ""
    section = ""
    clauses: list[PolicyClause] = []
    current: PolicyClause | None = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            clauses.append(current)
            current = None

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not title and (m := _TITLE_RE.match(line)) and not line.startswith("##"):
            title = m.group(1)
            continue
        if m := _SECTION_RE.match(line):
            flush()
            section = m.group(1)
            continue
        if m := _CLAUSE_RE.match(line):
            flush()
            current = PolicyClause(clause_id=m.group(1), section=section, text=m.group(2).strip())
            continue
        if current is not None:
            if not line.strip() or line.startswith("#"):
                flush()
            else:
                current = current.model_copy(update={"text": f"{current.text} {line.strip()}"})
    flush()

    doc_no = _DOC_NO_RE.search(markdown)
    version = _VERSION_RE.search(markdown)
    effective = _EFFECTIVE_RE.search(markdown)
    return PolicyRead(
        id=policy_id,
        version=version.group(1) if version else "unknown",
        title=title,
        document_no=doc_no.group(1) if doc_no else "",
        effective_date=effective.group(1) if effective else "",
        clauses=clauses,
    )
