#!/usr/bin/env python3
"""
Apply the exact-match replacements in issues_found.py, one issue at a time, and
commit each in the git repo that actually owns the changed file.

Each tuple is (M1, M2, file, message). M1 is an exact source substring produced by
issues_md_to_py.py. For every issue the script replaces M1 -> M2 across all scanned
files (so MULTI issues change every occurrence), then commits:
  * changed files in the superproject      -> committed in the superproject
  * changed files inside a git submodule    -> committed inside that submodule
After all issues, each touched submodule's new pointer is committed in the superproject.

Submodule dirs are scanned (so their fixes are applied); only .git/_site/_temp/etc.
are skipped. Files are staged explicitly (never `git add .`), so a gitignored or
empty change is skipped cleanly instead of stalling on an input() prompt.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from issues_found import ISSUES_FOUND


@dataclass
class Config:
    root_dir: Path | None = None
    include_extensions: tuple[str, ...] = (".md", ".njk")
    omit_dirs: tuple[str, ...] = (".git", ".idea", "_site", "_markbind", "node_modules", "_temp")
    issues_found: list = field(default_factory=lambda: ISSUES_FOUND)


@dataclass(frozen=True)
class ReplacementIssue:
    current: str
    replacement: str
    file: str | None = None
    message: str | None = None


CONFIG = Config()


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


def iter_target_files(root_dir: Path, extensions, omit_dirs) -> Iterable[Path]:
    exts = {e if e.startswith(".") else f".{e}" for e in extensions}
    if root_dir.is_file():
        if root_dir.suffix in exts:
            yield root_dir
        return
    for path in sorted(root_dir.rglob("*")):
        if not path.is_file() or path.suffix not in exts:
            continue
        if any(part in omit_dirs for part in path.parts):
            continue
        yield path


def apply_pair(text: str, current: str, replacement: str) -> tuple[str, int]:
    pattern = re.compile(rf"(?<!\w){re.escape(current)}(?!\w)")
    return pattern.subn(replacement, text)


def parse_issue(issue: Sequence[str]) -> ReplacementIssue:
    return ReplacementIssue(
        current=issue[0],
        replacement=issue[1],
        file=issue[2] if len(issue) > 2 else None,
        message=issue[3] if len(issue) > 3 else None,
    )


def apply_issue_to_files(issue: ReplacementIssue, target_files) -> tuple[int, list[Path]]:
    changed: list[Path] = []
    total = 0
    for path in target_files:
        original = path.read_text(encoding="utf-8")
        updated, n = apply_pair(original, issue.current, issue.replacement)
        if n == 0:
            continue
        total += n
        changed.append(path)
        path.write_text(updated, encoding="utf-8")
    return total, changed


def repo_of(path: Path, root: Path, prefixes: tuple[str, ...]) -> tuple[Path, str | None]:
    """Return (repo_dir, submodule_prefix or None) that owns `path`."""
    rel = str(path.resolve().relative_to(root))
    best = None
    for pfx in prefixes:
        if rel == pfx or rel.startswith(pfx + "/"):
            if best is None or len(pfx) > len(best):
                best = pfx
    return (root / best, best) if best else (root, None)


def git(args, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def commit_repo(repo: Path, files: list[Path], message: str) -> bool:
    """Stage the given files and commit them in `repo`. Returns True if a commit was made."""
    for f in files:
        git(["add", str(f)], repo)
    staged = git(["diff", "--cached", "--name-only"], repo).stdout.strip()
    if not staged:
        return False
    result = git(["commit", "-m", message], repo)
    return result.returncode == 0


def commit_message_for(issue: ReplacementIssue) -> str:
    return issue.message or f"Change: {issue.current} -> {issue.replacement}"


def process_issue(issue: ReplacementIssue, target_files, root: Path,
                  prefixes: tuple[str, ...], index: int, total: int, touched: set) -> None:
    print("=" * 80)
    print(f"Issue {index}/{total} in {issue.file}")
    print(f"   {issue.current!r}\n-> {issue.replacement!r}")

    replacements, changed = apply_issue_to_files(issue, target_files)
    print(f"Replacements: {replacements}  Files changed: {len(changed)}")
    if replacements == 0:
        print("WARNING: no changes; skipping commit (already applied or M1 not present).")
        return

    message = commit_message_for(issue)
    groups: dict[Path, list[Path]] = {}
    for path in changed:
        repo, pfx = repo_of(path, root, prefixes)
        groups.setdefault(repo, []).append(path)
        if pfx:
            touched.add(pfx)
    # commit submodule groups first, then the superproject group
    for repo in sorted(groups, key=lambda r: r != root):  # non-root (submodule) first
        made = commit_repo(repo, groups[repo], message)
        where = "superproject" if repo == root else f"submodule {repo.relative_to(root)}"
        print(f"  {'committed' if made else 'nothing to commit'} in {where}")


def main(root_dir: str) -> int:
    root = Path(root_dir).resolve()
    if not root.exists():
        print(f"Root directory does not exist: {root}", file=sys.stderr)
        return 1
    prefixes = submodule_prefixes(root)
    omit = set(CONFIG.omit_dirs)
    target_files = list(iter_target_files(root, CONFIG.include_extensions, omit))
    if not target_files:
        print("No matching files found.")
        return 0

    issues = [parse_issue(i) for i in CONFIG.issues_found]
    print(f"Scanning {len(target_files)} files under {root}")
    print(f"Submodules: {', '.join(prefixes) or 'none'}\n")

    touched: set = set()
    for index, issue in enumerate(issues, start=1):
        process_issue(issue, target_files, root, prefixes, index, len(issues), touched)

    # advance each touched submodule pointer in the superproject
    for pfx in sorted(touched):
        made = commit_repo(root, [root / pfx], f"Advance {pfx} submodule (editorial fixes)")
        print(f"\n{'Committed' if made else 'No'} pointer update for submodule {pfx}")

    print("\nAll issues processed.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 issues_batch_replace.py <project_root>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
