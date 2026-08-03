#!/usr/bin/env python3
r"""Catch Markdown constructs that read fine as raw text but collapse or
misrender at view time — the class of bug that never shows up until someone
actually renders the file.

Deliberately narrow and low-noise (like svg-diagram-qa's geometry linter):
it does NOT flag ordinary soft-wrapped prose, because a paragraph wrapped
across lines and joined with a space at render time is CommonMark working
as designed, not a bug. It flags only the well-understood, usually-
unintentional failure modes:

  SETEXT-MULTILINE       multi-line title text before a `===`/`---` underline
                         collapses into ONE rendered line (setext headings
                         parse their content as a single inline run) — this is
                         the most common real cause of "my header lines merged"
  LITERAL-BACKSLASH-HEADING  a trailing backslash on an ATX heading (`# Title\`)
                         renders as a LITERAL backslash character. ATX headings
                         are single-line by construction — CommonMark has no
                         hard-break syntax that works inside one.
  INEFFECTIVE-HARD-BREAK exactly one trailing space at end of line — looks like
                         someone reaching for a hard break but falling one
                         space short (CommonMark requires 2+, or a backslash)
  FRAGILE-HARD-BREAK     a working two-trailing-space hard break — not an
                         error, just a heads-up that it's invisible in most
                         editors/diffs and easy to strip by accident; a
                         trailing backslash or an explicit <br> survives both
  BOLD-LABEL-MERGE       consecutive lines that each start with `**` (a
                         "**Field:** value" metadata-line idiom), with no
                         blank line or hard break between them — CommonMark
                         treats them as ONE paragraph and joins them with a
                         space, silently collapsing what looks like a stacked
                         list of labeled lines into a single rendered line

Skips fenced code blocks (``` and ~~~) and YAML frontmatter, since line-break
rules inside those don't apply the same way (or don't apply at all).
"""

import argparse
import re
import sys

FENCE_RE = re.compile(r'^(`{3,}|~{3,})')
SETEXT_RE = re.compile(r'^ {0,3}(=+|-{2,})\s*$')
ATX_RE = re.compile(r'^ {0,3}#{1,6}(\s|$)')
THEMATIC_BREAK_RE = re.compile(r'^ {0,3}((-\s*){3,}|(\*\s*){3,}|(_\s*){3,})$')
BOLD_LABEL_RE = re.compile(r'^ {0,3}\*\*')
LIST_MARKER_RE = re.compile(r'^ {0,3}([-*+]\s|\d+[.)]\s)')


def strip_frontmatter(lines):
    """Return (body_lines, offset) — offset = how many leading lines to skip
    for line-number reporting."""
    if lines and lines[0].strip() == '---':
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                return lines[i + 1:], i + 1
    return lines, 0


def lint(path):
    with open(path, encoding='utf-8') as fh:
        raw_lines = fh.read().split('\n')

    lines, offset = strip_frontmatter(raw_lines)
    findings = []
    in_fence = False
    fence_marker = None

    for i, line in enumerate(lines):
        lineno = i + offset + 1

        fence_match = FENCE_RE.match(line.strip())
        if fence_match:
            marker = fence_match.group(1)[0]
            if not in_fence:
                in_fence, fence_marker = True, marker
            elif marker == fence_marker:
                in_fence = False
            continue
        if in_fence:
            continue

        # SETEXT-MULTILINE: this line is a setext underline; walk back over
        # the contiguous non-blank block above it.
        if SETEXT_RE.match(line) and not THEMATIC_BREAK_RE.match(line):
            j = i - 1
            block_start = None
            while j >= 0 and lines[j].strip() != '' and not FENCE_RE.match(lines[j].strip()):
                block_start = j
                j -= 1
            if block_start is not None and block_start < i - 1:
                heading_lines = lines[block_start:i]
                findings.append((
                    lineno,
                    "SETEXT-MULTILINE",
                    f"lines {block_start + offset + 1}-{i + offset}: this "
                    f"{len(heading_lines)}-line title collapses into ONE "
                    f"rendered heading (setext content is a single inline "
                    f"run) — join it onto one raw line, or restructure as "
                    f"an ATX `#`/`##` heading plus a separate subtitle line."
                ))

        # LITERAL-BACKSLASH-HEADING: trailing backslash on an ATX heading.
        if ATX_RE.match(line) and line.rstrip('\n').endswith('\\') and not line.rstrip('\n').endswith('\\\\'):
            findings.append((
                lineno,
                "LITERAL-BACKSLASH-HEADING",
                "trailing backslash on an ATX heading renders as a LITERAL "
                "'\\' character, not a line break — headings are single-line "
                "by construction. Move the extra text to a separate line "
                "below instead."
            ))

        # Trailing-space hard-break checks (skip blank lines and fence lines).
        if line.strip() != '':
            stripped_end = len(line) - len(line.rstrip(' '))
            next_is_content = (i + 1 < len(lines) and lines[i + 1].strip() != ''
                                and not FENCE_RE.match(lines[i + 1].strip()))
            if next_is_content:
                if stripped_end == 1:
                    findings.append((
                        lineno,
                        "INEFFECTIVE-HARD-BREAK",
                        "exactly one trailing space — CommonMark needs 2+ "
                        "trailing spaces (or a backslash) to force a line "
                        "break; one space renders identically to zero."
                    ))
                elif stripped_end >= 2:
                    findings.append((
                        lineno,
                        "FRAGILE-HARD-BREAK",
                        f"{stripped_end}-trailing-space hard break works, but "
                        f"is invisible in most editors/diffs and easy to "
                        f"strip by accident (trim-trailing-whitespace "
                        f"settings, some linters). Prefer a trailing "
                        f"backslash or an explicit <br> for the same effect, "
                        f"visibly."
                    ))
                else:
                    # No trailing-space hard break present — check the
                    # bold-label-stacking idiom specifically (safe, narrow
                    # signal: doesn't fire on ordinary wrapped prose).
                    has_backslash_break = line.rstrip('\n').endswith('\\') and not line.rstrip('\n').endswith('\\\\')
                    if (not has_backslash_break
                            and not LIST_MARKER_RE.match(line)
                            and BOLD_LABEL_RE.match(line)
                            and BOLD_LABEL_RE.match(lines[i + 1])
                            and not LIST_MARKER_RE.match(lines[i + 1])):
                        findings.append((
                            lineno,
                            "BOLD-LABEL-MERGE",
                            f"this line and line {lineno + 1} both start "
                            f"with '**' and have no blank line or hard break "
                            f"between them — CommonMark joins them into ONE "
                            f"paragraph with a space, not separate lines. "
                            f"Add a blank line between them, end this line "
                            f"with a hard break (backslash or 2+ trailing "
                            f"spaces), or turn the block into a real list "
                            f"(`- **Field:** value`)."
                        ))

    return findings


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('paths', nargs='+', help='markdown file(s) to check')
    args = ap.parse_args()

    exit_code = 0
    for path in args.paths:
        findings = lint(path)
        if not findings:
            print(f"✓ {path}: clean (still worth a render-and-look — this is a heuristic)")
            continue
        exit_code = 1
        for lineno, kind, msg in findings:
            severity = "INFO" if kind == "FRAGILE-HARD-BREAK" else "WARN"
            print(f"{severity:4} {path}:{lineno} [{kind}] {msg}")
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
