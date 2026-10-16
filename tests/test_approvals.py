import time
from pathlib import Path

import pytest

from server_mcp.approvals import approve, consume, request
from server_mcp.settings import Settings


def config(tmp_path: Path) -> Settings:
    return Settings(
        issuer="https://idp.test", resource="https://mcp.test/mcp", jwks_url="https://idp.test/jwks",
        host="127.0.0.1", port=8765, roots={"test":tmp_path},
        services=frozenset(), containers=frozenset(), runbooks={}, commands_cwd={},
        state_dir=tmp_path/"state", operate_enabled=True, workspace_write_enabled=False,
    )


def test_one_time_human_gate(tmp_path: Path, monkeypatch):
    cfg = config(tmp_path)
    created = request(cfg, "alice", "runbook", "example")
    rid = created["request_id"]
    with pytest.raises(PermissionError):
        consume(cfg, "alice", rid)
    monkeypatch.setattr("builtins.input", lambda _: f"APPROVE {rid}")
    assert approve(cfg, rid) is True
    with pytest.raises(PermissionError):
        consume(cfg, "mallory", rid)
    assert consume(cfg, "alice", rid) == ("runbook", "example")
    with pytest.raises(PermissionError):
        consume(cfg, "alice", rid)


def test_approval_requires_exact_confirmation(tmp_path: Path, monkeypatch):
    cfg = config(tmp_path)
    rid = request(cfg, "alice", "service_restart", "example.service")["request_id"]
    monkeypatch.setattr("builtins.input", lambda _: "yes")
    assert approve(cfg, rid) is False
    with pytest.raises(PermissionError):
        consume(cfg, "alice", rid)
