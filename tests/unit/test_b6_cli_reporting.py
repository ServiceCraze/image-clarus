"""B6 CLI planning, execution, and human-readable reporting coverage."""

import sys
from pathlib import Path

from image_clarus import cli
from image_clarus.batch_execution import (
    BatchExecutionResult,
    ExecutionEvent,
    ImageExecutionResult,
    StageOutcome,
)
from image_clarus.batch_plan import Admission, PlanningInput, build_plan
from image_clarus.batch_reporting import BatchReporter
from image_clarus.results import PipelineResult, StageResult
from image_clarus.stage_registry import StageDescriptor


def _config(path):
    path.write_text(
        "providers:\n"
        "  sample:\n"
        "    base_url: http://127.0.0.1:1/v1\n"
        "models:\n"
        "  sample:\n"
        "    provider: sample\n"
        "    model_id: fictional-model\n"
        "stages:\n"
        "  desc:\n"
        "    model: sample\n"
        "  json:\n"
        "    model: sample\n"
    )


def test_dry_run_reports_each_class_and_budget_boundary(tmp_path, monkeypatch, capsys):
    from image_clarus import config
    from image_clarus.state.service import StateService

    for name in ("a.jpg", "b.jpg", "c.jpg"):
        (tmp_path / name).write_bytes(b"synthetic")
    (tmp_path / "a.jpg.desc.txt").write_text("existing")
    settings = tmp_path / "settings.yaml"
    _config(settings)
    monkeypatch.setattr(
        config.shutil, "which", lambda _: (_ for _ in ()).throw(AssertionError())
    )
    monkeypatch.setattr(
        StateService,
        "select",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(tmp_path),
            "--stages",
            "desc",
            "--max-work-files",
            "1",
            "--config",
            str(settings),
            "--dry-run",
        ],
    )

    assert cli.main() == 0
    output = capsys.readouterr()
    rows = [
        line for line in output.out.splitlines() if line.startswith("plan provisional")
    ]
    assert len(rows) == 3
    assert "class=NO_LLM_WORK" in rows[0]
    assert "class=ADMITTED" in rows[1] and "budget=reached" in rows[1]
    assert "class=KNOWN_EXCLUDED" in rows[2]
    assert "plan complete images=3 admitted=1 no_work=1 excluded=1" in output.out
    assert "estimated initial plan/queue memory:" in output.out
    assert output.err == ""


def test_batch_execution_uses_default_concurrency_and_reports_actuals(
    tmp_path, monkeypatch, capsys
):
    for name in ("a.jpg", "b.jpg"):
        (tmp_path / name).write_bytes(b"synthetic")
        (tmp_path / f"{name}.desc.txt").write_text("existing")
    settings = tmp_path / "settings.yaml"
    _config(settings)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(tmp_path),
            "--stages",
            "desc",
            "--config",
            str(settings),
        ],
    )

    assert cli.main() == 0
    output = capsys.readouterr()
    assert "summary images=2 admitted=0 no_work=2 excluded=0" in output.out
    assert (
        "actual stage=desc evaluated=2 transformed=0 completed=0 skipped=2"
        in output.out
    )
    assert "skip stage=desc reason=output_exists count=2" in output.out
    assert "work llm_images=0 corrective_images=0 requests=0" in output.out
    assert "progress accounted=2/2" in output.out
    assert output.err == ""


def test_single_directory_and_pattern_use_batch_missing_prerequisite_default(
    tmp_path, monkeypatch, capsys
):
    image = tmp_path / "one.jpg"
    image.write_bytes(b"synthetic")
    settings = tmp_path / "settings.yaml"
    _config(settings)

    for selection in (str(tmp_path), str(tmp_path / "*.jpg")):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "image-clarus",
                "process",
                selection,
                "--stages",
                "json",
                "--config",
                str(settings),
            ],
        )

        assert cli.main() == 0
        output = capsys.readouterr()
        assert "skip stage=json reason=missing_prerequisite count=1" in output.out
        assert output.err == ""


