"""Isolated ExifTool XMP transformations; publication and policy live elsewhere."""

from __future__ import annotations

import os
import selectors
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XML = "http://www.w3.org/XML/1998/namespace"
DC = "http://purl.org/dc/elements/1.1/"
DK = "http://www.digikam.org/ns/1.0/"
R = "{" + RDF + "}"
LANG = "{" + XML + "}lang"
FIELDS = {
    "tags": (f"{{{DK}}}TagsList", "XMP-digiKam:TagsList"),
    "title": (f"{{{DC}}}title", "XMP-dc:Title-x-default"),
    "caption": (f"{{{DC}}}description", "XMP-dc:Description-x-default"),
    "author": (
        f"{{{DK}}}CaptionsAuthorNames",
        "XMP-digiKam:CaptionsAuthorNames-x-default",
    ),
}
EMPTY = b"""<?xpacket begin=""?><x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about=""/></rdf:RDF></x:xmpmeta><?xpacket end="w"?>"""


class XmpBackendError(Exception):
    """A sanitized failure at the metadata or tool boundary."""


def _value(element):
    attrs = tuple(sorted(element.attrib.items()))
    children = list(element)
    text = element.text or ""
    if children and text.strip():
        raise XmpBackendError("unsupported XMP structure")
    if any((child.tail or "").strip() for child in children):
        raise XmpBackendError("unsupported XMP structure")
    if children:
        if attrs:
            raise XmpBackendError("unsupported XMP structure")
        if len(children) != 1 or children[0].tag not in (
            R + "Seq",
            R + "Bag",
            R + "Alt",
        ):
            raise XmpBackendError("unsupported XMP structure")
        container = children[0]
        if container.attrib or (container.text or "").strip():
            raise XmpBackendError("unsupported XMP structure")
        values = []
        for item in container:
            if (
                item.tag != R + "li"
                or list(item)
                or set(item.attrib) - {LANG}
                or (item.tail or "").strip()
            ):
                raise XmpBackendError("unsupported XMP structure")
            values.append((item.get(LANG), item.text or ""))
        if container.tag == R + "Alt":
            langs = [v[0] for v in values]
            if None in langs or len(set(langs)) != len(langs):
                raise XmpBackendError("unsupported XMP structure")
            values.sort()
        elif container.tag == R + "Bag":
            values.sort(key=repr)
        return (container.tag, tuple(values))
    if set(element.attrib) - {LANG}:
        raise XmpBackendError("unsupported XMP structure")
    return ("literal", attrs, text)


def _parse(data):
    if (
        not isinstance(data, bytes)
        or b"\x00" in data
        or b"<!DOCTYPE" in data.upper()
        or b"<!ENTITY" in data.upper()
    ):
        raise XmpBackendError("malformed XMP")
    try:
        root = ET.fromstring(data)
    except (ET.ParseError, ValueError):
        raise XmpBackendError("malformed XMP") from None
    if root.tag == R + "RDF":
        rdf = root
    elif root.tag == "{adobe:ns:meta/}xmpmeta":
        if set(root.attrib) - {"{adobe:ns:meta/}xmptk"} or (root.text or "").strip():
            raise XmpBackendError("unsupported XMP structure")
        if len(root) != 1 or root[0].tag != R + "RDF" or (root[0].tail or "").strip():
            raise XmpBackendError("unsupported XMP structure")
        rdf = root[0]
    else:
        raise XmpBackendError("unsupported XMP structure")
    if rdf.attrib or (rdf.text or "").strip():
        raise XmpBackendError("unsupported XMP structure")
    properties = {}
    for desc in rdf:
        if desc.tag != R + "Description" or desc.get(R + "about", ""):
            raise XmpBackendError("unsupported XMP structure")
        if (desc.text or "").strip() or (desc.tail or "").strip():
            raise XmpBackendError("unsupported XMP structure")
        for name, value in desc.attrib.items():
            if name == R + "about":
                continue
            if not name.startswith("{") or name.startswith(R) or name in properties:
                raise XmpBackendError("unsupported XMP structure")
            properties[name] = ("literal", (), value)
        for prop in desc:
            if (prop.tail or "").strip():
                raise XmpBackendError("unsupported XMP structure")
            if (
                prop.tag in properties
                or not prop.tag.startswith("{")
                or prop.tag.startswith(R)
            ):
                raise XmpBackendError("unsupported XMP structure")
            properties[prop.tag] = _value(prop)
    return properties


