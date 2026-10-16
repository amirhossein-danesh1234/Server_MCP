from pathlib import Path

import pytest

from server_mcp.settings import load_settings


def valid_config(workspace: Path) -> str:
    return f'''
[auth]
issuer = "https://login.example.test/realms/mcp"
jwks_url = "https://login.example.test/certs"
resource = "https://mcp.example.test/mcp"
[server]
host = "127.0.0.1"
state_dir = "{workspace}/state"
[workspaces]
sample = "{workspace}"
[permissions]
operate_enabled = false
workspace_write_enabled = false
'''


def test_settings_fail_closed(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(valid_config(tmp_path))
    cfg = load_settings(str(path))
    assert cfg.operate_enabled is False
    assert cfg.workspace_write_enabled is False
    assert cfg.roots["sample"] == tmp_path
    path.write_text(valid_config(tmp_path).replace("127.0.0.1", "0.0.0.0"))
    with pytest.raises(ValueError, match="loopback"):
        load_settings(str(path))
    path.write_text(valid_config(tmp_path).replace("https://mcp.example.test/mcp", "http://example.test/mcp"))
    with pytest.raises(ValueError, match="HTTPS"):
        load_settings(str(path))
