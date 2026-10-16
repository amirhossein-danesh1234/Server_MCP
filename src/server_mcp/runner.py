"""Structured subprocess execution. No shell, no user-supplied executable paths."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def execute(argv: list[str], *, cwd: Path | None = None,
            timeout: int = 20, output_limit: int = 12000) -> dict:
    if not argv or any(not isinstance(arg, str) or "\x00" in arg for arg in argv):
        raise ValueError("Invalid argv")
    if not 1 <= timeout <= 180:
        raise ValueError("Timeout outside 1..180 seconds")
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "HOME": "/nonexistent",
        "GIT_TERMINAL_PROMPT": "0",
    }
    try:
        result = subprocess.run(
            argv, cwd=str(cwd) if cwd else None, env=env,
            stdin=subprocess.DEVNULL, capture_output=True,
            text=True, errors="replace", timeout=timeout,
            shell=False, check=False,
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout[:output_limit],
            "stderr": result.stderr[:output_limit],
            "truncated": len(result.stdout) > output_limit or len(result.stderr) > output_limit,
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "stdout":"", "stderr":"Timeout reached", "timed_out": True}
    except FileNotFoundError:
        return {"exit_code": 127, "stdout":"", "stderr":"Executable unavailable"}
