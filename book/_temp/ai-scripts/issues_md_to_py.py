#!/usr/bin/env python3
"""
Generate issues_found.py from a human-authored issues-noted.md, deterministically,
using the find-matching-update method to locate each fix's exact source span.

Reads   <project_root>/_temp/issues-noted.md
Writes  <project_root>/_temp/ai-scripts/issues_found.py   (exact-appliable tuples)
        <project_root>/_temp/ai-scripts/issues_report.md  (classification of every issue)

Why this exists
---------------
issues-noted.md can hold hundreds of issues copied from *rendered* page text, so a
large share do not match the authored source verbatim (stripped markup, resolved
MarkBind variables like v1.6 -> {{ version_final }}, links, code spans, panel titles).
This script does the whole transform on disk -- never loading the md into an AI
context -- by delegating each issue to the find-matching-update matcher (fmu_match):
it markup-strips the source while tracking a stripped->raw index map, computes the
char-level minimal diff between `current` and `corrected`, and maps that change back
to an exact source span (M1) plus its replacement (M2) that preserves the surrounding
markup, variables, links and code.

Per issue (blocks are split on '## Issue', never on '---'):
  READY      exactly one source hit                -> tuple (safe, unique replace)
  MULTI      the same span in several places        -> tuple (batch replace changes all)
  SUBMODULE  the hit is inside a git submodule       -> tuple (batch replace routes the
                                                         commit into the submodule)
  RESOLVED   corrected text already present          -> excluded (fix already applied)
  AMBIGUOUS  occurrences need different spans         -> excluded, reported for the human
  UNRESOLVED current not locatable / change straddles -> excluded, reported with anchor
  UNPARSED   block missing a fragment fence          -> excluded, reported

READY, MULTI and SUBMODULE become tuples in issues_found.py. Every tuple's M1 is an
exact source substring, so issues_batch_replace.py stays a plain exact-match replace.

Usage:
    python3 issues_md_to_py.py <project_root>
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import fmu_match

INCLUDE_EXTENSIONS = (".md", ".njk")
OMIT_DIRS = {".git", ".idea", "_site", "_markbind", "node_modules", "_temp"}

NOTED_REL = Path("_temp") / "issues-noted.md"
OUT_PY_REL = Path("_temp") / "ai-scripts" / "issues_found.py"
OUT_REPORT_REL = Path("_temp") / "ai-scripts" / "issues_report.md"

MAX_EXPLANATION_CHARS = 220
APPLICABLE = {"READY", "MULTI", "SUBMODULE"}


@dataclass
class Issue:
    number: str
    title: str
    type: str
    source_hint_full: str | None
    current: str
    corrected: str
    explanation: str
    status: str = "PENDING"
    file: str | None = None
    m1: str | None = None
    m2: str | None = None
    occurrences: int = 0
    anchor: str | None = None
    note: str = ""


ISSUE_SPLIT_RE = re.compile(r"(?=^## Issue\b)", re.MULTILINE)
TITLE_RE = re.compile(r"^## Issue\s+([^:\n]*):\s*(.*)$", re.MULTILINE)
TYPE_RE = re.compile(r"^-\s*\*\*Type\*\*:\s*(.+)$", re.MULTILINE)
SOURCE_RE = re.compile(r"^-\s*\*\*Source\*\*:\s*(.+)$", re.MULTILINE)
EXPLANATION_RE = re.compile(r"\*\*Issue\*\*:\s*(.+?)\n\s*\*\*Fragment \(corrected\)", re.DOTALL)


def fenced_text_after(block: str, label: str) -> str | None:
    pattern = re.compile(re.escape(label) + r".*?```text\n(.*?)\n```", re.DOTALL)
    match = pattern.search(block)
    return match.group(1) if match else None


def parse_issues(noted_text: str) -> list[Issue]:
    issues: list[Issue] = []
    for block in ISSUE_SPLIT_RE.split(noted_text):
        if not block.lstrip().startswith("## Issue"):
            continue
        title_match = TITLE_RE.search(block)
        type_match = TYPE_RE.search(block)
        source_match = SOURCE_RE.search(block)
        explanation_match = EXPLANATION_RE.search(block)
        current = fenced_text_after(block, "**Fragment (current):**")
        corrected = fenced_text_after(block, "**Fragment (corrected):**")
        number = title_match.group(1).strip() if title_match else "?"
        title = title_match.group(2).strip() if title_match else "(unparsed)"
        type_ = type_match.group(1).strip() if type_match else ""
        if current is None or corrected is None:
            issues.append(Issue(number, title, type_, None, current or "", corrected or "",
                                "", status="UNPARSED", note="Missing current or corrected fragment fence."))
            continue
        issues.append(Issue(
            number=number, title=title, type=type_,
            source_hint_full=source_match.group(1).strip() if source_match else None,
            current=current, corrected=corrected,
            explanation=explanation_match.group(1).strip() if explanation_match else "",
        ))
    return issues


def load_source_files(root: Path):
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in INCLUDE_EXTENSIONS:
            continue
        if any(part in OMIT_DIRS for part in path.relative_to(root).parts):
            continue
        try:
            files.append((str(path.relative_to(root)), path.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            continue
    return files


def submodule_prefixes(root: Path) -> tuple[str, ...]:
    gitmodules = root / ".gitmodules"
    if not gitmodules.is_file():
        return ()
    prefixes = []
    for line in gitmodules.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("path"):
            _, _, value = stripped.partition("=")
            if value.strip():
                prefixes.append(value.strip().rstrip("/"))
    return tuple(prefixes)


def is_within(rel_path: str, prefixes: tuple[str, ...]) -> bool:
    """True if rel_path is inside one of the submodule prefixes (kept for
    issues_trace_unresolved, which imports this helper)."""
    parts = Path(rel_path).parts
    return any(pfx and Path(pfx).parts == parts[: len(Path(pfx).parts)] for pfx in prefixes)


def classify(issue: Issue, files, prefixes) -> None:
    if issue.status == "UNPARSED":
        return
    match = fmu_match.resolve(issue.current, issue.corrected, files, prefixes)
    issue.status = match.status
    issue.file = match.file
    issue.m1 = match.m1
    issue.m2 = match.m2
    issue.occurrences = match.occurrences
    issue.note = match.note
    if issue.status in {"UNRESOLVED", "AMBIGUOUS"}:
        issue.anchor = issue.source_hint_full or (match.files[0] if match.files else None)


def commit_message_for(issue: Issue) -> str:
    subject = " ".join(issue.title.split()).strip()
    return subject or f"Fix {issue.type or 'wording'} issue"


def brief_explanation_for(issue: Issue) -> str:
    tag = " ".join(issue.type.split()) or "editorial"
    reason = " ".join(issue.explanation.split())
    if len(reason) > MAX_EXPLANATION_CHARS:
        reason = reason[: MAX_EXPLANATION_CHARS - 1].rstrip() + "…"
    extra = ""
    if issue.status == "MULTI":
        extra = f" ({issue.occurrences} occurrences)"
    elif issue.status == "SUBMODULE":
        extra = f" (submodule: {issue.file})"
    return f"[{tag}] {reason}{extra}".strip()


def write_issues_found(path: Path, issues) -> int:
    applicable = [i for i in issues if i.status in APPLICABLE]
    lines = [
        "# Generated by issues_md_to_py.py from _temp/issues-noted.md -- do not hand-edit.",
        "# Each M1 is an exact source substring; issues_batch_replace.py applies it verbatim.",
        "# MULTI issues intentionally match several places (all changed). SUBMODULE issues are",
        "# committed inside their submodule by issues_batch_replace.py.",
        "# See issues_report.md for AMBIGUOUS / UNRESOLVED / RESOLVED issues to handle by hand.",
        "ISSUES_FOUND = [",
    ]
    for issue in applicable:
        lines.append(f"    ({issue.m1!r},")
        lines.append(f"     {issue.m2!r},")
        lines.append(f"     {(issue.file or '')!r},")
        lines.append(f"     {commit_message_for(issue)!r}),  # {brief_explanation_for(issue)}")
    lines.append("]")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return len(applicable)


def write_report(path: Path, issues) -> dict:
    counts: dict = {}
    for issue in issues:
        counts[issue.status] = counts.get(issue.status, 0) + 1
    lines = [
        "# Issues report", "",
        f"Total issues parsed: {len(issues)}", "",
        "| Status | Count | Meaning |",
        "| --- | --- | --- |",
        f"| READY | {counts.get('READY', 0)} | One exact source hit; in issues_found.py. |",
        f"| MULTI | {counts.get('MULTI', 0)} | Same span in several places; all replaced; in issues_found.py. |",
        f"| SUBMODULE | {counts.get('SUBMODULE', 0)} | Hit inside a git submodule; committed there; in issues_found.py. |",
        f"| RESOLVED | {counts.get('RESOLVED', 0)} | Corrected text already present; excluded. |",
        f"| AMBIGUOUS | {counts.get('AMBIGUOUS', 0)} | Occurrences need different spans; excluded -- handle by hand. |",
        f"| UNRESOLVED | {counts.get('UNRESOLVED', 0)} | Not locatable / change straddles markup; excluded -- locate by hand. |",
        f"| UNPARSED | {counts.get('UNPARSED', 0)} | Block missing a fragment fence; excluded. |",
        "",
        "Issues in issues_found.py apply automatically. The lists below are the only ones",
        "needing attention -- read these, not the whole issues-noted.md.",
        "",
    ]

    def preview(text, limit=160):
        collapsed = " ".join(text.split())
        return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"

    def section(title, status):
        flagged = [i for i in issues if i.status == status]
        if not flagged:
            return
        lines.append(f"## {title} ({len(flagged)})")
        lines.append("")
        for issue in flagged:
            where = issue.anchor or issue.file or "grep the fragment to locate"
            lines.append(f"- **Issue {issue.number}** — {issue.title}")
            lines.append(f"  - at: `{where}`")
            lines.append(f"  - current: `{preview(issue.current)}`")
            lines.append(f"  - corrected: `{preview(issue.corrected)}`")
            if issue.note:
                lines.append(f"  - note: {issue.note}")
        lines.append("")

    section("AMBIGUOUS — occurrences need different spans", "AMBIGUOUS")
    section("UNRESOLVED — not locatable in source", "UNRESOLVED")
    section("UNPARSED — malformed block", "UNPARSED")
    path.write_text("\n".join(lines), encoding="utf-8")
    return counts


def main(project_root: str) -> int:
    root = Path(project_root).resolve()
    noted_path = root / NOTED_REL
    if not noted_path.is_file():
        print(f"issues-noted.md not found: {noted_path}", file=sys.stderr)
        return 1
    out_py = root / OUT_PY_REL
    out_report = root / OUT_REPORT_REL
    out_py.parent.mkdir(parents=True, exist_ok=True)

    issues = parse_issues(noted_path.read_text(encoding="utf-8"))
    if not issues:
        print("No issues parsed from issues-noted.md.", file=sys.stderr)
        return 1

    files = load_source_files(root)
    prefixes = submodule_prefixes(root)
    for issue in issues:
        classify(issue, files, prefixes)

    applicable_count = write_issues_found(out_py, issues)
    counts = write_report(out_report, issues)

    print(f"Parsed {len(issues)} issues from {noted_path.relative_to(root)}")
    print(f"Scanned {len(files)} source files; submodules: {', '.join(prefixes) or 'none'}")
    for status in ("READY", "MULTI", "SUBMODULE", "RESOLVED", "AMBIGUOUS", "UNRESOLVED", "UNPARSED"):
        if counts.get(status):
            print(f"  {status:<11} {counts[status]}")
    print(f"Wrote {applicable_count} applicable tuples -> {out_py.relative_to(root)}")
    print(f"Wrote classification report -> {out_report.relative_to(root)}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 issues_md_to_py.py <project_root>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