def test_dry_run_configuration_error_marks_plan_incomplete(
    tmp_path, monkeypatch, capsys
):
    image = tmp_path / "one.jpg"
    image.write_bytes(b"synthetic")
    settings = tmp_path / "settings.yaml"
    settings.write_text("pipeline:\n  max_work_files: 0\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--config",
            str(settings),
            "--dry-run",
        ],
    )

    assert cli.main() == 2
    output = capsys.readouterr()
    assert "plan incomplete" in output.err
    assert "estimate unavailable: incomplete plan" in output.err


def test_dry_run_redacts_configured_secret_from_path(tmp_path, monkeypatch, capsys):
    secret = "synthetic-secret"
    image = tmp_path / f"image-{secret}.jpg"
    image.write_bytes(b"synthetic")
    settings = tmp_path / "settings.yaml"
    _config(settings)
    settings.write_text(
        settings.read_text().replace("base_url:", f"api_key: {secret}\n    base_url:")
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--stages",
            "desc",
            "--config",
            str(settings),
            "--dry-run",
        ],
    )

    assert cli.main() == 0
    output = capsys.readouterr()
    assert secret not in output.out
    assert "[REDACTED]" in output.out
    assert secret not in output.err


def test_reporter_ignores_duplicate_state_diagnostic_rendering():
    plan = build_plan((), {})
    errors = []
    reporter = BatchReporter(plan, emit_error=errors.append)
    reporter.consume(
        ExecutionEvent(
            sequence=0,
            monotonic_ns=0,
            invocation_id="test",
            kind="state_diagnostic",
            image_id=0,
            error_category="unavailable",
        )
    )

    assert reporter.render_summary(BatchExecutionResult(()))
    assert errors == []


def test_reporter_flags_missing_terminal_and_unmatched_request():
    plan = build_plan(
        [PlanningInput("synthetic.jpg", ("synthetic.jpg", ".", "file"))],
        {},
        stages=(StageDescriptor("desc", True, False, lambda _image: False),),
    )
    errors = []
    reporter = BatchReporter(plan, emit_error=errors.append)
    reporter.consume(
        ExecutionEvent(
            sequence=0,
            monotonic_ns=0,
            invocation_id="test",
            kind="provider_request_started",
            image_id=0,
            stage="desc",
            generation=0,
            request_id="request-1",
        )
    )

    assert not reporter.render_summary(BatchExecutionResult(()))
    assert errors == ["image-clarus: internal accounting error; summary incomplete"]


def _one_stage_plan():
    return build_plan(
        [PlanningInput("synthetic.jpg", ("synthetic.jpg", ".", "file"))],
        {},
        stages=(StageDescriptor("desc", True, False, lambda _image: False),),
    )


def _skipped_result(reason):
    stage = StageResult("desc", "skipped", reason_code=reason)
    return BatchExecutionResult(
        (
            ImageExecutionResult(
                Path("synthetic.jpg"),
                Admission.ADMITTED,
                (StageOutcome("desc", "skipped", stage, reason),),
                PipelineResult(Path("synthetic.jpg"), (stage,)),
                "not_required",
            ),
        )
    )


def test_reporter_rejects_conflicting_provider_request_identity():
    reporter = BatchReporter(_one_stage_plan(), emit_error=lambda _message: None)
    reporter.consume(
        ExecutionEvent(
            0,
            0,
            "test",
            "provider_request_started",
            0,
            stage="desc",
            generation=0,
            request_id="request-1",
            attempt_number=0,
            is_validation_retry=False,
        )
    )
    reporter.consume(
        ExecutionEvent(
            1,
            0,
            "test",
            "provider_request_result",
            1,
            stage="json",
            generation=0,
            request_id="request-1",
            attempt_number=0,
            is_validation_retry=False,
        )
    )
    reporter.consume(
        ExecutionEvent(
            2,
            0,
            "test",
            "stage_terminal",
            0,
            stage="desc",
            generation=0,
            admission=Admission.ADMITTED,
            disposition="skipped",
            reason_code="output_exists",
        )
    )

    assert not reporter.reconcile(_skipped_result("output_exists"))


def test_reporter_rejects_conflicting_terminal_reason_code():
    reporter = BatchReporter(_one_stage_plan(), emit_error=lambda _message: None)
    reporter.consume(
        ExecutionEvent(
            0,
            0,
            "test",
            "stage_terminal",
            0,
            stage="desc",
            generation=0,
            admission=Admission.ADMITTED,
            disposition="skipped",
            reason_code="output_exists",
        )
    )

    assert not reporter.reconcile(_skipped_result("missing_prerequisite"))


