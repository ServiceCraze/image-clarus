"""Recoverable publication of stage-owned sidecar files.

Callers must pass a sidecar path, never the source image path.
"""

import errno
import os
import stat
import sys
import tempfile
from contextvars import ContextVar
from pathlib import Path


def _privacy_warning():
    try:
        print(
            "image-clarus: privacy warning: file permissions could not be preserved; "
            "access may be broader than intended (including via ACLs). "
            "The attempted operation may still fail.",
            file=sys.stderr,
        )
    except (OSError, ValueError):
        pass


class ArtifactError(Exception):
    def __init__(self, category, checkpoint=None, error_number=None):
        self.category = category
        self.checkpoint = checkpoint
        self.error_number = error_number if type(error_number) is int else None
        detail = category
        if checkpoint:
            detail += f"; checkpoint={checkpoint}"
        if self.error_number is not None:
            detail += f"; errno={self.error_number}"
        super().__init__(detail)


class ArtifactService:
    def __init__(self, retention="remove", checkpoint=None):
        if retention not in ("remove", "retain"):
            raise ValueError("invalid backup retention")
        self.retention = retention
        self.checkpoint = checkpoint
        self._last_point = ContextVar("artifact_checkpoint", default=None)

    def _point(self, name):
        if name != "temp_cleanup" or sys.exc_info()[0] is None:
            self._last_point.set(name)
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

    def _mode_capable(self, dest, kind, owned):
        # Probe only an empty sibling, before either output or backup bytes exist.
        self._last_point.set(kind + "_mode")
        fd, name = tempfile.mkstemp(
            prefix=f".{dest.name}.image-clarus-", suffix=".tmp", dir=dest.parent
        )
        path = Path(name)
        owned.add(path)
        try:
            with os.fdopen(fd, "wb") as stream:
                chmod = getattr(os, "fchmod", None)
                if chmod is None:
                    return False
                observed = []
                for requested in (0o600, 0o644):
                    try:
                        chmod(stream.fileno(), requested)
                    except ValueError:
                        raise OSError(errno.EINVAL, "invalid mode operation") from None
                    except OSError as error:
                        if error.errno not in (
                            errno.ENOTSUP,
                            errno.EOPNOTSUPP,
                            errno.ENOSYS,
                        ):
                            raise
                        return False
                    observed.append(stat.S_IMODE(os.fstat(stream.fileno()).st_mode))
                return observed == [0o600, 0o644]
        finally:
            self._cleanup({path}, probe=True)
            if not path.exists():
                owned.discard(path)

    def _stage(self, dest, payload, mode, kind, owned, warned):
        capable = self._mode_capable(dest, kind, owned)
        if not capable and not warned:
            _privacy_warning()
            warned.append(True)
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
            chmod = getattr(os, "fchmod", None)
            if chmod is not None:
                try:
                    chmod(stream.fileno(), mode)
                except ValueError:
                    raise OSError(errno.EINVAL, "invalid mode operation") from None
                except OSError as error:
                    if capable or error.errno not in (
                        errno.ENOTSUP,
                        errno.EOPNOTSUPP,
                        errno.ENOSYS,
                    ):
                        raise
            self._point(kind + "_fsync")
            stream.flush()
            os.fsync(stream.fileno())
        self._point("backup_verify" if kind == "backup" else kind + "_read")
        data, actual_mode, identity = self._read(path)
        if data != payload:
            raise ArtifactError("file_io")
        if capable and actual_mode != mode:
            raise ArtifactError("file_io", kind + "_mode")
        return path, data, identity, actual_mode

    def _cleanup(self, owned, *, probe=False):
        primary = sys.exc_info()[0] is not None
        failure = None
        for path in owned:
            try:
                if path.exists():
                    if not probe:
                        self._point("temp_cleanup")
                    path.unlink()
            except OSError as error:
                if failure is None:
                    failure = error
        if failure is not None and not primary:
            raise failure

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
        warned = []
        try:
            try:
                self._point("backup_read")
                try:
                    original, mode, _ = self._read(destination)
                except FileNotFoundError:
                    original, mode = None, 0o600
                staged, data, identity, staged_mode = self._stage(
                    destination, payload, mode, "output", owned, warned
                )
                self._point("output_validate")
                self._validate(validator, data, validation_category)
                if original is not None:
                    copy, _, _, _ = self._stage(
                        backup, original, mode, "backup", owned, warned
                    )
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
                if observed == identity and (
                    data != payload or actual_mode != staged_mode
                ):
                    raise ArtifactError("file_io")
                self._point("destination_validate")
                self._validate(validator, data, validation_category)
                self._remove_backup(backup)
            finally:
                self._cleanup(owned)
        except ArtifactError:
            raise
        except OSError as error:
            raise ArtifactError(
                "file_io", self._last_point.get(), error.errno
            ) from None

    def recover(
        self,
        destination,
        validator,
        validation_category="invalid_artifact",
        *,
        retain_backup=False,
    ):
        destination = Path(destination)
        backup = Path(str(destination) + ".bak")
        owned = set()
        warned = []
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
                    self._validate(validator, data, validation_category)
                    staged, _, identity, staged_mode = self._stage(
                        destination, data, mode, "recovery", owned, warned
                    )
                    self._point("recovery_replace")
                    os.replace(staged, destination)
                    self._point("destination_read")
                    restored, restored_mode, observed = self._read(destination)
                    if observed == identity and (
                        restored != data or restored_mode != staged_mode
                    ):
                        raise ArtifactError("file_io")
                    data = restored
                self._point("destination_validate")
                self._validate(validator, data, validation_category)
                if not retain_backup:
                    self._remove_backup(backup)
                return True
            finally:
                self._cleanup(owned)
        except ArtifactError:
            raise
        except OSError as error:
            raise ArtifactError(
                "file_io", self._last_point.get(), error.errno
            ) from None
