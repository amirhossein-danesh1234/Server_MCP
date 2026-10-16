"""ChatGPT-first, OAuth-protected Streamable HTTP MCP server for Linux hosts."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import re
from pathlib import Path

import psutil
from mcp.server import MCPServer
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from . import __version__
from .approvals import audit, consume, request
from .auth import OIDCTokenVerifier, require_scope
from .policy import atomic_write, digest, within_workspace
from .runner import execute
from .settings import Settings, load_settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
REDACTIONS = [
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[a-z0-9._~+/-]+"),
    re.compile(r"(?i)((?:api[_-]?key|password|secret|token)\s*[=:]\s*)\S+"),
]


def clean(value: str) -> str:
    for pattern in REDACTIONS:
        value = pattern.sub(r"\1[REDACTED]", value)
    return value


def output(result: dict) -> dict:
    for field in ("stdout", "stderr"):
        if field in result:
            result[field] = clean(result[field])
    return result


def create_server(cfg: Settings) -> MCPServer:
    mcp = MCPServer(
        "Server MCP Agent",
        instructions=(
            "Manage a Linux server using typed operations. Read operations require server:read; "
            "workspace writes require server:write; restarts and configured runbooks require "
            "server:operate plus a local human approval via server-mcp-approve. "
            "Never request root secrets or assume an operation succeeded before seeing the result."
        ),
        token_verifier=OIDCTokenVerifier(cfg),
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(cfg.issuer),
            resource_server_url=AnyHttpUrl(cfg.resource),
            required_scopes=["server:read"],
            validate_token_resource=True,
        ),
    )

    def workspace(name: str) -> Path:
        try:
            return cfg.roots[name]
        except KeyError:
            raise ValueError("Unknown workspace name") from None

    @mcp.tool()
    def whoami() -> dict:
        """Report the authenticated user scopes and enabled permissions."""
        actor = require_scope("server:read")
        from mcp.server.auth.middleware.auth_context import get_access_token
        token = get_access_token()
        return {
            "actor": actor,
            "scopes": token.scopes if token else [],
            "workspace_write_enabled": cfg.workspace_write_enabled,
            "operate_enabled": cfg.operate_enabled,
        }

    @mcp.tool()
    def host_status() -> dict:
        """Read CPU, memory, disk and boot health; no host modification."""
        require_scope("server:read")
        return {
            "os": platform.system(), "release": platform.release(),
            "hostname": platform.node(),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "cpu_count": psutil.cpu_count(),
            "memory": psutil.virtual_memory()._asdict(),
            "disk_root": psutil.disk_usage("/")._asdict(),
            "uptime_seconds": int(__import__("time").time() - psutil.boot_time()),
            "version": __version__,
        }

    @mcp.tool()
    def list_workspaces() -> dict:
        """List named and explicitly approved workspace roots."""
        require_scope("server:read")
        return {"workspaces": {name: str(path) for name, path in cfg.roots.items()}}

    @mcp.tool()
    def list_files(workspace_name: str, path: str = ".", limit: int = 100) -> dict:
        """List files in an allowlisted workspace without traversing secrets."""
        require_scope("server:read")
        if not 1 <= limit <= 200:
            raise ValueError("limit outside 1..200")
        root = workspace(workspace_name)
        location = root if path == "." else within_workspace(root, path)
        if not location.is_dir():
            raise ValueError("Not a directory")
        entries = []
        for p in sorted(location.iterdir()):
            try:
                rel = str(p.relative_to(root))
                within_workspace(root, rel)
                if p.is_symlink():
                    continue
                entries.append({"name": p.name, "type": "dir" if p.is_dir() else "file"})
            except (PermissionError, ValueError):
                continue
            if len(entries) >= limit:
                break
        return {"workspace": workspace_name, "path": path, "items": entries}

    @mcp.tool()
    def read_text(workspace_name: str, path: str) -> dict:
        """Read UTF-8 text and return a SHA-256 for optimistic subsequent editing."""
        require_scope("server:read")
        target = within_workspace(workspace(workspace_name), path)
        if not target.is_file() or target.is_symlink():
            raise ValueError("Only regular files may be read")
        if target.stat().st_size > cfg.max_read_bytes:
            raise ValueError("File exceeds configured read limit")
        data = target.read_bytes()
        if len(data) > cfg.max_read_bytes:
            raise ValueError("File exceeds configured read limit")
        return {"text": data.decode("utf-8"), "sha256": digest(data), "bytes": len(data)}

    @mcp.tool()
    def write_text(workspace_name: str, path: str, text: str, expected_sha256: str) -> dict:
        """Atomically replace/create a text file in an approved workspace using compare-and-swap."""
        actor = require_scope("server:write")
        if not cfg.workspace_write_enabled:
            raise PermissionError("Workspace writing is disabled in server config")
        if not re.fullmatch(r"(?:[a-f0-9]{64}|NEW)", expected_sha256):
            raise ValueError("expected_sha256 must be 64 hex characters or NEW")
        outcome = atomic_write(workspace(workspace_name), path, text, expected_sha256, cfg.max_write_bytes)
        audit(cfg, actor, "write_text", workspace_name + "/" + path, "success")
        return outcome

    @mcp.tool()
    def git_status(workspace_name: str) -> dict:
        """Show git status of an approved checkout."""
        require_scope("server:read")
        return output(execute(["git", "status", "--short", "--branch"], cwd=workspace(workspace_name)))

    @mcp.tool()
    def git_diff(workspace_name: str, staged: bool = False) -> dict:
        """Show bounded git diff of an approved checkout."""
        require_scope("server:read")
        argv = ["git", "diff", "--no-ext-diff", "--no-textconv"]
        if staged:
            argv.append("--cached")
        return output(execute(argv, cwd=workspace(workspace_name), output_limit=cfg.max_output_chars))

    @mcp.tool()
    def list_processes(limit: int = 30) -> dict:
        """List processes sorted by resident memory for diagnostics."""
        require_scope("server:read")
        if not 1 <= limit <= 100:
            raise ValueError("limit outside 1..100")
        items = []
        for proc in psutil.process_iter(["pid", "name", "username", "memory_info"]):
            try:
                info = proc.info
                items.append({
                    "pid": info["pid"], "name": info["name"], "user": info["username"],
                    "rss": info["memory_info"].rss if info["memory_info"] else 0,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return {"processes": sorted(items, key=lambda item:item["rss"], reverse=True)[:limit]}

    @mcp.tool()
    def listening_ports() -> dict:
        """Inspect listening TCP and UDP ports using ss."""
        require_scope("server:read")
        return output(execute(["ss", "-tuln"], output_limit=cfg.max_output_chars))

    @mcp.tool()
    def service_status(name: str) -> dict:
        """Get state for an allowlisted systemd service."""
        require_scope("server:read")
        if name not in cfg.services:
            raise PermissionError("Service is not on the allowlist")
        return output(execute(["systemctl", "show", name, "--no-pager",
                               "--property=Id,LoadState,ActiveState,SubState,UnitFileState"]))

    @mcp.tool()
    def service_logs(name: str, lines: int = 50) -> dict:
        """Read bounded journal logs of an allowlisted systemd service."""
        require_scope("server:read")
        if name not in cfg.services:
            raise PermissionError("Service is not on the allowlist")
        if not 1 <= lines <= 200:
            raise ValueError("lines outside 1..200")
        return output(execute(["journalctl", "-u", name, "-n", str(lines), "--no-pager",
                               "--output=short-iso"], output_limit=cfg.max_output_chars))

    @mcp.tool()
    def docker_containers() -> dict:
        """List configured Docker containers; only those names are returned."""
        require_scope("server:read")
        if not cfg.containers:
            return {"containers": [], "hint": "No containers configured"}
        result = execute(["docker", "ps", "-a", "--format", "{{json .}}"])
        if result["exit_code"] != 0:
            return output(result)
        entries = []
        for line in result["stdout"].splitlines():
            try:
                item = json.loads(line)
                if item.get("Names") in cfg.containers:
                    entries.append({"name":item["Names"],"image":item.get("Image"),
                                    "state":item.get("State"),"status":item.get("Status")})
            except (ValueError, KeyError):
                continue
        return {"containers": entries}

    @mcp.tool()
    def docker_logs(name: str, lines: int = 50) -> dict:
        """Read bounded Docker container logs; may contain sensitive application output."""
        require_scope("server:read")
        if name not in cfg.containers:
            raise PermissionError("Container is not on the allowlist")
        if not 1 <= lines <= 200:
            raise ValueError("lines outside 1..200")
        return output(execute(["docker", "logs", "--tail", str(lines), name],
                              output_limit=cfg.max_output_chars))

    @mcp.tool()
    def request_operation(kind: str, target: str) -> dict:
        """Prepare a restart or preconfigured runbook; only a local human can approve."""
        actor = require_scope("server:operate")
        if not cfg.operate_enabled:
            raise PermissionError("Operations disabled in server config")
        if kind == "service_restart" and target in cfg.services:
            pass
        elif kind == "container_restart" and target in cfg.containers:
            pass
        elif kind == "runbook" and target in cfg.runbooks:
            pass
        else:
            raise PermissionError("Unknown action or target not allowed")
        return request(cfg, actor, kind, target)

    @mcp.tool()
    def execute_approved(request_id: str) -> dict:
        """Execute an approved and unexpired one-time operation, recording an audit event."""
        actor = require_scope("server:operate")
        if not cfg.operate_enabled:
            raise PermissionError("Operations disabled in server config")
        kind, target = consume(cfg, actor, request_id)
        # Recheck allowlists after approval to defend against configuration changes.
        if kind == "service_restart" and target in cfg.services:
            argv, cwd = ["systemctl", "restart", target], None
        elif kind == "container_restart" and target in cfg.containers:
            argv, cwd = ["docker", "restart", target], None
        elif kind == "runbook" and target in cfg.runbooks:
            argv, cwd = list(cfg.runbooks[target]), cfg.commands_cwd[target]
        else:
            audit(cfg, actor, kind, target, "denied-policy-changed")
            raise PermissionError("Action no longer allowlisted")
        try:
            result = output(execute(argv, cwd=cwd, timeout=180, output_limit=cfg.max_output_chars))
            audit(cfg, actor, kind, target, "exit:" + str(result["exit_code"]))
            return {"request_id": request_id, "kind": kind, "target": target, **result}
        except Exception:
            audit(cfg, actor, kind, target, "exception")
            raise

    @mcp.tool()
    def recent_audit(limit: int = 25) -> dict:
        """Read recent operation audit records for accountability."""
        require_scope("server:read")
        if not 1 <= limit <= 100:
            raise ValueError("limit outside 1..100")
        from .approvals import connect
        with connect(cfg) as db:
            rows = db.execute(
                "SELECT ts,actor,kind,target,result FROM audit ORDER BY rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return {"events": [
            dict(zip(("ts","actor","kind","target","result"), row)) for row in rows
        ]}

    return mcp


def main() -> None:
    cfg = load_settings()
    if os.geteuid() == 0:
        raise SystemExit("Refusing to start as root; use dedicated server-mcp user")
    server = create_server(cfg)
    log.info("Server MCP binding to %s:%s (public resource %s)", cfg.host, cfg.port, cfg.resource)
    server.run(transport="streamable-http", host=cfg.host, port=cfg.port, stateless_http=True)


if __name__ == "__main__":
    main()
