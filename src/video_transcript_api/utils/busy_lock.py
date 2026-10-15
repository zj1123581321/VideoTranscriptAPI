"""Deploy busy lock: each in-flight transcription task holds a shared flock.

The deploy script takes an exclusive flock on the same bind-mounted file.
This module only does non-blocking shared admission. A False return means
the caller must not create a task row. If the lock directory or flock is
unavailable (old environments without the mount), the instance disables
itself, logs one grep-able BUSY LOCK WARN, and admission always succeeds.
"""
from __future__ import annotations

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
    mark the instance disabled and return True so old environments keep
    serving traffic.
    """

    _warned_paths: set[str] = set()

    def __init__(self, path: str = BUSY_LOCK_PATH):
        self.path = path
        self._fd: Optional[int] = None
        self._disabled = False

    @property
    def disabled(self) -> bool:
        return self._disabled

    def _warn(self, message: str) -> None:
        if self.path in self._warned_paths:
            return
        self._warned_paths.add(self.path)
        logger.warning("BUSY LOCK WARN: " + message)

    def acquire(self) -> bool:
        """Non-blocking shared flock. False means deploy holds exclusive."""
        if self._disabled:
            return True
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
                    f"busy lock path {self.path} is not a regular file; "
                    "proceeding without busy-lock protection"
                )
                return True
        except OSError as exc:
            self._disabled = True
            self._warn(
                f"cannot initialize {self.path} ({exc}); "
                "proceeding without busy-lock protection"
            )
            return True

        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                self._fd = fd
                return True
            except BlockingIOError:
                os.close(fd)
                return False
            except OSError as exc:
                self._disabled = True
                self._warn(
                    f"cannot acquire {self.path} ({exc}); "
                    "proceeding without busy-lock protection"
                )
                os.close(fd)
                return True
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
    return True


def release_for_task(task_id: str) -> None:
    """Close the fd held for task_id. Unknown ids are a no-op."""
    with _held_locks_guard:
        lock = _held_locks.pop(task_id, None)
    if lock is not None:
        lock.release()
