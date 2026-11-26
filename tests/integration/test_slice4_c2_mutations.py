"""Post-plan sidecar mutations through the CLI and a held loopback request.

Supplemental coverage: the transport is a synthetic local provider, while planning,
selection, correction, execution and publication are production paths.
"""

import base64
import json
import re
from pathlib import Path

import pytest
from test_single_image_pipeline import V2, rig  # noqa: F401
from test_slice4_c1_corrections import finish, start_batch


@pytest.mark.parametrize("mutation", ["changed", "deleted", "recreated"])
@pytest.mark.parametrize("excluded_mutation", ["created", "deleted", "recreated"])
def test_post_plan_mutations_preserve_exclusion_and_correct_work(
    rig,  # noqa: F811
    tmp_path,
    mutation,
    excluded_mutation,
):
    images = [rig.image.parent / f"{name}.png" for name in ("a", "b", "z")]
    rig.image.rename(images[0])
    # Distinct image bytes allow exact attribution of actual provider requests.
    originals = [rig.original + bytes([i]) for i in range(3)]
    for image, content in zip(images, originals, strict=True):
        image.write_bytes(content)
    sidecars = [Path(str(image) + ".desc.txt") for image in images]
    sidecars[1].write_text("planned existing", encoding="utf-8")
    rig.hold.add("desc")
    process = start_batch(rig, tmp_path, rig.config("mutations"))
    try:
        # Provider entry occurs only after planning; sequential dispatch keeps b and z untouched.
        assert rig.arrived["desc"].wait(20), "first provider request not reached"
        assert process.poll() is None
        if mutation == "changed":
            sidecars[1].write_text("changed after planning", encoding="utf-8")
        else:
            sidecars[1].unlink()
            if mutation == "recreated":
                sidecars[1].write_text("recreated after planning", encoding="utf-8")
        sidecars[2].write_text("created after planning", encoding="utf-8")
        if excluded_mutation != "created":
            sidecars[2].unlink()
            if excluded_mutation == "recreated":
                sidecars[2].write_text("recreated exclusion", encoding="utf-8")
        rig.release["desc"].set()
        stdout, stderr = finish(process)
    finally:
        rig.release["desc"].set()
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)

    assert process.returncode == 0, (stdout, stderr)
    assert not stderr
    assert "summary images=3 admitted=1 no_work=1 excluded=1" in stdout
    corrected = mutation == "deleted"
    count = 2 if corrected else 1
    assert (
        f"work llm_images={count} corrective_images={int(corrected)} "
        f"requests={count} first_requests={count} retries=0"
    ) in stdout
    ends = {}
    for line in stdout.splitlines():
        match = re.match(
            r'^stage end image=("(?:[^"\\]|\\.)*") stage=desc status=(\w+) reason=(\S+) ',
            line,
        )
        if match:
            path = json.loads(match[1])
            assert path not in ends
            ends[path] = (match[2], match[3])
    assert ends == {
        str(images[0]): ("completed", "-"),
        str(images[1]): ("completed", "-")
        if corrected
        else ("skipped", "output_exists"),
        str(images[2]): ("skipped", "budget_excluded"),
    }
    request_images = []
    for stage, body, _ in rig.requests:
        assert stage == "desc"
        url = body["messages"][1]["content"][0]["image_url"]["url"]
        request_images.append(base64.b64decode(url.split(",", 1)[1]))
    assert request_images == (
        [originals[0], originals[1]] if corrected else [originals[0]]
    )
    assert sidecars[0].read_text(encoding="utf-8") == V2
    assert (
        sidecars[1].read_text(encoding="utf-8")
        == {
            "changed": "changed after planning",
            "deleted": V2,
            "recreated": "recreated after planning",
        }[mutation]
    )
    if excluded_mutation == "deleted":
        assert not sidecars[2].exists()
    else:
        assert (
            sidecars[2].read_text(encoding="utf-8")
            == {
                "created": "created after planning",
                "recreated": "recreated exclusion",
            }[excluded_mutation]
        )
    assert [image.read_bytes() for image in images] == originals