def test_reporter_rejects_terminal_generation_not_in_plan():
    reporter = BatchReporter(_one_stage_plan(), emit_error=lambda _message: None)
    reporter.consume(
        ExecutionEvent(
            0,
            0,
            "test",
            "stage_terminal",
            0,
            stage="desc",
            generation=99,
            admission=Admission.ADMITTED,
            disposition="skipped",
            reason_code="output_exists",
        )
    )

    assert not reporter.reconcile(_skipped_result("output_exists"))


def test_reporter_rejects_terminal_admission_not_in_plan():
    reporter = BatchReporter(_one_stage_plan(), emit_error=lambda _message: None)
    reporter.consume(
        ExecutionEvent(
            0,
            0,
            "test",
            "stage_terminal",
            0,
            stage="desc",
            generation=0,
            admission=Admission.NO_LLM_WORK,
            disposition="skipped",
            reason_code="output_exists",
        )
    )

    assert not reporter.reconcile(_skipped_result("output_exists"))


def test_single_file_compatibility_path_still_reconciles(tmp_path, monkeypatch, capsys):
    image = tmp_path / "one.jpg"
    image.write_bytes(b"synthetic")
    (tmp_path / "one.jpg.desc.txt").write_text("existing")
    settings = tmp_path / "settings.yaml"
    _config(settings)
    monkeypatch.setattr(BatchReporter, "reconcile", lambda *_args: False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--stages",
            "desc",
            "--config",
            str(settings),
            "--no-inter-stage-concurrency",
        ],
    )

    assert cli.main() == 1
    output = capsys.readouterr()
    assert "internal accounting error; summary incomplete" in output.err
    assert "desc: skipped" not in output.out


def test_invalid_stage_dry_run_marks_plan_incomplete(tmp_path, monkeypatch, capsys):
    image = tmp_path / "one.jpg"
    image.write_bytes(b"synthetic")
    monkeypatch.setattr(
        sys,
        "argv",
        ["image-clarus", "process", str(image), "--stages", "invalid", "--dry-run"],
    )

    assert cli.main() == 2
    output = capsys.readouterr()
    assert "plan incomplete" in output.err
    assert "estimate unavailable: incomplete plan" in output.err


def test_verbose_failed_terminal_uses_category_without_mutating_reconciliation():
    plan = _one_stage_plan()
    lines = []
    reporter = BatchReporter(plan, emit=lines.append, verbose=True)
    stage = StageResult(
        "desc", "failed", error_category="network_timeout", message="private details"
    )
    result = BatchExecutionResult(
        (
            ImageExecutionResult(
                Path("synthetic.jpg"),
                Admission.ADMITTED,
                (StageOutcome("desc", "failed", stage, None),),
                PipelineResult(Path("synthetic.jpg"), (stage,)),
                "not_required",
            ),
        )
    )
    event = ExecutionEvent(
        0,
        0,
        "test",
        "stage_terminal",
        0,
        stage="desc",
        generation=0,
        admission=Admission.ADMITTED,
        disposition="failed",
        error_category="network_timeout",
    )
    reporter.consume(event)
    assert "status=failed reason=network_timeout " in lines[0]
    assert "private details" not in lines[0]
    assert reporter.reconcile(result)
    assert event.reason_code is None
    conflicting = BatchReporter(plan, emit=lambda _: None)
    from dataclasses import replace

    conflicting.consume(replace(event, error_category="configuration"))
    assert not conflicting.reconcile(result)


def test_verbose_failed_terminal_does_not_expose_untrusted_category():
    lines = []
    reporter = BatchReporter(_one_stage_plan(), emit=lines.append, verbose=True)
    reporter.consume(
        ExecutionEvent(
            0,
            0,
            "test",
            "stage_terminal",
            0,
            stage="desc",
            generation=0,
            admission=Admission.ADMITTED,
            disposition="failed",
            error_category="private-token\nforged output",
        )
    )
    assert "reason=unknown" in lines[0]
    assert "private-token" not in lines[0]
    assert "forged output" not in lines[0]
    assert len(lines) == 1 and "\n" not in lines[0]
