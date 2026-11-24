import sys
from collections import deque
from pathlib import Path

import pytest

from image_clarus.batch_plan import Admission, PlanningInput, build_plan, route
from image_clarus.stage_registry import StageDescriptor


@pytest.fixture
def config():
    return {"stages": {"desc": {"regenerate": False}, "json": {"regenerate": False}}}


def item(path):
    return PlanningInput(str(path), ("fictional", str(path.parent), "directory"))


def test_admission_routes_and_dedup(tmp_path, config):
    a, b, c = (tmp_path / f"{n}.jpg" for n in range(3))
    Path(str(a) + ".desc.txt").touch()
    Path(str(a) + ".desc.json").touch()
    Path(str(c) + ".desc.json").touch()
    plan = build_plan(map(item, (a, b, c, b)), config, limit=1)
    assert [r[4] for r in plan.rows] == [
        Admission.NO_LLM_WORK,
        Admission.ADMITTED,
        Admission.KNOWN_EXCLUDED,
    ]
    assert [len(q) for q in plan.queues] == [1, 0, 2]
    assert route(plan.rows[2], plan.stages) == (2, 2)
    assert plan.counts[Admission.ADMITTED] == 1


def test_regeneration_selection_and_generic_capability(tmp_path, config):
    p = tmp_path / "a.jpg"
    Path(str(p) + ".desc.txt").touch()
    config["stages"]["desc"]["regenerate"] = True
    assert (
        build_plan([item(p)], config, selected=("desc",), limit=0).rows[0][4]
        is Admission.KNOWN_EXCLUDED
    )
    assert (
        build_plan([item(p)], config, selected=("xmp",), limit=0).rows[0][4]
        is Admission.NO_LLM_WORK
    )
    custom = (StageDescriptor("other", False, False, lambda _: False),)
    plan = build_plan([item(p)], config, stages=custom, limit=0)
    assert len(plan.queues[0]) == 1
    assert plan.rows[0][4] is Admission.NO_LLM_WORK


def test_stream_estimate_matches_execution_graph(tmp_path, config):
    values = [item(tmp_path / f"{i}.jpg") for i in range(100)]
    execution = build_plan(values, config, limit=7)
    seen = []
    streamed = build_plan(
        values,
        config,
        limit=7,
        aggregate_only=True,
        stream=lambda *args: seen.append(args),
    )
    assert len(seen) == 100
    assert streamed.rows == []
    assert streamed.estimated_bytes == execution.estimated_bytes
    assert streamed.counts == execution.counts


def test_ten_thousand_routes(tmp_path, config, monkeypatch):
    def exists(path):
        image = int(path.name.split(".")[0])
        return image < 6000 or (image < 7000 and str(path).endswith(".desc.txt"))

    monkeypatch.setattr(Path, "exists", exists)
    order = list(range(6000)) + list(range(7000, 10000)) + list(range(6000, 7000))
    plan = build_plan((item(tmp_path / f"{i}.jpg") for i in order), config, limit=1000)
    assert plan.counts == {
        Admission.ADMITTED: 1000,
        Admission.NO_LLM_WORK: 6000,
        Admission.KNOWN_EXCLUDED: 3000,
    }
    assert [len(q) for q in plan.queues] == [1000, 0, 9000]


