"""Unit-driven policy scenarios; these do not run the CLI or publish files."""

import json
from copy import deepcopy
from xml.sax.saxutils import escape, quoteattr

import pytest

from image_clarus.config import DEFAULTS
from image_clarus.stages import xmp


def policy():
    return xmp


def settings(**values):
    result = deepcopy(DEFAULTS["stages"]["xmp"])
    result.update(values)
    return result


def payload(version="2.0.0", **overrides):
    metadata = {
        "subjects": [],
        "objects": [],
        "actions": [],
        "setting": {"type": "", "context": ""},
        "visual_characteristics": {
            "colors": [],
            "composition": "",
            "lighting": "",
            "visual_style": "",
        },
        "keywords": ["fictional keyword"],
    }
    if version == "2.0.0":
        metadata.update(title="", caption="", tag_candidates=[])
    metadata.update(overrides)
    return metadata


def envelope(metadata, version="2.0.0", schema_id=None):
    return {
        "format_version": 1,
        "schema_id": schema_id or f"urn:image-clarus:metadata-schema:{version}",
        "schema_version": version,
        "provenance": {
            "provider_alias": "fictional",
            "model_alias": "fictional",
            "model_id": "fictional",
            "prompt_id": "fictional",
            "prompt_sha256": "a" * 64,
            "description_sha256": "b" * 64,
        },
        "metadata": metadata,
    }


def data(metadata=None, version="2.0.0", schema_id=None):
    return json.dumps(
        envelope(payload(version) if metadata is None else metadata, version, schema_id)
    ).encode()


def packet(tags=(), title=(), caption=(), author=()):
    bag = (
        ""
        if not tags
        else "<dk:TagsList><rdf:Seq>"
        + "".join(f"<rdf:li>{escape(t)}</rdf:li>" for t in tags)
        + "</rdf:Seq></dk:TagsList>"
    )

    def alt(name, values):
        return (
            ""
            if not values
            else f"<{name}><rdf:Alt>"
            + "".join(
                f"<rdf:li xml:lang={quoteattr(lang)}>{escape(value)}</rdf:li>"
                for lang, value in values
            )
            + f"</rdf:Alt></{name}>"
        )

    body = (
        bag
        + alt("dc:title", title)
        + alt("dc:description", caption)
        + alt("dk:CaptionsAuthorNames", author)
    )
    return (
        f'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dk="http://www.digikam.org/ns/1.0/"><rdf:Description rdf:about="">{body}</rdf:Description></rdf:RDF>'
    ).encode()


def calculate(tmp_path, metadata, xmp=None, **opts):
    mod = policy()
    assert mod is not None, "B4 XMP selection and policy module not implemented"
    return mod.prepare_updates(data(metadata), xmp, settings(**opts), tmp_path)


def test_ranked_paths_are_selected_in_order_under_default_root(tmp_path):
    result = calculate(
        tmp_path,
        payload(tag_candidates=[["food", "pepper"], ["color", "red"], ["plate"]]),
        tag_limit=2,
    )
    assert result.updates == {"tags": ["ai/food/pepper", "ai/color/red"]}
    assert result.effective_tag_policy == "add"


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("disabled", None),
        (
            "add",
            ["manual/leaf", "auto/plate", "ai/old", "aisle/lamp", "ai/food/pepper"],
        ),
        ("new", None),
        ("overwrite", ["manual/leaf", "auto/plate", "aisle/lamp", "ai/food/pepper"]),
    ],
)
def test_nonempty_root_policy_table(tmp_path, mode, expected):
    existing = packet(tags=["manual/leaf", "auto/plate", "ai/old", "aisle/lamp"])
    result = calculate(
        tmp_path,
        payload(tag_candidates=[["food", "pepper"]]),
        existing,
        tag_policy=mode,
    )
    assert result.updates == ({} if expected is None else {"tags": expected})
    assert result.effective_tag_policy == mode
    if expected is None:
        assert (result.status, result.reason_code) == ("skipped", "no_change")


@pytest.mark.parametrize("mode", ["add", "new", "overwrite", "disabled"])
def test_empty_root_is_nondestructive_and_idempotent(tmp_path, mode):
    old = ["manual/leaf", "auto/plate", "food/pepper", "ai/old", "rootless"]
    metadata = payload(tag_candidates=[["food", "pepper"], ["food", "pizza"]])
    result = calculate(
        tmp_path, metadata, packet(tags=old), tag_root="", tag_policy=mode
    )
    assert result.effective_tag_policy == ("disabled" if mode == "disabled" else "add")
    expected = old if mode == "disabled" else old + ["food/pizza"]
    assert result.updates == ({} if expected == old else {"tags": expected})
    again = calculate(
        tmp_path, metadata, packet(tags=expected), tag_root="", tag_policy=mode
    )
    assert again.updates == {} and again.reason_code == "no_change"


