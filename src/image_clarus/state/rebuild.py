"""Strict, additive category rebuild with per-input accounting."""

from dataclasses import dataclass
from pathlib import Path

from image_clarus.discovery import discover_sidecars
from image_clarus.state.accumulation import SidecarExtractionError, extract_sidecar
from image_clarus.state.management import union_categories
from image_clarus.state.readonly import recognize_target


@dataclass
class RebuildResult:
    discovered: int = 0
    inspected: int = 0
    success: int = 0
    skip: int = 0
    input_failure: int = 0
    storage_failure: int = 0
    commit_unknown: int = 0
    interrupted: int = 0
    not_attempted: int = 0
    category_bearing: int = 0
    eligible_paths: int = 0
    transactions_attempted: int = 0
    confirmed_committed: int = 0
    confirmed_inserted: int = 0
    confirmed_inserted_complete: bool = True
    close_failed: bool = False

    @property
    def exit_code(self):
        return int(
            bool(
                self.input_failure
                or self.storage_failure
                or self.commit_unknown
                or self.interrupted
                or self.close_failed
            )
        )

    def render(self):
        fields = vars(self).copy()
        fields["confirmed_inserted_complete"] = str(
            self.confirmed_inserted_complete
        ).lower()
        fields.pop("close_failed")
        return "rebuild " + " ".join(f"{key}={value}" for key, value in fields.items())


def rebuild(
    target,
    sources,
    *,
    max_depth,
    ignore_case,
    read_envelope,
    stop=None,
    migrations=None,
    report_target=None,
    report_error=None,
):
    """Recognize first, discover atomically, then independently commit each input."""
    recognize_target(target, migrations=migrations)
    discovery = discover_sidecars(sources, max_depth=max_depth, ignore_case=ignore_case)
    result = RebuildResult(discovered=len(discovery.candidates))
    if report_target is not None:
        report_target(target.origin)
    for candidate in discovery.candidates:
        if stop is not None and stop.signum is not None:
            break
        result.inspected += 1
        try:
            paths = extract_sidecar(Path(candidate.path), read_envelope)
        except SidecarExtractionError:
            result.input_failure += 1
            if report_error is not None:
                report_error("sidecar extraction failed")
            continue
        if not paths:
            result.skip += 1
            continue
        result.category_bearing += 1
        result.eligible_paths += len(paths)
        outcome = union_categories(target, paths, stop=stop, migrations=migrations)
        result.transactions_attempted += int(outcome.attempted)
        if outcome.status == "committed":
            result.success += 1
            result.confirmed_committed += 1
            result.confirmed_inserted += outcome.inserted
        elif outcome.status == "interrupted":
            result.interrupted += 1
        elif outcome.status == "unknown":
            result.commit_unknown += 1
            result.confirmed_inserted_complete = False
        else:
            result.storage_failure += 1
        if outcome.close_failed:
            result.close_failed = True
        if outcome.status != "committed" or outcome.close_failed:
            if report_error is not None:
                if outcome.status == "committed":
                    report_error("category update committed; repository close failed")
                elif outcome.status == "unknown":
                    report_error("category union outcome unknown")
                else:
                    report_error("category update failed")
            break
    result.not_attempted = result.discovered - result.inspected
    return result
