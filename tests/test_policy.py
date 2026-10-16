import hashlib
from pathlib import Path

import pytest

from server_mcp.policy import atomic_write, within_workspace


def test_workspace_escape_and_sensitive_paths(tmp_path: Path):
    (tmp_path / "safe").mkdir()
    assert within_workspace(tmp_path, "safe/file.txt") == tmp_path / "safe/file.txt"
    for name in ("../etc/passwd", "/etc/passwd", ".env", "safe/.ssh/key", "safe/id_rsa", "config.pem"):
        with pytest.raises(PermissionError):
            within_workspace(tmp_path, name)
    (tmp_path / "outside").symlink_to("/etc", target_is_directory=True)
    with pytest.raises(PermissionError):
        within_workspace(tmp_path, "outside/passwd", write=True)


def test_atomic_compare_and_swap(tmp_path: Path):
    result = atomic_write(tmp_path, "code.py", "print(1)", "NEW", 1024)
    assert result["sha256"] == hashlib.sha256(b"print(1)").hexdigest()
    with pytest.raises(RuntimeError, match="Conflict"):
        atomic_write(tmp_path, "code.py", "print(2)", "0" * 64, 1024)
    changed = atomic_write(tmp_path, "code.py", "print(2)", result["sha256"], 1024)
    assert changed["bytes"] == 8
    assert (tmp_path / "code.py").read_text() == "print(2)"
    assert (tmp_path / "code.py").stat().st_mode & 0o777 == 0o600


def test_symlink_write_rejected(tmp_path: Path):
    (tmp_path / "linked.txt").symlink_to(tmp_path / "actual.txt")
    with pytest.raises(PermissionError):
        atomic_write(tmp_path, "linked.txt", "no", "NEW", 100)
