"""Owned ExifTool children must not inherit the caller's POSIX group."""

import os
import stat
import sys

import pytest

from image_clarus.config import _probe_exiftool
from image_clarus.xmp_backend import ExifToolBackend


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups required")
@pytest.mark.parametrize("probe", [True, False])
def test_exiftool_child_has_separate_process_group(tmp_path, probe):
    marker = tmp_path / "group"
    executable = tmp_path / "exiftool"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import os\n"
        f"open({str(marker)!r}, 'w').write(str(os.getpgrp()))\n"
        "print('12.34')\n"
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    if probe:
        _probe_exiftool(str(executable))
    else:
        ExifToolBackend(tmp_path, executable=str(executable))._run([])
    assert int(marker.read_text()) != os.getpgrp()
