from pathlib import Path

from server_mcp.runner import execute


def test_arguments_not_interpreted_as_shell(tmp_path: Path):
    result = execute(["/bin/echo", "hello; touch /tmp/server-mcp-should-not-exist"], cwd=tmp_path)
    assert result["exit_code"] == 0
    assert "hello; touch" in result["stdout"]


def test_missing_program():
    result = execute(["/missing/not-a-command"])
    assert result["exit_code"] == 127
