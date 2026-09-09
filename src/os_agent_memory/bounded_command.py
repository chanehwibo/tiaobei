"""Bounded pipes for trusted local engine clients, not a process sandbox."""
from __future__ import annotations

import math
import subprocess
from threading import Event, Thread
import time


class CommandFailure(RuntimeError):
    """A public error code without command output, prompts or credentials."""


def run_bounded(argv, *, input=None, timeout=60, max_stdout=64 * 1024,
                max_stderr=16 * 1024, check=True):
    if (not isinstance(argv, list) or not argv
            or not all(isinstance(arg, str) and arg and "\x00" not in arg for arg in argv)
            or type(check) is not bool
            or type(timeout) not in (int, float) or not math.isfinite(timeout)
            or not 0 < timeout <= 600
            or any(type(n) is not int or not 0 < n <= 4 * 1024 * 1024
                   for n in (max_stdout, max_stderr))):
        raise ValueError("invalid command or pipe budget")
    payload = b"" if input is None else input.encode("utf-8")
    if len(payload) > 4 * 1024 * 1024:
        raise ValueError("command input exceeds budget")
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, bufsize=0)
    overflow = Event()
    outputs = [bytearray(), bytearray()]

    def drain(stream, buffer, maximum):
        try:
            while chunk := stream.read(4096):
                available = maximum - len(buffer)
                buffer.extend(chunk[:available])
                if len(chunk) > available:
                    overflow.set()
                    break
        finally:
            stream.close()

    def feed():
        try:
            view = memoryview(payload)
            while view:
                written = process.stdin.write(view)
                if not written:
                    break
                view = view[written:]
        except (BrokenPipeError, OSError):
            pass
        finally:
            process.stdin.close()

    threads = [
        Thread(target=drain, args=(process.stdout, outputs[0], max_stdout), daemon=True),
        Thread(target=drain, args=(process.stderr, outputs[1], max_stderr), daemon=True),
        Thread(target=feed, daemon=True),
    ]
    deadline = time.monotonic() + timeout
    for thread in threads:
        thread.start()
    failure = None
    try:
        while process.poll() is None:
            if overflow.wait(min(.01, max(0, deadline - time.monotonic()))):
                failure = "command_output_limit"
                break
            if time.monotonic() >= deadline:
                failure = "command_timeout"
                break
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=1)
    if overflow.is_set():
        failure = "command_output_limit"
    if any(thread.is_alive() for thread in threads):
        failure = failure or "command_pipe_not_closed"
    if failure or (check and process.returncode):
        raise CommandFailure(failure or "command_nonzero_exit")
    try:
        stdout = outputs[0].decode("utf-8")
    except UnicodeDecodeError:
        raise CommandFailure("command_invalid_utf8") from None
    return subprocess.CompletedProcess(argv, process.returncode, stdout=stdout,
                                       stderr=outputs[1].decode("utf-8", errors="replace"))
