"""Collect ordinary engine descendants, including Chromium's detached processes.

This supervisor creates no namespaces and provides no security boundary between
requests. Network and credential restrictions belong to the container deployment.
"""

import ctypes
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def children():
    return [
        int(pid)
        for pid in Path(f"/proc/self/task/{os.getpid()}/children").read_text().split()
    ]


def cleanup():
    # Killing a direct child reparents its remaining descendants to this
    # subreaper. Repeat until all descendants have been reaped.
    while True:
        for pid in children():
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if not pid:
            time.sleep(0.01)


def terminate(signum, frame):
    raise SystemExit(128 + signum)


def main():
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "Cannot enable engine process cleanup")
    signal.signal(signal.SIGTERM, terminate)
    try:
        result = subprocess.Popen(sys.argv[1:]).wait()
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        cleanup()
    raise SystemExit(result if result >= 0 else 128 - result)


if __name__ == "__main__":
    main()