def test_new_root_is_exact_segment_and_ancestor_is_not_implicitly_assigned(tmp_path):
    result = calculate(
        tmp_path,
        payload(tag_candidates=[["food", "pizza"]]),
        packet(tags=["aisle/lamp"]),
        tag_policy="new",
    )
    assert result.updates == {"tags": ["aisle/lamp", "ai/food/pizza"]}


@pytest.mark.parametrize("mode", ["add", "new", "overwrite", "disabled"])
@pytest.mark.parametrize("limit,candidates", [(0, [["leaf"]]), (10, [])])
def test_empty_or_zero_selection_never_clears_tags(tmp_path, mode, limit, candidates):
    result = calculate(
        tmp_path,
        payload(tag_candidates=candidates),
        packet(tags=["ai/old", "manual/x"]),
        tag_limit=limit,
        tag_policy=mode,
    )
    assert result.updates == {} and result.reason_code == "no_change"


@pytest.mark.parametrize(
    "field,setting",
    [
        ("title", "title_policy"),
        ("caption", "caption_policy"),
        ("author", "caption_author_policy"),
    ],
)
@pytest.mark.parametrize("mode", ["new", "overwrite", "disabled"])
@pytest.mark.parametrize(
    "existing",
    [(), (("x-default", "Old"),), (("fr", "Bonjour"),), (("fr", ""),), (("fr", " "),)],
)
def test_field_policies_use_all_language_alternatives(
    tmp_path, field, setting, mode, existing
):
    metadata = payload(title="New title", caption="New caption")
    config = {
        "title_policy": "disabled",
        "caption_policy": "disabled",
        "caption_author_policy": "disabled",
        "caption_author": "New author",
        setting: mode,
    }
    source = {"title": "New title", "caption": "New caption", "author": "New author"}[
        field
    ]
    result = calculate(tmp_path, metadata, packet(**{field: existing}), **config)
    occupied = any(value != "" for _, value in existing)
    changed = mode == "overwrite" or (mode == "new" and not occupied)
    assert result.updates == ({field: source} if changed else {})


def test_field_policies_are_independent_and_empty_sources_preserve(tmp_path):
    old = packet(
        title=[("x-default", "Old title")],
        caption=[("x-default", "Old caption")],
        author=[("x-default", "Old author")],
    )
    result = calculate(
        tmp_path,
        payload(title="New", caption=""),
        old,
        title_policy="overwrite",
        caption_policy="overwrite",
        caption_author=None,
        caption_author_policy="overwrite",
    )
    assert result.updates == {"title": "New"}
    result = calculate(
        tmp_path,
        payload(),
        old,
        title_policy="overwrite",
        caption_policy="overwrite",
        caption_author="",
        caption_author_policy="overwrite",
    )
    assert result.updates == {} and result.reason_code == "no_change"


def test_existing_matching_values_are_no_change(tmp_path):
    result = calculate(
        tmp_path,
        payload(title="Same", tag_candidates=[["leaf"]]),
        packet(tags=["ai/leaf"], title=[("x-default", "Same")]),
        title_policy="overwrite",
    )
    assert result.updates == {} and result.reason_code == "no_change"


def custom(metadata, **mapping):
    return data(
        metadata, "custom-sha256:" + "a" * 64, "urn:image-clarus:custom-metadata-schema"
    ), settings(**mapping)


def test_custom_literal_mapping_deduplicates_before_limit_without_normalization(
    tmp_path,
):
    mod = policy()
    raw, opts = custom(
        {
            "rank.list": [["É"], ["É"], ["é"], ["é"], ["bird", "wing"]],
            "headline": "Title",
            "title": "Do not infer",
        },
        custom_tags_property="rank.list",
        custom_title_property="headline",
        tag_limit=3,
    )
    result = mod.prepare_updates(raw, None, opts, tmp_path)
    assert result.updates == {"tags": ["ai/É", "ai/é", "ai/é"], "title": "Title"}