def test_planning_has_no_execution_or_mutation_side_effects(
    tmp_path, config, monkeypatch
):
    import os
    import sqlite3

    from image_clarus.artifacts import ArtifactService
    from image_clarus.providers.openai_compatible import OpenAICompatible
    from image_clarus.stage_registry import StageDescriptor
    from image_clarus.xmp_backend import ExifToolBackend

    def prohibited(*args, **kwargs):
        raise AssertionError("planning performed an execution side effect")

    image = tmp_path / "a.jpg"
    image.touch()
    for method in (
        "open",
        "read_bytes",
        "read_text",
        "write_bytes",
        "write_text",
        "unlink",
        "replace",
        "rename",
        "mkdir",
        "touch",
        "chmod",
    ):
        monkeypatch.setattr(Path, method, prohibited)
    for method in ("open", "remove", "unlink", "replace", "mkdir"):
        monkeypatch.setattr(os, method, prohibited)
    monkeypatch.setattr(os, "open", prohibited)
    monkeypatch.setattr("builtins.open", prohibited)
    monkeypatch.setattr(sqlite3, "connect", prohibited)
    monkeypatch.setattr("subprocess.Popen", prohibited)
    monkeypatch.setattr(ArtifactService, "recover", prohibited)
    monkeypatch.setattr(ArtifactService, "write", prohibited)
    monkeypatch.setattr(OpenAICompatible, "_send", prohibited)
    monkeypatch.setattr(ExifToolBackend, "_run", prohibited)

    build_plan([item(image)], config)
    build_plan([item(image)], config, aggregate_only=True)
    build_plan([item(image)], config, selected=("xmp",), limit=0)

    def fail_prediction(_image):
        raise RuntimeError("synthetic planning failure")

    broken = StageDescriptor("probe", True, True, fail_prediction)
    with pytest.raises(RuntimeError, match="synthetic planning failure"):
        build_plan(
            [PlanningInput(str(image), ("selection", str(tmp_path), "file"))],
            {"stages": {"probe": {"regenerate": False}}},
            stages=(broken,),
        )

    def interrupted_inputs():
        yield item(image)
        raise RuntimeError("synthetic input failure")

    with pytest.raises(RuntimeError, match="synthetic input failure"):
        build_plan(interrupted_inputs(), config)

    with pytest.raises(ValueError, match="selection"):
        build_plan([item(image)], config, selected=("absent",))


@pytest.mark.parametrize("count", [0, 1, 8, 65, 1000])
@pytest.mark.parametrize("stage_count", [0, 1, 3, 5])
def test_estimator_against_independent_graph(count, stage_count):
    stages = tuple(
        StageDescriptor(str(i), i % 2 == 0, False, lambda _: False)
        for i in range(stage_count)
    )
    values = [
        PlanningInput(str(i), (str(i % 3), "shared", "directory")) for i in range(count)
    ]
    plan = build_plan(values, {}, stages=stages, limit=3, aggregate_only=True)
    pool, identities, origins, origin_map, rows = {}, set(), [], {}, []
    queues = tuple(deque() for _ in stages)
    lifecycle = []
    tracking = tuple([] for _ in stages)
    admitted = 0
    for value in values:
        path = pool.setdefault(value.identity, value.identity)
        identities.add(path)
        origin = tuple(pool.setdefault(v, v) for v in value.origin)
        if origin not in origin_map:
            origin_map[origin] = origin
            origins.append(origin)
        origin = origin_map[origin]
        has_llm = any(s.uses_llm for s in stages)
        classification = (
            Admission.NO_LLM_WORK
            if not has_llm
            else Admission.ADMITTED
            if admitted < 3
            else Admission.KNOWN_EXCLUDED
        )
        admitted += classification is Admission.ADMITTED
        row = (path, origin, (1 << stage_count) - 1, 0, classification, 0)
        rows.append(row)
        lifecycle.append(None)
        for slots in tracking:
            slots.append(None)
        target = next(
            (
                i
                for i, stage in enumerate(stages)
                if not (classification is Admission.KNOWN_EXCLUDED and stage.uses_llm)
            ),
            None,
        )
        if target is None and stages:
            target = len(stages) - 1
        if target is not None:
            queues[target].append((row, 0))
    seen = set()

    def charge(obj):
        if id(obj) in seen:
            return 0
        seen.add(id(obj))
        return sys.getsizeof(obj)

    total = sum(
        charge(obj) for obj in (identities, origins, rows, queues, lifecycle, tracking)
    )
    total += sum(charge(obj) for obj in identities)
    for origin in origins:
        total += charge(origin) + sum(charge(value) for value in origin)
    total += sum(charge(row) for row in rows)
    total += sum(
        charge(queue) + sum(charge(entry) for entry in queue) for queue in queues
    )
    total += sum(charge(slots) for slots in tracking)
    assert plan.estimated_bytes == total
    assert not plan.rows and not plan.lifecycle
    assert all(not queue for queue in plan.queues)
    assert all(not slots for slots in plan.tracking)