class _RecoveryTreeBuilder(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        raise XmpBackendError("malformed XMP")


def _validate_structure(data):
    """Validate the XMP container without interpreting foreign RDF properties."""
    if not isinstance(data, bytes):
        raise XmpBackendError("malformed XMP")
    try:
        root = ET.fromstring(data, parser=ET.XMLParser(target=_RecoveryTreeBuilder()))
    except (ET.ParseError, ValueError):
        raise XmpBackendError("malformed XMP") from None
    if root.tag == R + "RDF":
        return
    if (
        root.tag == "{adobe:ns:meta/}xmpmeta"
        and sum(child.tag == R + "RDF" for child in root) == 1
    ):
        return
    raise XmpBackendError("malformed XMP")


def _typed(props):
    result = {}
    for key, (name, _) in FIELDS.items():
        value = props.get(name)
        if value is None:
            result[key] = [] if key == "tags" else None
        elif key == "tags":
            if value[0] != R + "Seq" or any(lang is not None for lang, _ in value[1]):
                raise XmpBackendError("unsupported XMP field")
            result[key] = [v for _, v in value[1]]
        else:
            if value[0] != R + "Alt":
                raise XmpBackendError("unsupported XMP field")
            result[key] = dict(value[1]).get("x-default")
    return result


class ExifToolBackend:
    def __init__(
        self, directory, *, executable="exiftool", timeout=30, output_limit=1048576
    ):
        self.directory = Path(directory)
        self.executable = executable
        self.timeout = timeout
        self.output_limit = output_limit

    def read(self, snapshot):
        props = _parse(EMPTY if snapshot is None else snapshot)
        return {"properties": props, **_typed(props)}

    def validate(self, candidate):
        _validate_structure(candidate)
        return True

    def _run(self, args):
        executable = shutil.which(self.executable)
        if not executable:
            raise XmpBackendError("ExifTool executable unavailable")
        try:
            proc = subprocess.Popen(
                [executable, "-config", "", *args],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )
        except (OSError, ValueError):
            raise XmpBackendError("ExifTool executable unavailable") from None
        selector = selectors.DefaultSelector()
        try:
            for stream in (proc.stdout, proc.stderr):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            end = time.monotonic() + self.timeout
            total = 0
            while selector.get_map():
                remaining = end - time.monotonic()
                if remaining <= 0:
                    raise XmpBackendError("ExifTool timeout")
                for key, _ in selector.select(remaining):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        total += len(chunk)
                        if total > self.output_limit:
                            raise XmpBackendError("ExifTool output limit exceeded")
            remaining = end - time.monotonic()
            if remaining <= 0:
                raise XmpBackendError("ExifTool timeout")
            try:
                status = proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                raise XmpBackendError("ExifTool timeout") from None
            if status:
                raise XmpBackendError("ExifTool processing failed")
        finally:
            selector.close()
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()
            proc.stderr.close()

    def transform(self, snapshot, updates):
        before = self.read(snapshot)
        if not isinstance(updates, dict) or set(updates) - set(FIELDS):
            raise XmpBackendError("invalid XMP updates")
        args = []
        for key, value in updates.items():
            if key == "tags":
                if not isinstance(value, list) or any(
                    not isinstance(v, str) or not v for v in value
                ):
                    raise XmpBackendError("invalid XMP updates")
                if value:
                    args.extend("-XMP-digiKam:TagsList=" + v for v in value)
                else:
                    args.append("-XMP-digiKam:TagsList=")
            else:
                if not isinstance(value, str) or not value:
                    raise XmpBackendError("invalid XMP updates")
                args.append("-" + FIELDS[key][1] + "=" + value)
        try:
            for arg in args:
                if "\x00" in arg:
                    raise ValueError
                os.fsencode(arg)
        except (UnicodeError, ValueError):
            raise XmpBackendError("invalid XMP updates") from None
        if not updates:
            return EMPTY if snapshot is None else snapshot
        path = None
        try:
            fd, name = tempfile.mkstemp(
                prefix=".image-clarus-", suffix=".xmp", dir=self.directory
            )
            path = Path(name).absolute()
            with os.fdopen(fd, "wb") as stream:
                stream.write(EMPTY if snapshot is None else snapshot)
            self._run([*args, "-overwrite_original", "--", str(path)])
            candidate = path.read_bytes()
            after = self.read(candidate)
            for key, expected in updates.items():
                if after[key] != expected:
                    raise XmpBackendError("XMP update verification failed")
            old, new = before["properties"].copy(), after["properties"].copy()
            for key in updates:
                name = FIELDS[key][0]
                if key == "tags":
                    old.pop(name, None)
                    new.pop(name, None)
                else:
                    for props in (old, new):
                        value = props.get(name)
                        if value is not None:
                            rest = tuple(v for v in value[1] if v[0] != "x-default")
                            if rest:
                                props[name] = (value[0], rest)
                            else:
                                props.pop(name)
            if old != new:
                raise XmpBackendError("XMP preservation violation")
            return candidate
        except OSError:
            raise XmpBackendError("XMP working file failure") from None
        finally:
            if path is not None:
                for owned in (path, Path(str(path) + "_original")):
                    try:
                        owned.unlink(missing_ok=True)
                    except OSError:
                        pass