def test_old_and_unmapped_custom_fields_are_not_inferred(tmp_path):
    mod = policy()
    historical = mod.prepare_updates(
        data(payload("1.0.0"), "1.0.0"), None, settings(), tmp_path
    )
    raw, opts = custom({"title": "Do not infer", "tag_candidates": [["hidden"]]})
    current = mod.prepare_updates(raw, None, opts, tmp_path)
    assert historical.updates == current.updates == {}
    assert historical.reason_code == current.reason_code == "no_change"


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "leaf",
        [],
        [""],
        [" leaf"],
        ["leaf "],
        ["a/b"],
        ["a|b"],
        ["a\x00b"],
        ["a\x85b"],
        [1],
        ["\ud800"],
    ],
)
def test_custom_invalid_candidate_beyond_cutoff_fails(tmp_path, bad):
    raw, opts = custom(
        {"paths": [["good"], bad]}, custom_tags_property="paths", tag_limit=1
    )
    result = policy().prepare_updates(raw, None, opts, tmp_path)
    assert (result.status, result.error_category) == ("failed", "invalid_artifact")


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", None),
        ("title", 7),
        ("caption", []),
        ("tags", None),
        ("tags", {}),
        ("tags", "wrong"),
    ],
)
def test_present_invalid_custom_values_fail(tmp_path, field, value):
    raw, opts = custom(
        {"fictional": value}, **{f"custom_{field}_property": "fictional"}
    )
    result = policy().prepare_updates(raw, None, opts, tmp_path)
    assert (result.status, result.error_category) == ("failed", "invalid_artifact")


@pytest.mark.parametrize(
    "raw", [b"{", b"{}", b'{"x":NaN}', b'{"x":1,"x":2}', b'"\\ud800"', b"\xff"]
)
def test_malformed_json_and_envelope_fail_sanitized(tmp_path, raw):
    result = policy().prepare_updates(raw, None, settings(), tmp_path)
    assert (result.status, result.error_category) == ("failed", "invalid_artifact")


@pytest.mark.parametrize(
    "version,schema_id",
    [
        ("2.0.0", "urn:image-clarus:metadata-schema:1.0.0"),
        ("3.0.0", "urn:image-clarus:metadata-schema:3.0.0"),
        ("custom-sha256:" + "A" * 64, "urn:image-clarus:custom-metadata-schema"),
    ],
)
def test_unknown_or_mismatched_schema_id_fails(tmp_path, version, schema_id):
    raw = data(payload(), version, schema_id)
    result = policy().prepare_updates(raw, None, settings(), tmp_path)
    assert (result.status, result.error_category) == ("failed", "invalid_artifact")


def test_invalid_built_in_payload_and_duplicate_paths_fail(tmp_path):
    mod = policy()
    for bad in [
        payload(tag_candidates=[["dup"], ["dup"]]),
        {k: v for k, v in payload().items() if k != "title"},
        payload(tag_candidates=[["valid"], ["invalid/part"]]),
    ]:
        result = mod.prepare_updates(data(bad), None, settings(tag_limit=1), tmp_path)
        assert (result.status, result.error_category) == ("failed", "invalid_artifact")


@pytest.mark.parametrize(
    "missing,result",
    [
        ("fail", ("failed", "missing_prerequisite", None)),
        ("skip", ("skipped", None, "missing_prerequisite")),
    ],
)
def test_missing_input_differs_from_invalid(tmp_path, missing, result):
    answer = policy().prepare_updates(
        None, None, settings(), tmp_path, missing_prerequisite=missing
    )
    assert (answer.status, answer.error_category, answer.reason_code) == result


def test_mapped_missing_properties_and_duplicate_role_mappings(tmp_path):
    raw, opts = custom(
        {"other": "Fictional"},
        custom_title_property="missing",
        custom_tags_property="missing",
    )
    assert (
        policy().prepare_updates(raw, None, opts, tmp_path).reason_code == "no_change"
    )
    raw, opts = custom(
        {"same": "Fictional"},
        custom_title_property="same",
        custom_caption_property="same",
    )
    assert policy().prepare_updates(raw, None, opts, tmp_path).updates == {
        "title": "Fictional",
        "caption": "Fictional",
    }
    opts["custom_tags_property"] = "same"
    assert (
        policy().prepare_updates(raw, None, opts, tmp_path).error_category
        == "invalid_artifact"
    )


def test_unrepresentable_mapped_text_fails_even_when_disabled(tmp_path):
    raw, opts = custom(
        {"field": "bad\x00value"},
        custom_title_property="field",
        title_policy="disabled",
    )
    assert (
        policy().prepare_updates(raw, None, opts, tmp_path).error_category
        == "invalid_artifact"
    )


def test_unreadable_builtin_schema_is_file_io(tmp_path, monkeypatch):
    from image_clarus import resources

    monkeypatch.setattr(
        resources, "structure_schema", lambda: tmp_path / "missing-schema"
    )
    assert (
        policy().prepare_updates(data(), None, settings(), tmp_path).error_category
        == "file_io"
    )


