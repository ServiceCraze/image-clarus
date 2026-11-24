"""Metadata-only, deterministic selection for processing and category rebuild."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath


class DiscoveryError(ValueError):
    """Fatal, sanitized selection failure; no partial result is returned."""


@dataclass(frozen=True)
class Candidate:
    path: Path
    identity: str
    selection_index: int
    selection: str
    kind: str


@dataclass(frozen=True)
class DiscoveryResult:
    candidates: tuple[Candidate, ...]
    batch: bool
    kinds: tuple[str, ...]


def split_pattern(
    token: str, *, windows: bool = False
) -> tuple[PurePath, tuple[str, ...]]:
    """Split at the first wildcard using the requested host path grammar.

    The Windows mode is also usable for host-independent parsing tests.
    """
    cls = PureWindowsPath if windows else PurePosixPath
    path = cls(token)
    parts = path.parts
    first = next(
        (i for i, part in enumerate(parts) if any(c in part for c in "*?[")), len(parts)
    )
    prefix = cls(*parts[:first]) if first else cls(".")
    rest = parts[first:]
    if any(part == ".." for part in rest):
        raise DiscoveryError("invalid pattern: parent component after wildcard")
    return prefix, rest


def _compile_component(component: str, ignore_case: bool) -> re.Pattern[str]:
    out = ""
    i = 0
    while i < len(component):
        char = component[i]
        if char == "*":
            if i + 1 < len(component) and component[i + 1] == "*":
                raise DiscoveryError("invalid pattern: embedded recursive wildcard")
            out += ".*"
        elif char == "?":
            out += "."
        elif char == "[":
            start = i + 1
            neg = start < len(component) and component[start] == "!"
            start += int(neg)
            end = start + int(start < len(component) and component[start] == "]")
            end = component.find("]", end)
            if end < 0 or end == start:
                raise DiscoveryError("invalid pattern: malformed bracket class")
            chars = component[start:end]
            j = 0
            body = ""
            while j < len(chars):
                if j + 2 < len(chars) and chars[j + 1] == "-":
                    if ord(chars[j]) > ord(chars[j + 2]):
                        raise DiscoveryError("invalid pattern: descending range")
                    body += re.escape(chars[j]) + "-" + re.escape(chars[j + 2])
                    j += 3
                else:
                    body += re.escape(chars[j])
                    j += 1
            out += "[" + ("^" if neg else "") + body + "]"
            i = end
        else:
            out += re.escape(char)
        i += 1
    return re.compile(out, re.DOTALL | (re.IGNORECASE if ignore_case else 0))


def _sort_key(name: str) -> bytes:
    return (
        name.encode("utf-16-be", "surrogatepass")
        if os.name == "nt"
        else os.fsencode(name)
    )


def image_eligibility(extensions: Sequence[str]) -> Callable[[Path], bool]:
    allowed = {value.lower() for value in extensions}
    return lambda path: path.suffix[1:].lower() in allowed


def sidecar_eligibility(path: Path) -> bool:
    return path.name.endswith(".desc.json")


def discover_images(
    selections: Sequence[str],
    *,
    max_depth: int | None = None,
    extensions: Sequence[str] = ("jpg", "jpeg", "png", "webp", "tif", "tiff"),
    ignore_case: bool = False,
) -> DiscoveryResult:
    return discover(
        selections,
        max_depth=max_depth,
        eligibility=image_eligibility(extensions),
        explicit_requires_eligibility=False,
        ignore_case=ignore_case,
    )


def discover_sidecars(
    selections: Sequence[str],
    *,
    max_depth: int | None = None,
    ignore_case: bool = False,
) -> DiscoveryResult:
    return discover(
        selections,
        max_depth=max_depth,
        eligibility=sidecar_eligibility,
        explicit_requires_eligibility=True,
        ignore_case=ignore_case,
    )


def discover(
    selections: Sequence[str],
    *,
    max_depth: int | None,
    eligibility: Callable[[Path], bool],
    explicit_requires_eligibility: bool,
    ignore_case: bool = False,
) -> DiscoveryResult:
    """Select all inputs atomically; candidates retain first-selection provenance."""
    if not selections:
        raise DiscoveryError("invalid selection: provide nonempty paths")
    for index, selection in enumerate(selections):
        if not isinstance(selection, str) or not selection or "\0" in selection:
            raise DiscoveryError(
                f"selection index {index}: provide a nonempty path without NUL"
            )
    if max_depth is not None and (type(max_depth) is not int or max_depth < 0):
        raise DiscoveryError("invalid selection depth")
    candidates: list[Candidate] = []
    seen: set[str] = set()
    kinds: list[str] = []
    traversed: set[tuple[str, tuple[str, ...] | None]] = set()

    def add(path: Path, index: int, kind: str) -> None:
        resolved = path.resolve(strict=True)
        identity = str(resolved)
        if identity not in seen:
            seen.add(identity)
            candidates.append(
                Candidate(resolved, identity, index, selections[index], kind)
            )

    def walk(
        root: Path, index: int, kind: str, pattern: tuple[str, ...] | None
    ) -> None:
        key = (str(root), pattern)
        if key in traversed:
            return
        traversed.add(key)
        compiled = (
            tuple(
                None if p == "**" else _compile_component(p, ignore_case)
                for p in pattern
            )
            if pattern is not None
            else ()
        )

        def closure(states: set[int]) -> set[int]:
            states = set(states)
            for n in range(len(compiled)):
                if n in states and compiled[n] is None:
                    states.add(n + 1)
            return states

        def advance(states: set[int], name: str) -> set[int]:
            result: set[int] = set()
            for n in closure(states):
                if n < len(compiled):
                    matcher = compiled[n]
                    if matcher is None:
                        result.add(n)
                    elif matcher.fullmatch(name):
                        result.add(n + 1)
            return closure(result)

        def visit(directory: Path, depth: int, states: set[int]) -> None:
            with os.scandir(directory) as entries:
                items = sorted(entries, key=lambda e: _sort_key(e.name))
            files = []
            dirs = []
            for entry in items:
                info = entry.stat(follow_symlinks=False)
                attrs = getattr(info, "st_file_attributes", 0)
                if stat.S_ISLNK(info.st_mode) or attrs & getattr(
                    stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
                ):
                    continue
                next_states = (
                    advance(states, entry.name) if pattern is not None else set()
                )
                if stat.S_ISREG(info.st_mode):
                    if (
                        pattern is None or len(compiled) in next_states
                    ) and eligibility(Path(entry.name)):
                        files.append(Path(entry.path))
                elif stat.S_ISDIR(info.st_mode) and (
                    pattern is None or any(n < len(compiled) for n in next_states)
                ):
                    dirs.append((Path(entry.path), next_states))
            for path in files:
                add(path, index, kind)
            if max_depth is None or depth < max_depth:
                for path, next_states in dirs:
                    visit(path, depth + 1, next_states)

        visit(root, 0, closure({0}))

    index = 0
    try:
        for index, raw in enumerate(selections):
            path = Path(raw).expanduser()
            try:
                path.lstat()
                exists = True
            except FileNotFoundError:
                exists = False
            if exists:
                resolved = path.resolve(strict=True)
                info = resolved.stat()
                if stat.S_ISREG(info.st_mode):
                    if not os.access(resolved, os.R_OK):
                        raise DiscoveryError("unreadable selection file")
                    if explicit_requires_eligibility and not eligibility(resolved):
                        raise DiscoveryError("selection file is not eligible")
                    kinds.append("file")
                    add(resolved, index, "file")
                elif stat.S_ISDIR(info.st_mode):
                    kinds.append("directory")
                    walk(resolved, index, "directory", None)
                else:
                    raise DiscoveryError("selection is not a regular file or directory")
            elif any(c in str(path) for c in "*?["):
                prefix, pattern = split_pattern(str(path), windows=os.name == "nt")
                # Validate every component even when the tree has no matches.
                for part in pattern:
                    if part != "**":
                        _compile_component(part, ignore_case)
                anchor = Path(prefix).resolve(strict=True)
                if not anchor.is_dir():
                    raise DiscoveryError("pattern anchor is not a directory")
                kinds.append("pattern")
                walk(anchor, index, "pattern", pattern)
            else:
                raise DiscoveryError("selection does not exist")
    except DiscoveryError as exc:
        raise DiscoveryError(f"selection index {index}: {exc}") from None
    except (OSError, RuntimeError, ValueError):
        raise DiscoveryError(
            f"selection index {index}: path could not be accessed or enumerated; "
            "check that it exists and is readable"
        ) from None
    return DiscoveryResult(
        tuple(candidates), len(selections) != 1 or kinds[0] != "file", tuple(kinds)
    )
