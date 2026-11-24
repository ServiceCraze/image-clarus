"""Synthetic metadata-only selection contract tests."""

import builtins
import os
import stat
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

from image_clarus.config import resolve_config
from image_clarus.discovery import (
    DiscoveryError,
    _compile_component,
    discover_images,
    discover_sidecars,
    split_pattern,
)


def names(result):
    return [candidate.path.name for candidate in result.candidates]


def make(root, name):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fixture")
    return path


@pytest.mark.parametrize(
    "discover,suffix", [(discover_images, ".jpg"), (discover_sidecars, ".desc.json")]
)
@pytest.mark.parametrize("wildcard", ["*", "?"])
def test_windows_invalid_name_wildcard_is_pattern(
    tmp_path, monkeypatch, discover, suffix, wildcard
):
    expected = make(tmp_path, "a" + suffix)
    selection = tmp_path / (wildcard + suffix)
    original = Path.lstat

    def lstat(path, *args, **kwargs):
        if path == selection:
            error = OSError("simulated invalid name")
            error.winerror = 123
            raise error
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat)
    result = discover([str(selection)])
    assert names(result) == [expected.name]
    assert result.kinds == ("pattern",) and result.batch


@pytest.mark.parametrize(
    "discover,suffix", [(discover_images, ".jpg"), (discover_sidecars, ".desc.json")]
)
@pytest.mark.parametrize(
    "token,error_kind",
    [("plain", "invalid"), ("[a]", "invalid"), ("*", "denied"), ("*", "other")],
)
def test_lstat_other_errors_are_not_patterns(
    tmp_path, monkeypatch, discover, suffix, token, error_kind
):
    selection = tmp_path / (token + suffix)
    make(tmp_path, "a" + suffix)
    original = Path.lstat

    def lstat(path, *args, **kwargs):
        if path == selection:
            error = (
                PermissionError("private detail")
                if error_kind == "denied"
                else OSError("private detail")
            )
            error.winerror = 123 if error_kind == "invalid" else 5
            raise error
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(
        DiscoveryError, match="could not be accessed or enumerated"
    ) as error:
        discover([str(selection)])
    assert "private detail" not in str(error.value)


@pytest.mark.parametrize(
    "discover,suffix", [(discover_images, ".jpg"), (discover_sidecars, ".desc.json")]
)
def test_bracket_literal_first_at_both_interfaces(tmp_path, discover, suffix):
    literal = make(tmp_path, "[a]" + suffix)
    make(tmp_path, "a" + suffix)
    result = discover([str(literal)])
    assert names(result) == [literal.name]
    assert result.kinds == ("file",) and not result.batch


def test_depth_order_extensions_overrides_and_provenance(tmp_path):
    for name in [
        "z.JPG",
        ".hidden.png",
        "a.jpeg",
        "b.webp",
        "c.tif",
        "d.TIFF",
        "e.jpg",
        "ignore.raw",
        "dir/f.jpg",
        "dir/deep/g.jpg",
    ]:
        make(tmp_path, name)
    result = discover_images([str(tmp_path)])
    assert names(result) == [
        ".hidden.png",
        "a.jpeg",
        "b.webp",
        "c.tif",
        "d.TIFF",
        "e.jpg",
        "z.JPG",
        "f.jpg",
        "g.jpg",
    ]
    assert names(discover_images([str(tmp_path)], max_depth=0)) == names(result)[:7]
    assert names(discover_images([str(tmp_path)], max_depth=1)) == names(result)[:8]
    assert names(discover_images([str(tmp_path)], extensions=["raw"])) == ["ignore.raw"]
    assert result.batch and result.candidates[0].selection_index == 0
    assert discover_images([str(tmp_path)]) == result


def test_recursive_patterns_negation_and_distinct_case(tmp_path):
    if os.name == "nt":
        pytest.skip("requires a case-sensitive directory")
    make(tmp_path, "A.jpg")
    make(tmp_path, "a.jpg")
    make(tmp_path, "nest/z.jpg")
    result = discover_images([str(tmp_path / "**/**/[!b].jpg")], ignore_case=True)
    assert names(result) == ["A.jpg", "a.jpg", "z.jpg"]
    assert len({item.identity for item in result.candidates}) == 3
    assert result.batch


