"""Recoverable publication of stage-owned sidecar files.

Callers must pass a sidecar path, never the source image path.
"""

import os
import stat
import tempfile
from pathlib import Path


class ArtifactError(Exception):
    def __init__(self, category):
        self.category = category
        super().__init__(category)


class ArtifactService:
    def __init__(self, retention="remove", checkpoint=None):
        if retention not in ("remove", "retain"):
            raise ValueError("invalid backup retention")
        self.retention = retention
        self.checkpoint = checkpoint

    def _point(self, name):
        if self.checkpoint:
            self.checkpoint(name)

    def _validate(self, validator, data, category):
        try:
            valid = validator(data)
        except Exception:  # noqa: BLE001 - validators are an untrusted boundary
            raise ArtifactError(category) from None
        if not valid:
            raise ArtifactError(category)

    def _read(self, path):
        with path.open("rb") as stream:
            data = stream.read()
            info = os.fstat(stream.fileno())
        return data, stat.S_IMODE(info.st_mode), (info.st_dev, info.st_ino)

    def _stage(self, dest, payload, mode, kind, owned):
        self._point(kind + "_create")
        fd, name = tempfile.mkstemp(
            prefix=f".{dest.name}.image-clarus-", suffix=".tmp", dir=dest.parent
        )
        path = Path(name)
        owned.add(path)
        with os.fdopen(fd, "wb") as stream:
            self._point(kind + "_write")
            stream.write(payload)
            self._point(kind + "_mode")
            os.fchmod(stream.fileno(), mode)
            self._point(kind + "_fsync")
            stream.flush()
            os.fsync(stream.fileno())
        self._point("backup_verify" if kind == "backup" else kind + "_read")
        data, actual_mode, identity = self._read(path)
        if data != payload or actual_mode != mode:
            raise ArtifactError("file_io")
        return path, data, identity

    def _cleanup(self, owned):
        failed = False
        for path in owned:
            try:
                if path.exists():
                    self._point("temp_cleanup")
                    path.unlink()
            except OSError:
                failed = True
        if failed:
            raise OSError("temporary cleanup failed")

    def _remove_backup(self, backup):
        if self.retention == "remove" and backup.exists():
            self._point("backup_remove")
            backup.unlink()

    def write(
        self, destination, payload, validator, validation_category="invalid_artifact"
    ):
        destination = Path(destination)
        backup = Path(str(destination) + ".bak")
        owned = set()
        try:
            try:
                self._point("backup_read")
                try:
                    original, mode, _ = self._read(destination)
                except FileNotFoundError:
                    original, mode = None, 0o600
                staged, data, identity = self._stage(
                    destination, payload, mode, "output", owned
                )
                self._point("output_validate")
                self._validate(validator, data, validation_category)
                if original is not None:
                    copy, _, _ = self._stage(backup, original, mode, "backup", owned)
                    self._point("backup_replace")
                    os.replace(copy, backup)
                try:
                    self._point("destination_replace")
                    os.replace(staged, destination)
                except OSError:
                    if original is not None and not destination.exists():
                        try:
                            ArtifactService("retain", self.checkpoint).recover(
                                destination, lambda data: data == original
                            )
                        except ArtifactError:
                            pass  # Preserve the backup and the original failure.
                    raise
                self._point("destination_read")
                data, actual_mode, observed = self._read(destination)
                if observed == identity and (data != payload or actual_mode != mode):
                    raise ArtifactError("file_io")
                self._point("destination_validate")
                self._validate(validator, data, validation_category)
                self._remove_backup(backup)
            finally:
                self._cleanup(owned)
        except ArtifactError:
            raise
        except OSError:
            raise ArtifactError("file_io") from None

    def recover(self, destination, validator, validation_category="invalid_artifact"):
        destination = Path(destination)
        backup = Path(str(destination) + ".bak")
        owned = set()
        try:
            try:
                self._point("destination_read")
                try:
                    data, mode, _ = self._read(destination)
                except FileNotFoundError:
                    self._point("recovery_backup_read")
                    try:
                        data, mode, _ = self._read(backup)
                    except FileNotFoundError:
                        return False
                    staged, _, identity = self._stage(
                        destination, data, mode, "recovery", owned
                    )
                    self._point("recovery_replace")
                    os.replace(staged, destination)
                    self._point("destination_read")
                    restored, restored_mode, observed = self._read(destination)
                    if observed == identity and (
                        restored != data or restored_mode != mode
                    ):
                        raise ArtifactError("file_io")
                    data = restored
                self._point("destination_validate")
                self._validate(validator, data, validation_category)
                self._remove_backup(backup)
                return True
            finally:
                self._cleanup(owned)
        except ArtifactError:
            raise
        except OSError:
            raise ArtifactError("file_io") from None
