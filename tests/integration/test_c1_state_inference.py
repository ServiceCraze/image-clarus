"""Held synthetic inference must not lock the selected persistent state."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from test_single_image_pipeline import check_envelope, rig  # noqa: F401


def categories(database):
    with sqlite3.connect(database, timeout=2) as connection:
        return [
            row[0]
            for row in connection.execute(
                "select path from known_categories order by path"
            )
        ]


def test_other_process_reads_and_updates_state_during_held_inference(rig, tmp_path):  # noqa: F811
    init = subprocess.run(
        [sys.executable, "-m", "image_clarus", "init"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert init.returncode == 0, (init.stdout, init.stderr)
    state = tmp_path / ".image-clarus"
    database = state / "state.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "insert into known_categories(path) values (?)", ("seed/item",)
        )

    config = rig.config("held-inference")
    rig.desc.write_text("fictional description", encoding="utf-8")
    rig.hold.add("json")
    process = rig.start(config, "--stages", "json", "--state-dir", str(state))
    try:
        assert rig.arrived["json"].wait(15), "provider request never arrived"
        assert process.poll() is None
        assert not rig.structured.exists()

        # This is a separate CLI process using the same selected repository.
        # Its skipped persisted JSON is still accumulated after processing.
        other = tmp_path / "other.png"
        other.write_bytes(rig.original)
        artifact = Path(str(other) + ".desc.json")
        artifact_bytes = json.dumps(
            {
                "format_version": 1,
                "schema_id": "urn:image-clarus:metadata-schema:2.0.0",
                "schema_version": "2.0.0",
                "provenance": {
                    "provider_alias": "fictional",
                    "model_alias": "fictional",
                    "model_id": "fictional",
                    "prompt_id": "fictional",
                    "description_sha256": "a" * 64,
                },
                "metadata": {"tag_candidates": [["concurrent", "item"]]},
            }
        ).encode()
        artifact.write_bytes(artifact_bytes)
        # The CLI's macro read and category accumulation exercise the public path.
        prompt = tmp_path / "macro.txt"
        prompt.write_text("Known: {{state.categories.known}}", encoding="utf-8")
        writer = subprocess.run(
            [
                sys.executable,
                "-m",
                "image_clarus",
                "process",
                str(other),
                "--stages",
                "desc,json",
                "--desc-prompt",
                str(prompt),
                "--config",
                str(config),
                "--state-dir",
                str(state),
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        assert writer.returncode == 0, (writer.stdout, writer.stderr)
        assert "json: skipped" in writer.stdout
        assert artifact.read_bytes() == artifact_bytes
        assert process.poll() is None and not rig.release["json"].is_set()
        assert categories(database) == ["concurrent/item", "seed/item"]
        rig.release["json"].set()
        stdout = rig.finish(process)
        assert "json: completed" in stdout
        check_envelope(rig, "fictional description")
        assert categories(database) == [
            "color/blue",
            "concurrent/item",
            "seed/item",
            "shape/square",
        ]
        assert rig.image.read_bytes() == rig.original
        assert other.read_bytes() == rig.original
        assert [request[0] for request in rig.requests] == ["json", "desc"]
        assert "seed/item" in json.dumps(rig.requests[1][1])
    finally:
        rig.release["json"].set()
