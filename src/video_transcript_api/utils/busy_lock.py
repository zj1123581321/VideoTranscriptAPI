"""Deploy busy lock: each in-flight transcription task holds a shared flock.

The deploy script takes an exclusive flock on the same bind-mounted file.
This module only does non-blocking shared admission. A False return means
the caller must not create a task row. Fail-closed: when the lock directory,
the lock file, or flock itself is unavailable (old environments without the
mount, permission problems), the instance disables itself, logs one grep-able
BUSY LOCK WARN, and admission DENIES new tasks — a broken lock must never
degrade into an unprotected admission path (deploy/task mutual exclusion
would silently vanish).
"""
from __future__ import annotations

import errno
import fcntl
import os
import threading
from typing import Optional

from .logging import setup_logger

logger = setup_logger("busy_lock")

BUSY_LOCK_PATH = "/app/.deploy-state/busy.lock"


class BusyLock:
    """One shared flock fd covering a single task lifetime.

    ``acquire()`` is the production admission entry: if an exclusive holder
    exists it returns False immediately. Init or flock infrastructure errors
    also mark the instance disabled and return False — admission fails
    closed (the caller answers 503) instead of serving without mutual
    exclusion.
    """

    _warned_paths: set[str] = set()

    def __init__(self, path: str = BUSY_LOCK_PATH):
        self.path = path
        self._fd: Optional[int] = None
        self._disabled = False

    @property
    def disabled(self) -> bool:
        """True once a lock-infrastructure failure denied this instance."""
        return self._disabled

    def _warn(self, message: str) -> None:
        if self.path in self._warned_paths:
            return
        self._warned_paths.add(self.path)
        logger.warning("BUSY LOCK WARN: " + message)

    @staticmethod
    def _os_error_reason(exc: OSError) -> str:
        """Coarse mount/permission bucket for the one-shot warn line."""
        if exc.errno in (errno.EACCES, errno.EPERM):
            return "permission denied"
        return "deploy-state mount/filesystem problem"

    def acquire(self) -> bool:
        """Non-blocking shared flock admission.

        False means denied: either the deploy holds the exclusive lock, or
        the lock infrastructure is unavailable (fail-closed).
        """
        if self._disabled:
            return False
        parent = os.path.dirname(self.path) or "."
        try:
            existed = os.path.isdir(parent)
            file_existed = os.path.exists(self.path)
            os.makedirs(parent, mode=0o755, exist_ok=True)
            if not existed:
                self._warn(
                    f"directory {parent} was missing; created it; deployment "
                    "admission may be unprotected until the host mount is fixed"
                )
            # Read-only fd is enough for flock. Mode 0666 plus umask yields a
            # host-deploy-user-readable file; a 0600 root-created file would
            # block the host exclusive flock.
            fd = os.open(self.path, os.O_CREAT | os.O_RDONLY, 0o666)
            if not file_existed:
                self._warn(
                    f"lock file {self.path} was missing; created it; verify the "
                    "host deploy-state bind mount before enabling caller gate"
                )
            if not os.path.isfile(self.path):
                os.close(fd)
                self._disabled = True
                self._warn(
                    f"busy lock path {self.path} is not a regular file "
                    "(deploy-state mount misconfigured); "
                    "admission now denies new tasks until the mount is fixed"
                )
                return False
        except OSError as exc:
            self._disabled = True
            self._warn(
                f"cannot initialize {self.path} "
                f"({self._os_error_reason(exc)}: {exc}); "
                "admission now denies new tasks until it is fixed"
            )
            return False

        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                self._fd = fd
                # Fail-closed admission: the shared flock above is the only
                # allow path; a disabled instance can never admit a task.
                return not self._disabled
            except BlockingIOError:
                os.close(fd)
                return False
            except OSError as exc:
                self._disabled = True
                self._warn(
                    f"cannot acquire {self.path} "
                    f"({self._os_error_reason(exc)}: {exc}); "
                    "admission now denies new tasks until it is fixed"
                )
                os.close(fd)
                return False
        except BaseException:
            os.close(fd)
            raise

    def release(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


_held_locks: dict[str, BusyLock] = {}
_held_locks_guard = threading.Lock()


def acquire_for_task(task_id: str, path: str | None = None) -> bool:
    """Open a dedicated fd and hold shared flock until release_for_task."""
    lock = BusyLock(path or BUSY_LOCK_PATH)
    if not lock.acquire():
        return False
    with _held_locks_guard:
        previous = _held_locks.pop(task_id, None)
        _held_locks[task_id] = lock
    if previous is not None:
        previous.release()
    # Held shared flock on a healthy lock instance is the only allow path.
    return not lock.disabled


def release_for_task(task_id: str) -> None:
    """Close the fd held for task_id. Unknown ids are a no-op."""
    with _held_locks_guard:
        lock = _held_locks.pop(task_id, None)
    if lock is not None:
        lock.release()