def test_discovery_candidate_provenance_and_identity(tmp_path, config):
    from image_clarus.discovery import discover_images

    image = tmp_path / "one.jpg"
    image.touch()
    pattern = str(tmp_path / "*.jpg")
    result = discover_images([pattern, str(image)])
    assert len(result.candidates) == 1
    plan = build_plan([PlanningInput.from_candidate(result.candidates[0])], config)
    assert plan.rows[0][:2] == (
        str(image.resolve()),
        (pattern, str(tmp_path.resolve()), "pattern"),
    )
    explicit = discover_images([str(image)]).candidates[0]
    assert PlanningInput.from_candidate(explicit).origin == (
        str(image),
        str(tmp_path.resolve()),
        "file",
    )
    directory = discover_images([str(tmp_path)]).candidates[0]
    assert PlanningInput.from_candidate(directory).origin == (
        str(tmp_path),
        str(tmp_path.resolve()),
        "directory",
    )


def test_legacy_candidate_constructor_captures_anchor(tmp_path):
    from image_clarus.discovery import Candidate

    directory = tmp_path / "missing"
    candidate = Candidate(
        directory / "one.jpg", "identity", 0, str(directory), "directory"
    )
    assert PlanningInput.from_candidate(candidate).origin == (
        str(directory),
        str(directory),
        "directory",
    )


@pytest.mark.parametrize("kind", ["directory", "pattern", "file"])
@pytest.mark.parametrize("replacement", ["redirect", "remove"])
def test_discovery_anchor_survives_symlink_change(tmp_path, config, kind, replacement):
    from image_clarus.discovery import discover_images

    original = tmp_path / "original"
    other = tmp_path / "other"
    original.mkdir()
    other.mkdir()
    image = original / "one.jpg"
    image.touch()
    (other / "one.jpg").touch()
    link = tmp_path / "link"
    link.symlink_to(original, target_is_directory=True)
    selection = str(
        link
        if kind == "directory"
        else link / ("*.jpg" if kind == "pattern" else "one.jpg")
    )
    candidate = discover_images([selection]).candidates[0]
    link.unlink()
    if replacement == "redirect":
        link.symlink_to(other, target_is_directory=True)
    plan = build_plan([PlanningInput.from_candidate(candidate)], config)
    assert plan.rows[0][:2] == (
        str(image.resolve()),
        (selection, str(original.resolve()), kind),
    )


@pytest.mark.parametrize("limit", [-1, True, 1.5])
def test_invalid_limit_fails_before_consuming_inputs(limit):
    def source():
        raise AssertionError("must not consume")
        yield

    with pytest.raises(ValueError, match="limit"):
        build_plan(source(), {}, limit=limit)


def test_stream_is_provisional_when_input_fails(config):
    seen = []

    def source():
        yield PlanningInput("one", ("a", "b", "directory"))
        raise RuntimeError("enumeration failure")

    with pytest.raises(RuntimeError, match="enumeration failure"):
        build_plan(
            source(), config, stream=lambda *row: seen.append(row), aggregate_only=True
        )
    assert len(seen) == 1


def test_stage_independence_and_exact_identity():
    observed = []

    def predicate(path):
        observed.append(str(path))
        return True

    stages = (
        StageDescriptor("one", True, True, predicate),
        StageDescriptor("two", False, False, lambda _: False),
    )
    inputs = [
        PlanningInput("/x/A", ("raw", "anchor", "file")),
        PlanningInput("/x/a", ("raw", "anchor", "file")),
    ]
    plan = build_plan(
        inputs,
        {"stages": {"one": {"regenerate": False}}},
        stages=stages,
        selected=("two",),
    )
    assert len(plan.rows) == 2 and not observed
    assert all(row[4] is Admission.NO_LLM_WORK for row in plan.rows)
    plan = build_plan(inputs, {"stages": {"one": {"regenerate": False}}}, stages=stages)
    assert observed == ["/x/A", "/x/a"]
    assert all(route(row, plan.stages) == (1, 1) for row in plan.rows)


def test_invalid_selection_and_duplicate_stages():
    stage = StageDescriptor("s", False, False, lambda _: False)
    for selected in ((), ("s", "s"), ("absent",)):
        with pytest.raises(ValueError, match="selection"):
            build_plan([], {}, stages=(stage,), selected=selected)
    with pytest.raises(ValueError, match="duplicate"):
        build_plan([], {}, stages=(stage, stage))


