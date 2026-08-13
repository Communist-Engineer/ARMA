"""Shell-free subprocess execution with explicit POSIX resource ceilings."""

from __future__ import annotations

import ctypes
import errno
import os
import resource
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from amra.domain.errors import ExecutionFailure, InvariantViolation
from amra.ports.execution import ProcessResult, ResourceLimits


class LocalProcessExecutor:
    """Execute argument arrays in a bounded process group with a minimal environment."""

    @staticmethod
    def _deny_network() -> None:
        """Install a seccomp filter that denies creation of socket endpoints."""

        class SockFilter(ctypes.Structure):
            _fields_ = [
                ("code", ctypes.c_ushort),
                ("jt", ctypes.c_ubyte),
                ("jf", ctypes.c_ubyte),
                ("k", ctypes.c_uint32),
            ]

        class SockFprog(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ushort), ("filter", ctypes.POINTER(SockFilter))]

        machine = os.uname().machine
        socket_syscalls = {"x86_64": (41, 53), "aarch64": (198, 199)}.get(machine)
        if socket_syscalls is None:
            raise InvariantViolation(
                f"network-denial filter lacks an audited mapping for {machine}"
            )
        socket_call, socketpair_call = socket_syscalls
        deny = 0x00050000 | errno.EPERM
        allow = 0x7FFF0000
        instructions = (SockFilter * 6)(
            SockFilter(0x20, 0, 0, 0),  # load seccomp_data.nr
            SockFilter(0x15, 0, 1, socket_call),
            SockFilter(0x06, 0, 0, deny),
            SockFilter(0x15, 0, 1, socketpair_call),
            SockFilter(0x06, 0, 0, deny),
            SockFilter(0x06, 0, 0, allow),
        )
        program = SockFprog(len(instructions), instructions)
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
            raise OSError(ctypes.get_errno(), "PR_SET_NO_NEW_PRIVS failed")
        if libc.prctl(22, 2, ctypes.byref(program)) != 0:  # PR_SET_SECCOMP, FILTER
            raise OSError(ctypes.get_errno(), "PR_SET_SECCOMP failed")

    @staticmethod
    def _limit_process(limits: ResourceLimits) -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (limits.memory_bytes, limits.memory_bytes))
        resource.setrlimit(resource.RLIMIT_NPROC, (limits.process_count, limits.process_count))
        resource.setrlimit(resource.RLIMIT_FSIZE, (limits.file_size_bytes, limits.file_size_bytes))
        LocalProcessExecutor._deny_network()
        os.umask(0o077)

    def execute(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        limits: ResourceLimits,
        environment: Mapping[str, str] | None = None,
    ) -> ProcessResult:
        if not argv or any("\x00" in argument for argument in argv):
            raise InvariantViolation("execution requires a nonempty NUL-free argument array")
        normalized = tuple(str(argument) for argument in argv)
        clean_environment = {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "TZ": "UTC",
        }
        if environment:
            clean_environment.update(environment)
        before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        started = time.monotonic()
        process = subprocess.Popen(  # noqa: S603 - argv remains explicit and shell-free
            normalized,
            cwd=cwd,
            env=clean_environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=True,
            preexec_fn=lambda: self._limit_process(limits),
        )
        try:
            stdout, stderr = process.communicate(timeout=limits.wall_seconds)
        except subprocess.TimeoutExpired as error:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
            raise ExecutionFailure(
                f"process exceeded wall-time limit of {limits.wall_seconds} seconds"
            ) from error
        elapsed = time.monotonic() - started
        if len(stdout) + len(stderr) > limits.output_bytes:
            raise ExecutionFailure(
                f"process output exceeded {limits.output_bytes} bytes after bounded execution"
            )
        after = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        peak_bytes = max(0, after - before) * 1024
        return ProcessResult(
            argv=normalized,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            wall_time_seconds=elapsed,
            peak_memory_bytes=peak_bytes,
        )
