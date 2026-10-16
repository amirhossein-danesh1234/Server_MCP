"""Fail-closed TOML configuration for the host-resident MCP agent."""
from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    issuer: str
    resource: str
    jwks_url: str
    host: str
    port: int
    roots: dict[str, Path]
    services: frozenset[str]
    containers: frozenset[str]
    runbooks: dict[str, tuple[str, ...]]
    commands_cwd: dict[str, Path]
    state_dir: Path
    operate_enabled: bool
    workspace_write_enabled: bool
    max_read_bytes: int = 262144
    max_write_bytes: int = 262144
    max_output_chars: int = 12000


def load_settings(path: str | None = None) -> Settings:
    target = Path(path or os.environ.get("SERVER_MCP_CONFIG", "/etc/server-mcp/config.toml"))
    with target.open("rb") as f:
        cfg = tomllib.load(f)
    auth = cfg.get("auth", {})
    server = cfg.get("server", {})
    permissions = cfg.get("permissions", {})
    required = ("issuer", "resource", "jwks_url")
    for field in required:
        if not auth.get(field) or not str(auth[field]).startswith("https://"):
            raise ValueError(f"auth.{field} is required and must be HTTPS")
    if not str(auth["resource"]).endswith("/mcp"):
        raise ValueError("auth.resource must be the public HTTPS MCP URL ending in /mcp")
    roots = {}
    for name, location in cfg.get("workspaces", {}).items():
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,63}", name):
            raise ValueError("invalid workspace name")
        root = Path(location).resolve(strict=True)
        if not root.is_dir() or str(root) == "/":
            raise ValueError(f"workspace {name} must be a directory other than /")
        roots[name] = root
    if not roots:
        raise ValueError("At least one workspace is required")
    services = frozenset(cfg.get("services", {}).get("allow", []))
    containers = frozenset(cfg.get("containers", {}).get("allow", []))
    for collection in (services, containers):
        if any(not isinstance(n, str) or not re.fullmatch(r"[a-zA-Z0-9_.@-]{1,120}", n) for n in collection):
            raise ValueError("invalid allowed service/container name")
    runbooks = {}
    cwd = {}
    for name, value in cfg.get("runbooks", {}).items():
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,63}", name):
            raise ValueError("invalid runbook name")
        argv = value.get("argv", [])
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
            raise ValueError(f"runbook {name} must have argv list")
        work = value.get("workspace")
        if work not in roots:
            raise ValueError(f"runbook {name} must reference configured workspace")
        runbooks[name] = tuple(argv)
        cwd[name] = roots[work]
    state_dir = Path(server.get("state_dir", "/var/lib/server-mcp")).resolve()
    if not state_dir.is_absolute() or str(state_dir) == "/":
        raise ValueError("invalid state directory")
    host = str(server.get("host", "127.0.0.1"))
    if host not in ("127.0.0.1", "::1"):
        raise ValueError("Bind to loopback only; publish through authenticated reverse proxy/tunnel")
    port = int(server.get("port", 8765))
    if not 1024 <= port <= 65535:
        raise ValueError("port must be >=1024 and <=65535")
    return Settings(
        issuer=str(auth["issuer"]).rstrip("/"),
        resource=str(auth["resource"]),
        jwks_url=str(auth["jwks_url"]),
        host=host, port=port, roots=roots,
        services=services, containers=containers,
        runbooks=runbooks, commands_cwd=cwd,
        state_dir=state_dir,
        operate_enabled=permissions.get("operate_enabled", False) is True,
        workspace_write_enabled=permissions.get("workspace_write_enabled", False) is True,
    )