def test_literal_prefix_is_not_case_insensitive(tmp_path):
    if os.name == "nt":
        pytest.skip("requires a case-sensitive directory")
    make(tmp_path, "Photos/a.jpg")
    with pytest.raises(DiscoveryError):
        discover_images([str(tmp_path / "photos/*.jpg")], ignore_case=True)


def test_literal_first_and_overlapping_identities(tmp_path):
    literal = make(tmp_path, "photo[1].jpg")
    make(tmp_path, "photo1.jpg")
    single = discover_images([str(literal)])
    assert names(single) == ["photo[1].jpg"] and not single.batch
    result = discover_images([str(literal), str(tmp_path), str(literal)])
    assert names(result) == ["photo[1].jpg", "photo1.jpg"]
    assert [x.selection_index for x in result.candidates] == [0, 1]
    assert result.batch
    literal.unlink()
    assert names(discover_images([str(literal)])) == ["photo1.jpg"]


def test_native_glob_unicode_brackets_recursive_and_case(tmp_path):
    for name in [
        "a.jpg",
        "B.JPG",
        "K.jpg",
        ".x.jpg",
        "one/a.jpg",
        "one/deep/b.jpg",
        "[.jpg",
        "].jpg",
    ]:
        make(tmp_path, name)
    assert names(discover_images([str(tmp_path / "*.jpg")])) == [
        ".x.jpg",
        "[.jpg",
        "].jpg",
        "a.jpg",
        "K.jpg",
    ]
    assert "B.JPG" in names(
        discover_images([str(tmp_path / "*.jpg")], ignore_case=True)
    )
    assert names(discover_images([str(tmp_path / "[a-k].jpg")], ignore_case=True)) == [
        "B.JPG",
        "a.jpg",
        "K.jpg",
    ]
    assert (
        names(discover_images([str(tmp_path / "**/*.jpg")], max_depth=1))[-1] == "a.jpg"
    )
    assert names(discover_images([str(tmp_path / "[[]*.jpg")])) == ["[.jpg"]
    assert names(discover_images([str(tmp_path / "[]]*.jpg")])) == ["].jpg"]
    assert _compile_component("[**].jpg", False).fullmatch("*.jpg")
    assert _compile_component("[?].jpg", False).fullmatch("?.jpg")
    if os.name != "nt":
        make(tmp_path, "*.jpg")
        make(tmp_path, "?.jpg")
        assert names(discover_images([str(tmp_path / "[**].jpg")])) == ["*.jpg"]
        assert names(discover_images([str(tmp_path / "[*].jpg")])) == ["*.jpg"]
        assert names(discover_images([str(tmp_path / "[?].jpg")])) == ["?.jpg"]


@pytest.mark.parametrize(
    "pattern", ["[abc", "[]", "[!]", "[z-a]", "x**y", "*/../*.jpg"]
)
def test_invalid_glob_is_fatal_even_after_valid_input(tmp_path, pattern):
    good = make(tmp_path, "ok.jpg")
    with pytest.raises(DiscoveryError):
        discover_images([str(good), str(tmp_path / pattern)])


def test_resolved_controls_feed_both_interfaces(tmp_path):
    make(tmp_path, "nested/a.PNG")
    make(tmp_path, "nested/a.desc.json")
    config = resolve_config(
        discovery_paths=(),
        overrides=[
            "selection.max_depth=1",
            "selection.extensions=[png]",
            "category_rebuild.max_depth=0",
        ],
    )
    assert names(discover_images([str(tmp_path)], **config["selection"])) == ["a.PNG"]
    assert names(discover_sidecars([str(tmp_path)], **config["category_rebuild"])) == []


