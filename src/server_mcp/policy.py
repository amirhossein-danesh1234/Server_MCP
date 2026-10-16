"""Workspace boundaries, secret exclusions, and optimistic file writes."""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

DENIED_PARTS = {
    ".ssh", ".aws", ".kube", ".gnupg", ".terraform", ".env", ".npmrc",
    ".netrc", "id_rsa", "id_ed25519", "authorized_keys", "credentials",
    "private_key", "secrets", "secret", ".git-credentials",
}
DENIED_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}


def within_workspace(root: Path, relative: str, *, write: bool = False) -> Path:
    candidate = Path(relative)
    if not relative or candidate.is_absolute() or "\x00" in relative:
        raise PermissionError("Only relative workspace paths are allowed")
    if any(part in DENIED_PARTS or part.startswith(".env.") for part in candidate.parts):
        raise PermissionError("Sensitive path blocked")
    if candidate.suffix.lower() in DENIED_SUFFIXES:
        raise PermissionError("Sensitive file type blocked")
    root = root.resolve(strict=True)
    resolved = (root / candidate).resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise PermissionError("Path escapes workspace")
    if write:
        # Reject symlinks in any existing component; no silent write-through.
        node = root
        for part in candidate.parts:
            node = node / part
            if node.is_symlink():
                raise PermissionError("Writing through symlinks is prohibited")
    return resolved


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(root: Path, relative: str, text: str, expected_sha256: str, limit: int) -> dict:
    target = within_workspace(root, relative, write=True)
    content = text.encode("utf-8")
    if len(content) > limit:
        raise ValueError("File exceeds write size limit")
    if not target.parent.is_dir():
        raise FileNotFoundError("Parent directory must already exist")
    if target.exists():
        if not target.is_file():
            raise ValueError("Target is not a regular file")
        current = target.read_bytes()
        if len(current) > limit:
            raise ValueError("Existing file too large for safe edit")
        if digest(current) != expected_sha256:
            raise RuntimeError("Conflict: expected_sha256 differs from current file; re-read first")
    elif expected_sha256 != "NEW":
        raise RuntimeError("For new files expected_sha256 must equal NEW")
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix=".server-mcp-", text=False)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return {"path":relative, "sha256":digest(content), "bytes":len(content)}