@pytest.mark.parametrize(
    "desc_exists,json_exists",
    [(False, False), (False, True), (True, False), (True, True)],
)
@pytest.mark.parametrize(
    "selected",
    [
        ("desc",),
        ("json",),
        ("xmp",),
        ("desc", "json"),
        ("desc", "xmp"),
        ("json", "xmp"),
        ("desc", "json", "xmp"),
    ],
)
@pytest.mark.parametrize(
    "desc_regenerate,json_regenerate",
    [(False, False), (False, True), (True, False), (True, True)],
)
@pytest.mark.parametrize("limit", [None, 0, 1])
def test_metadata_matrix(
    tmp_path,
    config,
    desc_exists,
    json_exists,
    selected,
    desc_regenerate,
    json_regenerate,
    limit,
):
    path = tmp_path / "image.jpg"
    if desc_exists:
        Path(str(path) + ".desc.txt").touch()
    if json_exists:
        Path(str(path) + ".desc.json").touch()
    config["stages"]["desc"]["regenerate"] = desc_regenerate
    config["stages"]["json"]["regenerate"] = json_regenerate
    plan = build_plan([item(path)], config, selected=selected, limit=limit)
    assert tuple(stage.name for stage in plan.stages) == selected
    bypassed = {
        "desc": desc_exists and not desc_regenerate,
        "json": json_exists and not json_regenerate,
        "xmp": False,
    }
    bypass = sum(1 << i for i, stage in enumerate(plan.stages) if bypassed[stage.name])
    work = ((1 << len(selected)) - 1) ^ bypass
    assert plan.rows[0][2] == work
    assert plan.rows[0][3] == bypass
    needs_llm = any(
        not bypassed[stage.name] and stage.uses_llm for stage in plan.stages
    )
    admission = (
        Admission.NO_LLM_WORK
        if not needs_llm
        else Admission.KNOWN_EXCLUDED
        if limit == 0
        else Admission.ADMITTED
    )
    assert plan.rows[0][4] is admission
    eligible = [
        i
        for i, stage in enumerate(plan.stages)
        if not bypass & (1 << i)
        and not (admission is Admission.KNOWN_EXCLUDED and stage.uses_llm)
    ]
    target = eligible[0] if eligible else len(selected) - 1
    confirmation = bypass & ((1 << target) - 1)
    assert route(plan.rows[0], plan.stages) == (target, confirmation)
    assert list(plan.queues[target]) == [(plan.rows[0], confirmation)]
    assert sum(map(len, plan.queues)) == 1
    aggregate = build_plan(
        [item(path)], config, selected=selected, limit=limit, aggregate_only=True
    )
    assert aggregate.estimated_bytes == plan.estimated_bytes


def test_all_bypassed_stages_are_queued_for_confirmation(tmp_path, config):
    path = tmp_path / "image.jpg"
    Path(str(path) + ".desc.txt").touch()
    Path(str(path) + ".desc.json").touch()
    plan = build_plan([item(path)], config, selected=("desc", "json"))
    assert route(plan.rows[0], plan.stages) == (1, 1)
    assert list(plan.queues[1]) == [(plan.rows[0], 1)]
    assert plan.rows[0][4] is Admission.NO_LLM_WORK


@pytest.mark.parametrize(
    "selected,desc_exists,json_exists,limit,expected,mask",
    [
        (("desc",), True, False, None, 0, 0),
        (("desc", "json"), True, True, None, 1, 1),
        (("desc", "json"), True, False, 0, 1, 1),
        (("desc", "json"), False, True, 0, 1, 0),
        (("desc", "json"), False, False, 0, 1, 0),
    ],
)
def test_terminal_routes_retain_tokens_and_confirmation(
    tmp_path, config, selected, desc_exists, json_exists, limit, expected, mask
):
    path = tmp_path / "image.jpg"
    if desc_exists:
        Path(str(path) + ".desc.txt").touch()
    if json_exists:
        Path(str(path) + ".desc.json").touch()
    seen = []
    plan = build_plan([item(path)], config, selected=selected, limit=limit)
    aggregate = build_plan(
        [item(path)],
        config,
        selected=selected,
        limit=limit,
        aggregate_only=True,
        stream=lambda *entry: seen.append(entry),
    )
    assert route(plan.rows[0], plan.stages) == (expected, mask)
    assert list(plan.queues[expected]) == [(plan.rows[0], mask)]
    assert seen == [(plan.rows[0], expected, mask)]
    assert aggregate.estimated_bytes == plan.estimated_bytes