def test_explicit_file_compatibility_and_sidecar_independent_depth(tmp_path):
    raw = make(tmp_path, "item.raw")
    make(tmp_path, "orphan.desc.json")
    make(tmp_path, "nested/other.desc.json")
    assert names(discover_images([str(raw)])) == ["item.raw"]
    with pytest.raises(DiscoveryError):
        discover_sidecars([str(raw)])
    assert names(discover_sidecars([str(tmp_path)], max_depth=0)) == [
        "orphan.desc.json"
    ]
    assert names(discover_sidecars([str(tmp_path)], max_depth=1)) == [
        "orphan.desc.json",
        "other.desc.json",
    ]
    assert names(
        discover_sidecars([str(tmp_path / "**/*.DESC.JSON")], ignore_case=True)
    ) == ["orphan.desc.json", "other.desc.json"]


def test_empty_missing_and_errors(tmp_path, monkeypatch):
    assert discover_images([str(tmp_path)]).candidates == ()
    assert discover_images([str(tmp_path / "*.jpg")]).candidates == ()
    for inputs in [
        [],
        [""],
        [str(tmp_path / "missing")],
        [str(tmp_path / "missing" / "*.jpg")],
    ]:
        with pytest.raises(DiscoveryError):
            discover_images(inputs)
    for value in [-1, True, 1.5]:
        with pytest.raises(DiscoveryError):
            discover_images([str(tmp_path)], max_depth=value)

    def fail(_):
        raise PermissionError("private detail")

    monkeypatch.setattr(os, "scandir", fail)
    with pytest.raises(DiscoveryError, match="enumerated") as error:
        discover_images([str(tmp_path)])
    assert "private detail" not in str(error.value)


def test_links_and_hard_links(tmp_path):
    root = tmp_path / "root"
    target = make(root, "target.jpg")
    outside = make(tmp_path, "outside/other.jpg")
    try:
        (root / "alias.jpg").symlink_to(target)
        (root / "broken.jpg").symlink_to(root / "missing")
        (root / "cycle").symlink_to(root, target_is_directory=True)
        (root / "external").symlink_to(outside.parent, target_is_directory=True)
        (tmp_path / "root-link").symlink_to(root, target_is_directory=True)
        os.link(target, root / "hard.jpg")
    except (OSError, NotImplementedError):
        pytest.skip("links unavailable")
    assert names(discover_images([str(root)])) == ["hard.jpg", "target.jpg"]
    assert names(discover_images([str(root / "**/*.jpg")])) == [
        "hard.jpg",
        "target.jpg",
    ]
    assert names(discover_images([str(root / "alias.jpg"), str(target)])) == [
        "target.jpg"
    ]
    assert names(discover_images([str(tmp_path / "root-link")])) == [
        "hard.jpg",
        "target.jpg",
    ]
    with pytest.raises(DiscoveryError):
        discover_images([str(root / "broken.jpg")])


@pytest.mark.parametrize(
    ("token", "prefix", "parts"),
    [
        (r"C:\Photos\*.jpg", "C:\\Photos", ("*.jpg",)),
        ("C:/Photos/*.jpg", "C:\\Photos", ("*.jpg",)),
        (r"\\server\share\photos\*.jpg", r"\\server\share\photos", ("*.jpg",)),
    ],
)
def test_windows_grammar_without_windows_runtime(token, prefix, parts):
    anchor, suffix = split_pattern(token, windows=True)
    assert anchor == PureWindowsPath(prefix)
    assert suffix == parts


