"""Resolve the inline/reference Markdown links used by public review documents."""
from __future__ import annotations

import posixpath
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit


LINK = re.compile(
    r'!?\[[^\]\n]*\]\(\s*(?P<inline><[^>\n]+>|(?:\\.|[^\s()\\]|\([^()\n]*\))+?)'
    r'(?=\s*(?:\"[^\"\n]*\"|\'[^\'\n]*\')?\s*\))'
    r'|^ {0,3}\[[^\]\n]+\]:\s*(?P<reference><[^>\n]+>|\S+)',
    re.MULTILINE,
)
INLINE_CODE = re.compile(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.DOTALL)


def _visible_markdown(text: str) -> str:
    """Mask code without moving link offsets in the original document."""
    lines, fence = [], None
    for line in text.splitlines(keepends=True):
        marker = re.match(r" {0,3}(`{3,}|~{3,})(.*)", line)
        if fence:
            lines.append("".join("\n" if char == "\n" else " " for char in line))
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        elif marker:
            fence = marker[1]
            lines.append("".join("\n" if char == "\n" else " " for char in line))
        else:
            lines.append(line)
    return INLINE_CODE.sub(lambda match: " " * len(match[0]), "".join(lines))


def relocate_links(
    text: str, *, source: str, target: str, destinations: dict[str, str],
) -> tuple[str, list[dict[str, str]]]:
    """Rewrite local destinations only; reject links outside the planned allowlist."""
    replacements, rows = [], []
    for match in LINK.finditer(_visible_markdown(text)):
        group = "inline" if match["inline"] is not None else "reference"
        raw = match[group]
        destination = raw[1:-1] if raw.startswith("<") else raw
        destination = re.sub(r"\\([\\ ()])", r"\1", destination)
        parts = urlsplit(destination)
        if parts.scheme in {"http", "https", "mailto", "data"} or parts.netloc:
            continue
        if not parts.path and not parts.scheme:
            continue
        path = unquote(parts.path).replace("\\", "/")
        if parts.scheme or path.startswith("/") or ":" in path:
            raise ValueError(f"{source}: nonportable local link: {destination}")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), path))
        if resolved.startswith("../") or resolved not in destinations:
            raise ValueError(f"{source}: link target is absent from the allowlist: {destination}")
        mapped = destinations[resolved]
        relative = posixpath.relpath(mapped, posixpath.dirname(target) or ".")
        rewritten = urlunsplit(("", "", quote(relative, safe="/-._~"), parts.query, parts.fragment))
        replacements.append((*match.span(group), f"<{rewritten}>" if raw.startswith("<") else rewritten))
        rows.append({
            "source": source, "target": target, "original": destination,
            "resolved_source": resolved, "resolved_target": mapped, "rewritten": rewritten,
        })
    for start, end, value in reversed(replacements):
        text = text[:start] + value + text[end:]
    return text, rows


def planned_public_markdown(
    project_root: Path, entries: list[dict[str, str]],
) -> tuple[dict[str, str], list[dict[str, str]]]:
    # Prefer the readable public copy, falling back to the path-preserving source mirror.
    destinations = {row["source"]: row["target"] for row in entries if row["kind"] == "source"}
    for row in reversed(entries):
        if row["kind"] == "public":
            destinations[row["source"]] = row["target"]
    rewritten, links = {}, []
    for row in entries:
        if row["kind"] != "public" or Path(row["source"]).suffix.lower() != ".md":
            continue
        text, found = relocate_links(
            (project_root / row["source"]).read_text(encoding="utf-8"),
            source=row["source"], target=row["target"], destinations=destinations,
        )
        rewritten[row["target"]] = text
        links.extend(found)
    return rewritten, links