def test_malformed_xmp_and_malformed_owned_path_fail_without_updates(tmp_path):
    for snapshot in [b"<broken", packet(tags=["ai//bad", "manual/good"])]:
        result = calculate(
            tmp_path,
            payload(tag_candidates=[["leaf"]]),
            snapshot,
            tag_policy="overwrite",
        )
        assert result.status == "failed" and result.error_category == "invalid_artifact"
        assert result.updates == {}


def test_update_plan_roundtrips_with_real_backend_preserving_locales(tmp_path):
    import shutil

    from image_clarus.xmp_backend import ExifToolBackend

    if not shutil.which("exiftool"):
        pytest.skip("ExifTool unavailable")
    backend = ExifToolBackend(tmp_path)
    initial = packet(
        tags=["auto/leaf", "ai/old"],
        title=[("x-default", "Old"), ("fr", "Bonjour")],
        caption=[("fr", "Salut")],
    )
    metadata = payload(
        title="New", caption="Caption", tag_candidates=[["plant", "leaf"]]
    )
    opts = settings(
        tag_policy="overwrite", title_policy="overwrite", caption_policy="new"
    )
    result = policy().prepare_updates(data(metadata), initial, opts, tmp_path)
    assert result.updates == {"tags": ["auto/leaf", "ai/plant/leaf"], "title": "New"}
    updated = backend.transform(initial, result.updates)
    before, after = backend.read(initial), backend.read(updated)
    assert after["tags"] == ["auto/leaf", "ai/plant/leaf"]
    assert ("fr", "Bonjour") in after["properties"][
        "{http://purl.org/dc/elements/1.1/}title"
    ][1]
    assert (
        before["properties"]["{http://purl.org/dc/elements/1.1/}description"]
        == after["properties"]["{http://purl.org/dc/elements/1.1/}description"]
    )
    assert (
        policy().prepare_updates(data(metadata), updated, opts, tmp_path).reason_code
        == "no_change"
    )


def test_parent_and_child_are_distinct_assignments(tmp_path):
    source = payload(tag_candidates=[["food"], ["food", "pizza"], ["plate"]])
    result = calculate(tmp_path, source, packet(tags=["ai/food/pizza"]), tag_limit=2)
    assert result.updates == {"tags": ["ai/food/pizza", "ai/food"]}


@pytest.mark.parametrize("mode", ["add", "new", "overwrite", "disabled"])
def test_nonempty_policy_is_idempotent(tmp_path, mode):
    source = payload(tag_candidates=[["food", "pizza"]])
    existing = ["manual/leaf", "aisle/plant", "ai/old"]
    first = calculate(tmp_path, source, packet(tags=existing), tag_policy=mode)
    second = calculate(
        tmp_path,
        source,
        packet(tags=first.updates.get("tags", existing)),
        tag_policy=mode,
    )
    assert second.reason_code == "no_change" and second.updates == {}


def test_strict_json_rejections_exercise_valid_envelopes(tmp_path):
    original = data(payload(title="Fictional"))
    samples = [
        original.replace(
            b'"format_version": 1', b'"format_version": 1, "format_version": 1'
        ),
        original.replace(b'"title": "Fictional"', b'"title": NaN'),
        original.replace(b'"title": "Fictional"', b'"title": "\\ud800"'),
        original.decode().encode("utf-16"),
    ]
    for raw in samples:
        result = policy().prepare_updates(raw, None, settings(), tmp_path)
        assert result.error_category == "invalid_artifact"


def test_planner_never_invokes_provider_or_json_generation(tmp_path, monkeypatch):
    import socket

    from image_clarus.stages import structure

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected generation")

    monkeypatch.setattr(structure, "run_structure", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    result = calculate(tmp_path, payload(title="Fictional", tag_candidates=[["leaf"]]))
    assert result.updates == {"tags": ["ai/leaf"], "title": "Fictional"}


@pytest.mark.parametrize(
    "digest,valid",
    [(None, True), ("a" * 64, True), ("A" * 64, False), ("a" * 64 + "\n", False)],
)
def test_optional_prompt_hash_at_xmp_publication_boundary(tmp_path, digest, valid):
    value = envelope(payload(title="Fictional", tag_candidates=[["food", "leaf"]]))
    value["provenance"].pop("prompt_sha256")
    if digest is not None:
        value["provenance"]["prompt_sha256"] = digest
    result = xmp.prepare_updates(json.dumps(value).encode(), None, settings(), tmp_path)
    if valid:
        assert result.updates == {"title": "Fictional", "tags": ["ai/food/leaf"]}
    else:
        assert (result.status, result.error_category) == ("failed", "invalid_artifact")
