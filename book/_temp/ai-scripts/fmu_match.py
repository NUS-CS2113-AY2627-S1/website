#!/usr/bin/env python3
"""find-matching-update matcher: locate a rendered fragment's source span and build M1->M2.

Public entry: resolve(current, corrected, files, submodule_prefixes) -> Match.
`files` is [(rel_path, raw_text)]. Strips MarkBind/Markdown inline markup while
recording a stripped->raw index map, so the char-level minimal diff between the
rendered `current` and `corrected` can be mapped back to an exact source span
that preserves surrounding markup, variables, links and code.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

# version variables that render to a concrete token
VERSION_VALUES = {"version_final": "v1.6", "version_penultimate": "v1.5"}

_TAG = re.compile(r"<[^>]+>")
_VAR = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)[^}]*\}\}")
_ATTR = re.compile(r"\{[.:][^}]*\}")
_PAIR = ("%%", "==", "!!", "++", "~~", "**", "__")


def _emit(out, idx, s, base):
    for k, ch in enumerate(s):
        out.append(ch)
        idx.append(base + k)


def strip_map(raw: str):
    """Return (stripped_chars, idx) with markup removed; idx[i] = raw offset of char i."""
    out: list[str] = []
    idx: list[int] = []
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        # HTML tag / <br>
        m = _TAG.match(raw, i)
        if m:
            out.append(" "); idx.append(i); i = m.end(); continue
        # {{ variable }}
        m = _VAR.match(raw, i)
        if m:
            val = VERSION_VALUES.get(m.group(1))
            if val:
                _emit(out, idx, val, i)
            i = m.end(); continue
        # {.class} / {:attr}
        m = _ATTR.match(raw, i)
        if m:
            i = m.end(); continue
        # image ![alt](url) -> alt
        if raw.startswith("![", i):
            m = re.match(r"!\[([^\]]*)\]\([^)]*\)", raw[i:])
            if m:
                _emit(out, idx, m.group(1), i + 2); i += m.end(); continue
        # link [text](url) -> text
        if c == "[":
            m = re.match(r"\[([^\]]+)\]\([^)]*\)", raw[i:])
            if m:
                _emit(out, idx, m.group(1), i + 1); i += m.end(); continue
        # `code` -> inner, resolving any version variable inside it
        if c == "`":
            m = re.match(r"`([^`]*)`", raw[i:])
            if m:
                inner, base = m.group(1), i + 1
                k = 0
                while k < len(inner):
                    vm = _VAR.match(inner, k)
                    if vm and vm.group(1) in VERSION_VALUES:
                        _emit(out, idx, VERSION_VALUES[vm.group(1)], base + k)
                        k = vm.end()
                    else:
                        out.append(inner[k]); idx.append(base + k); k += 1
                i += m.end(); continue
        # paired inline markers
        hit = next((p for p in _PAIR if raw.startswith(p, i)), None)
        if hit:
            i += len(hit); continue
        # emphasis * or _ at a word boundary
        if c in "*_":
            prev = raw[i - 1] if i > 0 else " "
            nxt = raw[i + 1] if i + 1 < n else " "
            opening = (not prev.isalnum()) and (nxt.isalnum() or nxt in "*_[`")
            closing = (not nxt.isalnum()) and prev.isalnum()
            if opening or closing:
                i += 1; continue
        out.append(c); idx.append(i); i += 1
    return out, idx


def strip_norm_map(raw: str):
    """Markup-strip + whitespace-normalize, keeping a stripped->raw index map."""
    chars, idx = strip_map(raw)
    out: list[str] = []
    oidx: list[int] = []
    prev_ws = False
    for ch, j in zip(chars, idx):
        if ch.isspace():
            if not prev_ws:
                out.append(" "); oidx.append(j)
            prev_ws = True
        else:
            out.append(ch); oidx.append(j); prev_ws = False
    return "".join(out), oidx


def normalize(s: str) -> str:
    for a, b in {"‘": "'", "’": "'", "“": '"', "”": '"', " ": " "}.items():
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def char_diff(a: str, b: str):
    """Char-level tightest change: (old, new, pos) with pos an index into `a`."""
    i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]:
        i += 1
    j = 0
    while j < len(a) - i and j < len(b) - i and a[-1 - j] == b[-1 - j]:
        j += 1
    return a[i:len(a) - j], b[i:len(b) - j], i


@dataclass
class Match:
    status: str
    file: str | None = None
    m1: str | None = None
    m2: str | None = None
    occurrences: int = 0
    files: list[str] = field(default_factory=list)
    note: str = ""


def _word_left(s: str, i: int) -> int:
    while i > 0 and not s[i - 1].isspace():
        i -= 1
    return i


def _word_right(s: str, i: int) -> int:
    while i < len(s) and not s[i].isspace():
        i += 1
    return i


def _build_span(raw: str, ra: int, rb: int, new_core: str, full_count):
    """Snap [ra,rb) to whole-word boundaries, then expand outward until the substring
    count stabilizes (= intended occurrences). M1 never starts/ends on whitespace, so
    it survives the (?<!\\w)...(?!\\w) boundary in issues_batch_replace."""
    lo = min(_word_left(raw, ra), ra)
    hi = max(_word_right(raw, rb), rb)
    prev_count = None
    for _ in range(60):
        m1 = raw[lo:hi]
        cnt = full_count(m1)
        if m1 and not m1[0].isspace() and not m1[-1].isspace() and (cnt == 1 or cnt == prev_count):
            return m1, raw[lo:ra] + new_core + raw[rb:hi], cnt
        prev_count = cnt
        nlo = _word_left(raw, lo - 1) if lo > 0 else lo
        nhi = _word_right(raw, hi + 1) if hi < len(raw) else hi
        if nlo == lo and nhi == hi:
            break
        lo, hi = nlo, nhi
    m1 = raw[lo:hi]
    return m1, raw[lo:ra] + new_core + raw[rb:hi], full_count(m1)


def _within(rel: str, prefixes) -> bool:
    from pathlib import Path
    parts = Path(rel).parts
    return any(pfx and Path(pfx).parts == parts[:len(Path(pfx).parts)] for pfx in prefixes)


def resolve(current: str, corrected: str, files, submodule_prefixes=()) -> Match:
    curn, corn = normalize(current), normalize(corrected)
    old_core, new_core, pos = char_diff(curn, corn)

    # concatenated raw for global count of a candidate span
    all_raw = "\n".join(raw for _, raw in files)
    full_count = lambda s: all_raw.count(s)

    hits = []  # (rel, raw, m1, m2)
    for rel, raw in files:
        sn, idx = strip_norm_map(raw)
        start = 0
        while True:
            p = sn.find(curn, start)
            if p < 0:
                break
            start = p + 1
            # map change span [pos, pos+len(old_core)] (offset by p) to raw
            a_s = p + pos
            b_s = p + pos + len(old_core)
            if b_s > len(idx):
                continue
            ra = idx[a_s] if a_s < len(idx) else (idx[-1] + 1)
            rb = idx[b_s - 1] + 1 if len(old_core) > 0 else ra
            # verify the raw slice equals the plain old_core (no markup straddle)
            if old_core and raw[ra:rb] != old_core:
                hits.append((rel, raw, None, None))  # straddle marker
                continue
            m1, m2, _ = _build_span(raw, ra, rb, new_core, full_count)
            hits.append((rel, raw, m1, m2))

    if not hits:
        # already applied?
        if any(corn in strip_norm_map(raw)[0] for _, raw in files):
            return Match("RESOLVED", note="corrected text already present")
        return Match("UNRESOLVED", note="current not found in source")

    if any(m1 is None for *_, m1, _ in [(h[0], h[1], h[2], h[3]) for h in hits]):
        return Match("UNRESOLVED", note="change straddles markup; needs manual span")

    m1s = {h[2] for h in hits}
    files_hit = sorted({h[0] for h in hits})
    sub = [f for f in files_hit if _within(f, submodule_prefixes)]

    if len(m1s) > 1:
        return Match("AMBIGUOUS", files=files_hit, occurrences=len(hits),
                     note="occurrences need different M1 spans; handle by hand")
    m1 = next(iter(m1s))
    m2 = hits[0][3]
    status = "MULTI" if len(hits) > 1 else "READY"
    if sub:
        status = "SUBMODULE"
    return Match(status, file=files_hit[0], m1=m1, m2=m2,
                 occurrences=len(hits), files=files_hit,
                 note=("in submodule: " + sub[0]) if sub else "")


if __name__ == "__main__":
    import sys
    from pathlib import Path
    root = Path(sys.argv[1])
    files = []
    for p in sorted(root.rglob("*.md")):
        if "_temp" in p.parts:
            continue
        files.append((str(p.relative_to(root)), p.read_text()))
    subs = ()
    gm = root / ".gitmodules"
    if gm.is_file():
        subs = tuple(l.split("=")[1].strip() for l in gm.read_text().splitlines() if l.strip().startswith("path"))
    # quick self-test from the fixture issues
    import re as _re
    noted = (root / "_temp" / "issues-noted.md").read_text()
    blocks = [b for b in _re.split(r"(?=^## Issue )", noted, flags=_re.M) if b.startswith("## Issue")]
    for b in blocks:
        num = _re.match(r"## Issue (\S+):", b).group(1)
        cur = _re.search(r"\(current\):\*\*\s*```text\n(.*?)\n```", b, _re.S).group(1)
        cor = _re.search(r"\(corrected\):\*\*\s*```text\n(.*?)\n```", b, _re.S).group(1)
        m = resolve(cur, cor, files, subs)
        print(f"#{num} {m.status} file={m.file} occ={m.occurrences} note={m.note}")
        print(f"    M1={m.m1!r}")
        print(f"    M2={m.m2!r}")
