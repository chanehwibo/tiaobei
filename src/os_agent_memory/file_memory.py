"""KylinBot-compatible Markdown memory for a trusted runtime-owned workspace.

Single writer, explicit consent, bounded files, no filesystem tools from content.
SQLite research storage remains separate; this module does not silently export it.
"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .security import SensitiveFilter

MEMORY_TYPES = ("user", "feedback", "project", "reference")
KEY = re.compile(r"^(user|feedback|project|reference)-[a-z0-9][a-z0-9-]{0,63}\.md$")
INDEX_LINE = re.compile(r"^- \[([^\[\]]+)\]\(([a-z0-9-]+\.md)\) — (.+)$")


@dataclass(frozen=True)
class WriteContext:
    explicit_request: bool
    origin_session_id: str
    current_time: str

    def validate(self):
        if self.explicit_request is not True:
            raise PermissionError("explicit user request is required")
        time = datetime.fromisoformat(self.current_time.replace("Z", "+00:00"))
        if time.tzinfo is None:
            raise ValueError("runtime time must include a timezone")
        if any(c in self.origin_session_id for c in "\r\n") or len(self.origin_session_id) > 128:
            raise ValueError("invalid runtime session id")


class FileMemory:
    def __init__(self, workspace):
        self.workspace = Path(workspace).absolute()
        self.root = self.workspace / "memory"
        self._check_path(self.root)
        self.filter = SensitiveFilter()

    @staticmethod
    def _check_path(path):
        for part in (path, *path.parents):
            if part.is_symlink() or (part.exists() and getattr(part.lstat(), "st_file_attributes", 0) & 0x400):
                raise ValueError("memory path contains a link/reparse point")

    def _path(self, key):
        if not KEY.fullmatch(key):
            raise ValueError("invalid memory key")
        path = self.root / key
        self._check_path(path)
        return path

    @staticmethod
    def _bounded_read(path, maximum):
        with path.open("rb") as stream:
            value = stream.read(maximum + 1)
        if len(value) > maximum:
            raise ValueError("memory byte budget exceeded")
        return value.decode("utf-8")

    def headers(self):
        """Only read MEMORY.md, never prefetch entry bodies."""
        index = self.root / "MEMORY.md"
        self._check_path(index)
        if not index.exists():
            return []
        text = self._bounded_read(index, 25 * 1024)
        if len(text.splitlines()) > 200:
            raise ValueError("index line budget exceeded")
        rows, seen = [], set()
        for line in text.splitlines():
            if not line.startswith("- "):
                continue
            match = INDEX_LINE.fullmatch(line)
            if not match or len(line) > 150:
                raise ValueError("invalid memory index")
            name, key, description = match.groups()
            self._path(key)
            if key in seen:
                raise ValueError("duplicate memory key")
            seen.add(key)
            rows.append({"key": key, "type": key.split("-", 1)[0], "name": name, "description": description})
        return rows

    @staticmethod
    def _parse(text):
        if not text.startswith("---\n") or "\n---\n" not in text[4:]:
            raise ValueError("invalid frontmatter")
        front, body = text[4:].split("\n---\n", 1)
        header = {}
        for line in front.splitlines():
            key, separator, value = line.partition(": ")
            if not separator or key in header:
                raise ValueError("invalid or duplicate frontmatter field")
            header[key] = json.loads(value)
        required = ("name", "description", "type", "origin_session_id", "created_at", "updated_at")
        if any(type(header.get(key)) is not str for key in required) or header["type"] not in MEMORY_TYPES:
            raise ValueError("frontmatter contract violated")
        for field in ("created_at", "updated_at"):
            if datetime.fromisoformat(header[field].replace("Z", "+00:00")).tzinfo is None:
                raise ValueError("frontmatter time lacks timezone")
        return header, body.rstrip("\n")

    def read(self, key):
        indexed = next((row for row in self.headers() if row["key"] == key), None)
        if indexed is None:
            raise KeyError("entry not indexed")
        text = self._bounded_read(self._path(key), 4096)
        if len(text.splitlines()) > 200:
            raise ValueError("entry line budget exceeded")
        header, body = self._parse(text)
        if any(header[field] != indexed[field] for field in ("name", "description", "type")):
            raise ValueError("index/frontmatter mismatch")
        return {**header, "key": key, "body": body, "revision": hashlib.sha256(text.encode()).hexdigest()}

    @staticmethod
    def _index(rows):
        lines = ["# Memory index", ""]
        for kind in MEMORY_TYPES:
            lines.extend(["## " + kind, ""])
            for row in sorted(rows, key=lambda r: r["key"]):
                if row["type"] == kind:
                    line = f"- [{row['name']}]({row['key']}) — {row['description']}"
                    if len(line) > 150:
                        raise ValueError("index summary exceeds 150 characters")
                    lines.append(line)
            lines.append("")
        text = "\n".join(lines)
        if len(lines) > 200 or len(text.encode()) > 25 * 1024:
            raise ValueError("index budget exceeded")
        return text

    @contextmanager
    def _writer(self):
        self._check_path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        lock = self.root / ".writer.lock"
        with lock.open("x", encoding="utf-8") as stream:
            stream.write(str(os.getpid()))
        try:
            yield
        finally:
            lock.unlink()

    @staticmethod
    def _atomic_write(path, text):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    def write(self, *, kind, slug, name, description, body, context, expected_revision=None):
        context.validate()
        key = f"{kind}-{slug}.md"
        path = self._path(key)
        if kind not in MEMORY_TYPES or not all(type(s) is str and s.strip() for s in (name, description, body)):
            raise ValueError("invalid memory fields")
        if any(c in name + description for c in "\r\n[]"):
            raise ValueError("index fields must be plain single-line text")
        if kind in {"feedback", "project"} and not all(section in body for section in ("规则或事实：", "原因：", "如何执行：")):
            raise ValueError("feedback/project requires fact, reason and execution sections")
        if kind in {"feedback", "project"} and not (body.index("规则或事实：") < body.index("原因：") < body.index("如何执行：")):
            raise ValueError("memory sections are out of order")
        if kind == "project" and re.search("今天|明天|昨天|前天|后天|下周|上周|本周|下个月|月底", body):
            raise ValueError("project dates must be resolved to explicit absolute dates before writing")
        if kind in {"user", "reference"} and "\n\n" in body:
            raise ValueError("user/reference requires one declarative paragraph")
        combined = " ".join((name, description, body))
        unsafe = re.search(r"(?:无需|不用|绕过).{0,6}(?:确认|安全)|直接.{0,6}(?:发邮件|删除全部|清空磁盘)", combined)
        if self.filter.detect(combined) or self.filter.assess_memory_risk(combined) or unsafe:
            raise ValueError("sensitive or unsafe memory must not be persisted")
        with self._writer():
            rows = self.headers()
            previous = self.read(key) if any(row["key"] == key for row in rows) else None
            if previous and expected_revision != previous["revision"]:
                raise ValueError("update requires current revision")
            if not previous and path.exists():
                raise ValueError("unindexed entry requires explicit recovery review")
            if not previous and any(row["name"].casefold() == name.casefold() for row in rows):
                raise ValueError("same topic exists; update it instead")
            header = {"name": name, "description": description, "type": kind,
                      "origin_session_id": context.origin_session_id or "unknown",
                      "created_at": previous["created_at"] if previous else context.current_time,
                      "updated_at": context.current_time}
            text = "---\n" + "\n".join(k + ": " + json.dumps(v, ensure_ascii=False) for k, v in header.items()) + "\n---\n" + body.strip() + "\n"
            if len(text.encode()) > 4096 or len(text.splitlines()) > 200:
                raise ValueError("entry budget exceeded")
            new_index = self._index([row for row in rows if row["key"] != key] + [{**header, "key": key}])
            old_text = path.read_text(encoding="utf-8") if previous else None
            self._atomic_write(path, text)
            try:
                self._atomic_write(self.root / "MEMORY.md", new_index)
            except Exception:
                if old_text is None:
                    path.unlink()
                else:
                    self._atomic_write(path, old_text)
                raise
            return self.read(key)

    def delete(self, key, *, context, expected_revision):
        context.validate()
        with self._writer():
            current = self.read(key)
            if current["revision"] != expected_revision:
                raise ValueError("stale deletion confirmation")
            rows = self.headers()
            index = self.root / "MEMORY.md"
            old_index = index.read_text(encoding="utf-8")
            self._atomic_write(index, self._index([row for row in rows if row["key"] != key]))
            try:
                self._path(key).unlink()
            except Exception:
                self._atomic_write(index, old_index)
                raise
            return {"deleted_key": key, "deleted": True}
