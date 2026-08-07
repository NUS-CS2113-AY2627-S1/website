#!/usr/bin/env python3
"""
Build one consolidated change-list for every fix applied during an
update-as-per-issues-found-md run, sourced from git.

Why git and not the issues md: a run applies fixes three ways -- auto-applied
tuples (issues_batch_replace.py), auto-traced (trace-unresolved), and hand-fixed
residual. Only git sees all three uniformly, and reading commits keeps issue data
out of model context (the skill's token-efficiency rule).

For each fix commit in <base>..HEAD it emits one change entry: the commit subject
is the label, and the removed/added lines are before/after. Commits that only
advance a submodule pointer are skipped; instead each touched submodule's own
commits (over the range the pointer moved) are expanded in place, so a submodule
fix shows as a real text diff rather than an opaque gitlink bump.

The output JSON is meant to be rendered by the generate-visual-diff-of-changes
skill's render_diff.py (this script reinvents no diff HTML):

    python3 issues_applied_diff.py <project_root> <base_ref> [out.json]
    python3 ~/.claude/skills/generate-visual-diff-of-changes/scripts/render_diff.py <out.json> <out.html>

With no explicit out.json the default is timestamped -- _temp/changes-applied-<ts>.json
(and render its .html twin) -- so a later run never overwrites an earlier diff. The
script prints the exact paths; use those.

<base_ref> is the superproject HEAD captured BEFORE the run began.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True
    ).stdout


def submodule_paths(root: Path) -> list[str]:
    out = git(root, "config", "--file", ".gitmodules", "--get-regexp", r"\.path$")
    return [line.split(" ", 1)[1].strip() for line in out.splitlines() if " " in line]


def gitlink_sha(root: Path, ref: str, subpath: str) -> str | None:
    out = git(root, "rev-parse", f"{ref}:{subpath}").strip()
    return out or None


def commits(root: Path, rev_range: str) -> list[tuple[str, str]]:
    out = git(root, "log", "--reverse", "--no-merges", "--format=%H%x1f%s", rev_range)
    result = []
    for line in out.splitlines():
        if "\x1f" in line:
            sha, subject = line.split("\x1f", 1)
            result.append((sha, subject))
    return result


def changed_files(root: Path, sha: str) -> list[str]:
    out = git(root, "show", "--format=", "--name-only", "--no-color", sha)
    return [f for f in out.splitlines() if f.strip()]


def before_after(root: Path, sha: str) -> tuple[str, str]:
    """Removed vs added lines for a commit, de-duplicated so a MULTI fix (same
    line changed in several files) shows once rather than N times."""
    diff = git(root, "show", "--format=", "--unified=0", "--no-color", sha)
    pairs: list[tuple[str, str]] = []
    removed: list[str] = []
    added: list[str] = []
    for line in diff.splitlines():
        if line.startswith(("---", "+++")):
            continue
        if line.startswith("@@"):
            if removed or added:
                pairs.append(("\n".join(removed), "\n".join(added)))
                removed, added = [], []
            continue
        if line.startswith("-"):
            removed.append(line[1:])
        elif line.startswith("+"):
            added.append(line[1:])
    if removed or added:
        pairs.append(("\n".join(removed), "\n".join(added)))
    seen = []
    for pair in pairs:
        if pair not in seen:
            seen.append(pair)
    before = "\n".join(b for b, _ in seen)
    after = "\n".join(a for _, a in seen)
    return before, after


def collect(root: Path, rev_range: str, subprefixes: set[str], label_prefix: str = "") -> list[dict]:
    entries = []
    for sha, subject in commits(root, rev_range):
        files = changed_files(root, sha)
        # Skip pointer-advance commits: every changed path is a submodule dir.
        if files and all(any(f == p or f.startswith(p + "/") for p in subprefixes) for f in files):
            continue
        before, after = before_after(root, sha)
        if not before and not after:
            continue
        note = ", ".join(files)
        if label_prefix:
            note = f"{label_prefix}{note}"
        entries.append(
            {"label": subject, "note": note, "before": before, "after": after}
        )
    return entries


def main(project_root: str, base_ref: str, out_json: str | None = None) -> int:
    root = Path(project_root).resolve()
    subs = submodule_paths(root)
    subprefixes = set(subs)

    changes = collect(root, f"{base_ref}..HEAD", subprefixes)

    # Expand each touched submodule's own commits in place.
    for sub in subs:
        old = gitlink_sha(root, base_ref, sub)
        new = gitlink_sha(root, "HEAD", sub)
        if not old or not new or old == new:
            continue
        subroot = root / sub
        changes += collect(subroot, f"{old}..{new}", set(), label_prefix=f"{sub}/ · ")

    if not changes:
        print("No applied changes found in range -- nothing to render.", file=sys.stderr)
        return 1

    payload = {
        "title": "Editorial fixes applied from issues-noted.md",
        "subtitle": f"{root.name} — {len(changes)} changes across the superproject"
        + (f" and {len(subs)} submodule(s)" if subs else ""),
        "changes": changes,
    }
    # Timestamp the default name (matching changes-for-review-*.html) so a later
    # run never overwrites an earlier run's consolidated diff.
    ts = datetime.now().strftime("%Y-%m-%d-%H-%M")
    out_path = Path(out_json) if out_json else root / "_temp" / f"changes-applied-{ts}.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} ({len(changes)} changes)")
    print("Render with generate-visual-diff-of-changes:")
    print(
        "  python3 ~/.claude/skills/generate-visual-diff-of-changes/scripts/render_diff.py "
        f"{out_path} {out_path.with_suffix('.html')}"
    )
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) not in (2, 3):
        print(
            "Usage: python3 issues_applied_diff.py <project_root> <base_ref> [out.json]",
            file=sys.stderr,
        )
        raise SystemExit(2)
    raise SystemExit(main(*args))
