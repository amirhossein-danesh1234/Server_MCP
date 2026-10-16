# Codex deployment instruction — Server MCP Agent

You are deploying my ChatGPT-first Server MCP Agent to **my own Linux VPS**. Repository: https://github.com/amirhossein-danesh1234/Server_MCP

Objective: enable a **private authenticated remote MCP endpoint for ChatGPT**, NOT an open SSH substitute. Do not change UniLrn/Baazargaan apps or unrelated existing services.

Procedure:
1. Inventory OS/version, existing reverse proxy/DNS/TLS, open ports, running systemd services, Docker containers, and backup/recovery method. Preserve existing workloads. Do not guess domain or IdP values. Ask ONLY for essential missing authorization-server credentials/hostname.
2. Pull the latest reviewed commit from `main` (or a user-approved pinned SHA), inspect README, SECURITY.md and docs/DEPLOY.md. Run tests; do not deploy if tests fail.
3. Install Python 3.11+, dedicated non-root `server-mcp` account, isolated venv, systemd unit, and private config/state directories, following docs/DEPLOY.md.
4. Set up a dedicated HTTPS subdomain under my control and a reverse proxy to 127.0.0.1:8765. Do not expose 8765 to the Internet. Keep existing web apps/routes untouched.
5. Configure a real OIDC authorization server with PKCE, refresh tokens as needed, access JWTs with exact `aud=https://<host>/mcp`, `iss`, `exp`, `iat`, `sub`, and scopes. Do not fake OAuth or disable authentication. Keep client secrets out of repository/logs.
6. Configure explicit workspace and service allowlists only after inspecting actual host paths. Start with `workspace_write_enabled=false` and `operate_enabled=false`; connect ChatGPT read-only first.
7. Verify: HTTPS, OAuth protected-resource discovery, 401 for unauthenticated MCP calls, authorized `whoami`, `host_status`, status/logs and disallowed path rejection. Never paste tokens into reports.
8. If requested and authorized, configure write scopes and OS ACLs per workspace. Privileged operations must use human-approved runbooks or a narrowly scoped broker. NO root MCP process, NOPASSWD ALL, Docker socket mounts, blanket writable root mounts, or shutdown/reboot tests.
9. Supply ChatGPT plugin setup details (endpoint, issuer, scopes) without sharing secrets, plus exact end-to-end test observations and rollback commands.
10. Produce a concise deployment report: hostname, OS, pinned commit, service status, endpoint, OAuth checks, tool checks, unresolved blockers and rollback plan.

Do NOT deploy changes to the application code. Don't silently open firewall rules, change SSH, or grant broad Docker/host privileges. If ChatGPT subscription/workspace lacks write-enabled custom MCP tools, report that limitation transparently and leave read-only mode operational.
