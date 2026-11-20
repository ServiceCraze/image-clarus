"""B1 CLI JSON evidence using fictional prompts and a local provider stub."""

import hashlib

import pytest
from test_xmp_cli_b5 import DESCRIPTION, assert_source, validate_json

pytest_plugins = ("test_xmp_cli_b5",)


@pytest.fixture
def prompt(rig, tmp_path):
    path = tmp_path / "fictional-prompt.txt"
    # CRLF and non-ASCII exercise exact source-byte hashing without normalization.
    source = "Fictional café with a square.\r\n".encode()
    path.write_bytes(source)
    rig.desc.write_text(DESCRIPTION, encoding="utf-8")
    return path, source


def run_json(rig, *args):
    out, err = rig.finish(rig.start("--stages", "json", *args))
    assert not err
    assert_source(rig)
    return out


@pytest.mark.parametrize(
    "yaml_value,override,expected",
    [
        (None, None, False),
        ("true", None, True),
        ("false", "true", True),
        ("true", "false", False),
    ],
    ids=["default", "yaml-enabled", "cli-enables-over-yaml", "cli-disables-over-yaml"],
)
def test_generated_json_prompt_hash_config_precedence(
    rig, tmp_path, prompt, yaml_value, override, expected
):
    path, source = prompt
    if yaml_value is not None:
        config = tmp_path / "config.yaml"
        config.write_text(
            config.read_text() + f"    include_prompt_sha256: {yaml_value}\n"
        )
    args = ["--json-prompt", str(path)]
    if override is not None:
        args += ["--set", f"stages.json.include_prompt_sha256={override}"]
    assert run_json(rig, *args).startswith("json: completed — output=")
    value = validate_json(rig)
    provenance = value["provenance"]
    assert provenance["prompt_id"] == "custom"
    if expected:
        assert provenance["prompt_sha256"] == hashlib.sha256(source).hexdigest()
    else:
        assert "prompt_sha256" not in provenance
    assert [stage for stage, _ in rig.requests] == ["json"]
    system = rig.requests[0][1]["messages"][0]
    assert system == {"role": "system", "content": source.decode("utf-8")}


def test_changed_prompt_skips_existing_json_until_explicit_regeneration(rig, prompt):
    path, original = prompt
    args = [
        "--json-prompt",
        str(path),
        "--set",
        "stages.json.include_prompt_sha256=true",
    ]
    assert run_json(rig, *args).startswith("json: completed — output=")
    before = rig.structured.read_bytes()
    assert (
        validate_json(rig)["provenance"]["prompt_sha256"]
        == hashlib.sha256(original).hexdigest()
    )
    replacement = b"A different fictional prompt.\n"
    path.write_bytes(replacement)
    assert run_json(rig, *args) == "json: skipped — reason=output_exists\n"
    assert rig.structured.read_bytes() == before
    assert [stage for stage, _ in rig.requests] == ["json"]
    assert run_json(rig, *args, "--regenerate").startswith("json: completed — output=")
    after = validate_json(rig)
    assert (
        after["provenance"]["prompt_sha256"] == hashlib.sha256(replacement).hexdigest()
    )
    assert after["provenance"]["prompt_sha256"] != hashlib.sha256(original).hexdigest()
    assert rig.structured.read_bytes() != before
    assert [stage for stage, _ in rig.requests] == ["json", "json"]
    assert rig.requests[1][1]["messages"][0]["content"] == replacement.decode()


def test_cli_prompt_path_origin_and_dedicated_flag_precedence(rig, tmp_path, prompt):
    config_dir = tmp_path / "config-dir"
    config_dir.mkdir()
    yaml_source = b"YAML relative fictional prompt\n"
    set_source = b"CLI set relative fictional prompt\n"
    flag_source = b"Dedicated flag fictional prompt\n"
    (config_dir / "prompt.txt").write_bytes(yaml_source)
    (tmp_path / "prompt.txt").write_bytes(set_source)
    (tmp_path / "flag.txt").write_bytes(flag_source)
    config = config_dir / "config.yaml"
    config.write_text(
        (tmp_path / "config.yaml").read_text()
        + "    prompt_file: prompt.txt\n    include_prompt_sha256: true\n"
    )
    for args, source in [
        ([], yaml_source),
        (["--set", "stages.json.prompt_file=prompt.txt"], set_source),
        (
            [
                "--json-prompt",
                "flag.txt",
                "--set",
                "stages.json.prompt_file=prompt.txt",
            ],
            flag_source,
        ),
    ]:
        if rig.structured.exists():
            rig.structured.unlink()
        out, err = rig.finish(rig.start("--stages", "json", *args, config=config))
        assert out.startswith("json: completed — output=") and not err
        assert (
            validate_json(rig)["provenance"]["prompt_sha256"]
            == hashlib.sha256(source).hexdigest()
        )
        assert rig.requests[-1][1]["messages"][0]["content"] == source.decode()
    assert [stage for stage, _ in rig.requests] == ["json"] * 3
    assert_source(rig)