def test_posix_backslash_and_no_content_reads(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("POSIX filename semantics")
    make(tmp_path, r"name\file.jpg")

    def forbidden(*args, **kwargs):
        raise AssertionError("content access")

    monkeypatch.setattr(Path, "open", forbidden)
    assert names(discover_images([str(tmp_path / "*.jpg")])) == [r"name\file.jpg"]


@pytest.mark.parametrize(
    "discover,suffix", [(discover_images, ".jpg"), (discover_sidecars, ".desc.json")]
)
@pytest.mark.parametrize("failure", [False, True])
def test_discovery_never_reads_or_mutates_contents(
    tmp_path, monkeypatch, discover, suffix, failure
):
    first = make(tmp_path, "first" + suffix)
    second = make(tmp_path, "nested/second" + suffix)
    before = {p: p.read_bytes() for p in (first, second)}

    def forbidden(*args, **kwargs):
        raise AssertionError("content access or mutation")

    with monkeypatch.context() as patch:
        for obj, attr in [
            (builtins, "open"),
            (os, "open"),
            (Path, "open"),
            (os, "unlink"),
            (os, "remove"),
            (os, "rename"),
            (os, "replace"),
            (os, "mkdir"),
            (os, "rmdir"),
        ]:
            patch.setattr(obj, attr, forbidden)
        inputs = [str(first), str(tmp_path)] if failure else [str(tmp_path)]
        if failure:

            def denied(*args, **kwargs):
                raise PermissionError("private injected detail")

            patch.setattr(os, "scandir", denied)
            with pytest.raises(DiscoveryError, match="selection index 1"):
                discover(inputs)
        else:
            assert names(discover(inputs)) == [first.name, second.name]
    assert {p: p.read_bytes() for p in before} == before


@pytest.mark.parametrize(
    "discover,suffix", [(discover_images, ".jpg"), (discover_sidecars, ".desc.json")]
)
@pytest.mark.parametrize("failure", ["scandir", "entry_stat", "resolve", "invalid"])
def test_injected_errors_after_valid_selection_are_atomic_and_sanitized(
    tmp_path, monkeypatch, discover, suffix, failure
):
    good = make(tmp_path, "good" + suffix)
    folder = tmp_path / "folder"
    make(folder, "item" + suffix)
    secret = "PRIVATE_SENTINEL"
    original_scandir = os.scandir
    original_resolve = Path.resolve

    def fail(*args, **kwargs):
        raise PermissionError(secret)

    if failure == "scandir":
        monkeypatch.setattr(os, "scandir", fail)
    elif failure == "resolve":

        def resolve(path, *args, **kwargs):
            if path == folder:
                return fail()
            return original_resolve(path, *args, **kwargs)

        monkeypatch.setattr(Path, "resolve", resolve)
    elif failure == "entry_stat":

        class Entries:
            def __enter__(self):
                with original_scandir(folder) as entries:
                    entry = next(iter(entries))
                    return [SimpleNamespace(name=entry.name, stat=fail)]

            def __exit__(self, *args):
                return False

        monkeypatch.setattr(os, "scandir", lambda path: Entries())
    target = "bad\0" + secret if failure == "invalid" else str(folder)
    with pytest.raises(DiscoveryError) as error:
        discover([str(good), target])
    assert "selection index 1" in str(error.value)
    assert secret not in str(error.value)


@pytest.mark.parametrize(
    "discover,suffix", [(discover_images, ".jpg"), (discover_sidecars, ".desc.json")]
)
def test_simulated_reparse_entries_are_not_followed(
    tmp_path, monkeypatch, discover, suffix
):
    keep = make(tmp_path, "keep" + suffix)
    skip = make(tmp_path, "skip" + suffix)
    make(tmp_path, "redirect/hidden" + suffix)
    original_scandir = os.scandir

    class Entry:
        def __init__(self, entry):
            self.entry = entry
            self.name = entry.name
            self.path = entry.path

        def stat(self, **kwargs):
            info = self.entry.stat(**kwargs)
            return SimpleNamespace(
                st_mode=info.st_mode,
                st_file_attributes=(
                    getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
                    if self.name in {skip.name, "redirect"}
                    else 0
                ),
            )

    class Entries:
        def __init__(self, path):
            self.inner = original_scandir(path)

        def __enter__(self):
            return [Entry(entry) for entry in self.inner]

        def __exit__(self, *args):
            self.inner.close()

    monkeypatch.setattr(os, "scandir", Entries)
    assert names(discover([str(tmp_path)])) == [keep.name]
    assert names(discover([str(tmp_path / ("**/*" + suffix))])) == [keep.name]
