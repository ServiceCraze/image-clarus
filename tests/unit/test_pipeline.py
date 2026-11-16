from copy import deepcopy
from pathlib import Path

import pytest

from image_clarus.results import StageResult


def test_default_registry_runs_fakes_in_order_with_same_dependencies():
    from image_clarus.pipeline import STAGE_REGISTRY, run_pipeline

    seen = []
    config = {
        "pipeline": {"on_stage_failure": "stop"},
        "providers": {"local": {"base_url": "https://example.test"}},
        "models": {"vision": {"provider": "local"}},
        "stages": {"desc": {"model": "vision"}, "json": {"model": "vision"}},
        "logging": {"level": "WARNING"},
    }
    original_config = deepcopy(config)
    services = object()
    image = Path("image.jpg")

    def stage(name):
        def run(received_image, received_config, received_services):
            seen.append((name, received_image, received_config, received_services))
            return StageResult(name, "completed")

        return run

    result = run_pipeline(
        image, config, services, {name: stage(name) for name in STAGE_REGISTRY}
    )
    assert STAGE_REGISTRY == ("desc", "json")
    assert [item[0] for item in seen] == ["desc", "json"]
    assert all(
        item[1] is image and item[2] is config and item[3] is services for item in seen
    )
    assert config == original_config
    assert result.image_path is image
    assert result.exit_code == 0


def test_json_only_does_not_invoke_description():
    from image_clarus.pipeline import run_pipeline

    calls = []

    def json_stage(image, config, services):
        calls.append("json")
        return StageResult("json", "failed", error_category="missing_prerequisite")

    result = run_pipeline(
        Path("image.jpg"), {}, None, {"json": json_stage}, selected=("json",)
    )
    assert calls == ["json"]
    assert result.stages[0].error_category == "missing_prerequisite"
    assert result.exit_code == 1


def test_json_stage_skip_policy_remains_a_success():
    from image_clarus.pipeline import run_pipeline

    def json_stage(image, config, services):
        assert config["pipeline"]["missing_prerequisite"] == "skip"
        return StageResult("json", "skipped", reason_code="missing_prerequisite")

    result = run_pipeline(
        Path("image"),
        {"pipeline": {"missing_prerequisite": "skip"}},
        None,
        {"json": json_stage},
        selected=("json",),
    )
    assert result.stages[0].reason_code == "missing_prerequisite"
    assert result.exit_code == 0


@pytest.mark.parametrize("signum,exit_code", [(2, 130), (15, 143)])
def test_signal_during_stage_preserves_completed_result_and_skips_later(
    signum, exit_code
):
    from image_clarus.pipeline import StopToken, run_pipeline

    stop = StopToken()
    calls = []

    def desc(image, config, services):
        calls.append("desc")
        stop.request(signum)
        return StageResult("desc", "completed")

    def json(image, config, services):
        calls.append("json")
        return StageResult("json", "completed")

    result = run_pipeline(
        Path("image"), {}, stop, {"desc": desc, "json": json}, stop=stop
    )
    assert calls == ["desc"]
    assert result.stages[0].status == "completed"
    assert result.stages[1].reason_code == "interrupted"
    assert result.exit_code == exit_code


def test_signal_takes_precedence_over_failure_and_interrupts_unstarted_stage():
    from image_clarus.pipeline import StopToken, run_pipeline

    stop = StopToken()

    def desc(image, config, services):
        stop.request(15)
        return StageResult("desc", "failed", error_category="file_io")

    def json(image, config, services):
        pytest.fail("stage must not start after signal")

    result = run_pipeline(
        Path("image"), {}, None, {"desc": desc, "json": json}, stop=stop
    )
    assert result.exit_code == 143
    assert result.stages[1].reason_code == "interrupted"


def test_explicit_selection_follows_registry_not_request_order():
    from image_clarus.pipeline import run_pipeline

    stages = {
        name: (
            lambda image, config, services, name=name: StageResult(name, "completed")
        )
        for name in ("desc", "json")
    }
    result = run_pipeline(Path("image"), {}, None, stages, selected=("json", "desc"))
    assert [stage.stage for stage in result.stages] == ["desc", "json"]


@pytest.mark.parametrize("selected", [(), ("json", "json"), ("xmp",), ("",)])
def test_invalid_selection_is_rejected_before_execution(selected):
    from image_clarus.pipeline import run_pipeline

    with pytest.raises(ValueError):
        run_pipeline(Path("image"), {}, None, {}, selected=selected)


def test_missing_stage_implementation_is_detected_before_any_stage_runs():
    from image_clarus.pipeline import run_pipeline

    calls = []

    def desc(image, config, services):
        calls.append("desc")
        return StageResult("desc", "completed")

    with pytest.raises(ValueError, match="implementation"):
        run_pipeline(Path("image"), {}, None, {"desc": desc})
    assert calls == []


@pytest.mark.parametrize(
    "policy,expected_calls,expected_status",
    [
        ("stop", ["desc"], "skipped"),
        ("continue", ["desc", "json"], "completed"),
    ],
)
def test_failure_policy_and_exit_aggregation(policy, expected_calls, expected_status):
    from image_clarus.pipeline import run_pipeline

    calls = []

    def desc(image, config, services):
        calls.append("desc")
        return StageResult(
            "desc", "failed", error_category="file_io", message="write failed"
        )

    def json(image, config, services):
        calls.append("json")
        return StageResult("json", "completed")

    result = run_pipeline(
        Path("image"),
        {"pipeline": {"on_stage_failure": policy}},
        None,
        {"desc": desc, "json": json},
    )
    assert calls == expected_calls
    assert result.stages[1].status == expected_status
    if policy == "stop":
        assert result.stages[1].reason_code == "stage_not_run_after_failure"
    assert result.exit_code == 1
