# Server MCP Agent

**ChatGPT-first, host-resident Linux server MCP** — an open-source Python MCP server with OAuth, explicit workspace policies, system monitoring, Docker/systemd diagnostics, safe file edits and human-approved operations.

> **Status: v0.1 experimental.** Not audited or penetration-tested. Install on a disposable VM before using a production host. It is deliberately **not** an unauthenticated root shell. SSH remains an emergency recovery channel.

## Features

| Tool | Scope | Effect |
|---|---|---|
| `whoami`, `host_status`, `list_workspaces` | `server:read` | Identity and host health |
| `list_files`, `read_text` | `server:read` | Workspace-bounded UTF-8 files, hashes |
| `git_status`, `git_diff` | `server:read` | Inspect repositories |
| `list_processes`, `listening_ports` | `server:read` | Process/network diagnostics |
| `service_status`, `service_logs` | `server:read` | Allowlisted systemd services |
| `docker_containers`, `docker_logs` | `server:read` | Allowlisted Docker resources |
| `recent_audit` | `server:read` | Recent approval and mutation events |
| `write_text` | `server:write` | Optional atomic compare-and-swap workspace editing |
| `request_operation`, `execute_approved` | `server:operate` | Human-approved restarts/runbooks |

Administrative operations require BOTH an OAuth access token with `server:operate` AND `permissions.operate_enabled=true` AND approval via **local CLI**, with five-minute, one-use requests. There is no tool to self-approve.

## Architecture

```text
ChatGPT custom MCP app
       |
 HTTPS + OAuth 2.x (OIDC/JWT audience-scoped)
       |
 Caddy/NGINX TLS reverse proxy
       |
 127.0.0.1:8765/mcp       <-- MCP Python SDK Streamable HTTP
       |
 non-root server-mcp service
       |---- allowlisted workspaces / Git
       |---- systemd and journalctl read-only
       |---- Docker diagnostics (optional; socket access has high privilege!)
       |---- out-of-band operator approvals in SQLite
       |---- predefined runbooks, never arbitrary model-supplied shell
```

## Important requirements

- Linux, Python 3.11+, `systemd` for service management, optionally `docker`, `git`, `ss`, `journalctl`.
- An **external OAuth 2.1/OIDC authorization server** (Keycloak/Auth0/etc) that issues **JWT access tokens** with the exact MCP resource URL in the `aud` claim, proper `scope` strings and `RS256`/`ES256` signing. Server MCP is a **resource server**, not an identity provider.
- Public HTTPS address or supported secure MCP tunnel. The agent binds only to localhost.
- Availability of write tools in ChatGPT depends on its plan/workspace permissions and whether the custom MCP app is enabled.

## Quick deployment

Follow [docs/DEPLOY.md](docs/DEPLOY.md) and configure [config.example.toml](config.example.toml). This repository does **not** ship a remotely executable curl-to-shell installer.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pytest -q
```

Do not run the MCP service as root. See [SECURITY.md](SECURITY.md), [THIRD_PARTY.md](THIRD_PARTY.md), and [docs/CODEX_DEPLOY_PROMPT.md](docs/CODEX_DEPLOY_PROMPT.md).

## Source inspirations

Built on the official MIT-licensed [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), [psutil](https://github.com/giampaolo/psutil), and [PyJWT](https://github.com/jpadilla/pyjwt). The server-operations model is informed by MIT-licensed [fleet](https://github.com/wrxck/fleet) and [Dozor](https://github.com/anatolykoptev/dozor). Their code has **not** been copied or vendored: tools are newly implemented around established dependencies. GPL-3.0 1Panel is not copied.

MIT license. Experimental and provided without warranties.
