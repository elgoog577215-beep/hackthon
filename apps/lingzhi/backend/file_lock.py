"""Advisory file locks for Linux deployment and Windows local development."""
from __future__ import annotations

import errno
import os
import time

if os.name != "nt":
    from fcntl import LOCK_EX, LOCK_NB, LOCK_SH, LOCK_UN, flock
else:
    import msvcrt

    LOCK_SH, LOCK_EX, LOCK_NB, LOCK_UN = 1, 2, 4, 8

    def flock(file, operation: int) -> None:
        """Lock byte zero; every cooperating writer uses the same lock region.

        Windows supports locking beyond EOF, so empty lock files need no write.
        Preserve the caller's file position, and wait until acquisition for EX.
        """
        descriptor = file if isinstance(file, int) else file.fileno()
        position = os.lseek(descriptor, 0, os.SEEK_CUR)
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            if operation == LOCK_UN:
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                return
            if operation & ~(LOCK_EX | LOCK_SH | LOCK_NB) or not operation & (LOCK_EX | LOCK_SH):
                raise ValueError("Unsupported file lock operation")
            mode = msvcrt.LK_NBRLCK if operation & LOCK_SH else msvcrt.LK_NBLCK
            while True:
                try:
                    msvcrt.locking(descriptor, mode, 1)
                    return
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK} or operation & LOCK_NB:
                        raise
                    time.sleep(0.05)
        finally:
            os.lseek(descriptor, position, os.SEEK_SET)
