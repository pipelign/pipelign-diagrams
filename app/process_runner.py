"""Bounded engine execution within the deployment's container boundary."""

import os
import selectors
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .limits import (
    ENGINE_TIMEOUT_SECONDS,
    MAX_DIAGNOSTIC_BYTES,
    MAX_OUTPUT_BYTES,
    RenderPolicyError,
)


def run_engine(command, *, source=b"", cwd=None, timeout=ENGINE_TIMEOUT_SECONDS):
    """Run one command without inheriting API credentials or unbounded pipes."""
    if os.name != "posix":
        raise RenderPolicyError(
            "engine_unavailable", "Rendering requires the Linux container.", 503
        )
    with tempfile.TemporaryDirectory(prefix="diagram-engine-") as scratch:
        workdir = Path(cwd or scratch)
        environment = {
            "PATH": "/app/.venv/bin:/opt/mermaid-cli/bin:/usr/local/bin:/usr/bin:/bin",
            "HOME": scratch,
            "TMPDIR": scratch,
            "LANG": "C.UTF-8",
        }
        # prlimit avoids preexec_fn, which is unsafe in the API's worker threads.
        bounded = [
            sys.executable,
            "-m",
            "app.engine_process",
            "/usr/bin/prlimit",
            f"--fsize={MAX_OUTPUT_BYTES}",
            f"--cpu={ENGINE_TIMEOUT_SECONDS}",
            "--nofile=256",
            "--nproc=256",
            "--",
            *command,
        ]
        with tempfile.TemporaryFile() as stdin:
            stdin.write(source)
            stdin.seek(0)
            try:
                process = subprocess.Popen(
                    bounded,
                    stdin=stdin,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=workdir,
                    env=environment,
                    start_new_session=True,
                )
            except OSError:
                raise RenderPolicyError(
                    "engine_unavailable", "The rendering engine is unavailable.", 503
                ) from None
            output, diagnostics = bytearray(), bytearray()
            deadline = time.monotonic() + min(float(timeout), ENGINE_TIMEOUT_SECONDS)
            try:
                with selectors.DefaultSelector() as selector:
                    for stream, buffer, maximum in (
                        (process.stdout, output, MAX_OUTPUT_BYTES),
                        (process.stderr, diagnostics, MAX_DIAGNOSTIC_BYTES),
                    ):
                        os.set_blocking(stream.fileno(), False)
                        selector.register(
                            stream, selectors.EVENT_READ, (buffer, maximum)
                        )
                    while selector.get_map():
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise RenderPolicyError(
                                "engine_timeout", "The rendering engine timed out.", 504
                            )
                        for key, _ in selector.select(min(remaining, 0.1)):
                            chunk = os.read(key.fd, 16_384)
                            if not chunk:
                                selector.unregister(key.fileobj)
                                continue
                            buffer, maximum = key.data
                            if len(buffer) + len(chunk) > maximum:
                                raise RenderPolicyError(
                                    "resource_limit",
                                    "Rendering exceeded an output limit.",
                                    413,
                                )
                            buffer.extend(chunk)
                    try:
                        returncode = process.wait(
                            timeout=max(0.001, deadline - time.monotonic())
                        )
                    except subprocess.TimeoutExpired:
                        raise RenderPolicyError(
                            "engine_timeout", "The rendering engine timed out.", 504
                        ) from None
            finally:
                # Let the subreaper collect detached Chromium children before
                # removing workspaces. This is cleanup, not request isolation.
                process.terminate() if process.poll() is None else None
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()
            if returncode in {
                -signal.SIGXFSZ,
                -signal.SIGXCPU,
                128 + signal.SIGXFSZ,
                128 + signal.SIGXCPU,
            }:
                raise RenderPolicyError(
                    "resource_limit", "Rendering exceeded a resource limit.", 413
                )
            return subprocess.CompletedProcess(
                command, returncode, bytes(output), bytes(diagnostics)
            )
