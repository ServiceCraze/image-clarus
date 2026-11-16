from pathlib import Path


def test_stage_result_records_outcome():
    from image_clarus.results import StageResult

    result = StageResult("desc", "completed", output_path=Path("image.desc.txt"))
    assert result.stage == "desc"
    assert result.status == "completed"
    assert result.output_path == Path("image.desc.txt")
    assert result.reason_code is None
    assert result.error_category is None
    assert result.message == ""
