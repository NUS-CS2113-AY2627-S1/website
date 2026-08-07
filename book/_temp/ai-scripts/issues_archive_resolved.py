#!/usr/bin/env python3
"""
Move resolved issues out of issues-noted.md into issues-resolved.md.

An issue counts as resolved when its corrected fragment is present in the source
tree and its current fragment is not -- i.e., the fix is in place. This is
state-based and idempotent: run it after issues_batch_replace.py (or after manual
edits) and it archives whatever is now done, leaving the rest as the live backlog.

It errs toward keeping. A block is moved only when the corrected text is found and
the original text is gone and the corrected text is specific enough (>= 4 words) to
trust, so a still-pending issue is never silently dropped. Review issues-resolved.md
before discarding it.

Presence is checked against a markup-stripped, variable-resolved rendering of every
source file (via fmu_match), so a fix hidden behind bold/code/links/version variables
is still recognized. Submodule files are included, so submodule fixes are archived too.

Reads/writes (issues-noted.md is typically gitignored -- there is no undo):
  <project_root>/_temp/issues-noted.md      (resolved blocks removed)
  <project_root>/_temp/issues-resolved.md   (resolved blocks appended, created if absent)

Usage:
    python3 issues_archive_resolved.py <project_root> [--dry-run]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import fmu_match
from issues_md_to_py import ISSUE_SPLIT_RE, fenced_text_after, load_source_files

NOTED_REL = Path("_temp") / "issues-noted.md"
RESOLVED_REL = Path("_temp") / "issues-resolved.md"

MIN_CORRECTED_WORDS = 4

RESOLVED_HEADER = (
    "# Issues resolved\n\n"
    "Issues moved here automatically once their corrected text was found in the "
    "source and their original text was gone. Review before discarding.\n\n---\n\n"
)

ISSUE_NUMBER_RE = re.compile(r"^## Issue\s+([^:\n]*):", re.MULTILINE)


def split_blocks(noted_text: str) -> tuple[str, list[str]]:
    preamble_parts: list[str] = []
    blocks: list[str] = []
    for part in ISSUE_SPLIT_RE.split(noted_text):
        if part.lstrip().startswith("## Issue"):
            blocks.append(part)
        else:
            preamble_parts.append(part)
    return "".join(preamble_parts), blocks


def block_number(block: str) -> str:
    match = ISSUE_NUMBER_RE.search(block)
    return match.group(1).strip() if match else "?"


def present(fragment: str, rendered: list[str]) -> bool:
    needle = fmu_match.normalize(fragment)
    return any(needle in text for text in rendered)


def is_resolved(block: str, rendered: list[str]) -> bool:
    current = fenced_text_after(block, "**Fragment (current):**")
    corrected = fenced_text_after(block, "**Fragment (corrected):**")
    if not current or not corrected:
        return False  # cannot judge -> keep
    if len(corrected.split()) < MIN_CORRECTED_WORDS:
        return False  # too short to archive confidently -> keep
    return present(corrected, rendered) and not present(current, rendered)


def main(project_root: str, dry_run: bool = False) -> int:
    root = Path(project_root).resolve()
    noted_path = root / NOTED_REL
    resolved_path = root / RESOLVED_REL
    if not noted_path.is_file():
        print(f"issues-noted.md not found: {noted_path}", file=sys.stderr)
        return 1

    preamble, blocks = split_blocks(noted_path.read_text(encoding="utf-8"))
    # markup-stripped, variable-resolved rendering of every source file (submodules included)
    rendered = [fmu_match.strip_norm_map(text)[0] for _, text in load_source_files(root)]

    resolved_blocks: list[str] = []
    kept_blocks: list[str] = []
    for block in blocks:
        (resolved_blocks if is_resolved(block, rendered) else kept_blocks).append(block)

    print(f"Blocks: {len(blocks)} total")
    print(f"Resolved (fix confirmed in source): {len(resolved_blocks)}")
    print(f"Kept as backlog: {len(kept_blocks)}")
    if resolved_blocks:
        moving = ", ".join(block_number(block) for block in resolved_blocks)
        print(f"Issue numbers {'that would move' if dry_run else 'moved'}: {moving}")

    if dry_run:
        print("(dry run -- no files changed)")
        return 0
    if not resolved_blocks:
        print("Nothing to move.")
        return 0

    noted_path.write_text(preamble + "".join(kept_blocks), encoding="utf-8")
    existing = resolved_path.read_text(encoding="utf-8") if resolved_path.is_file() else RESOLVED_HEADER
    resolved_path.write_text(existing + "".join(resolved_blocks), encoding="utf-8")
    print(f"Updated {noted_path.relative_to(root)} and {resolved_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    positional = [arg for arg in args if not arg.startswith("--")]
    if len(positional) != 1:
        print("Usage: python3 issues_archive_resolved.py <project_root> [--dry-run]", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(positional[0], dry_run=dry_run))
