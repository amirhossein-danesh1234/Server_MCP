# Deploy on a Linux VPS: ChatGPT-first MCP

> This is an experimental host-resident agent. Test on a disposable VM first. Deployment does not change firewall rules, SSH settings, or existing applications.

## 1. Prerequisites

- Ubuntu/Debian Linux (primary tested target), Python 3.11+, venv, Git, systemd.
- A domain under your control, reachable over HTTPS, e.g. `mcp.example.com`.
- A properly configured external OIDC provider (e.g. Keycloak, Auth0). **JWT access tokens**, not opaque tokens, must be issued with:
  - `iss`: exact `auth.issuer`
  - `aud`: exact `auth.resource`, e.g. `https://mcp.example.com/mcp`
  - `scope`: `server:read` and optionally `server:write`, `server:operate`
  - valid RS256/ES256 signature, `iat`, `exp`, `sub`.
- For ChatGPT OAuth, configure Authorization Code + PKCE, correct redirect URI(s), and refresh-token support if required. Register the OAuth client in your IdP according to ChatGPT's connector configuration. The MCP service is a **resource server**, NOT an OAuth authorization server.
- Real OS access for the `server-mcp` user to every workspace or service required. Never grant blanket root.

## 2. Install package (manual, reversible)

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv git ca-certificates
sudo useradd --system --user-group --home-dir /var/lib/server-mcp \
  --create-home --shell /usr/sbin/nologin server-mcp || true
sudo install -d -m 0700 -o server-mcp -g server-mcp /var/lib/server-mcp
sudo install -d -m 0750 -o root -g server-mcp /etc/server-mcp

sudo git clone https://github.com/amirhossein-danesh1234/Server_MCP.git /opt/server-mcp
cd /opt/server-mcp
# Use a reviewed and pinned commit or release, not an unreviewed moving branch.
sudo python3 -m venv /opt/server-mcp/.venv
sudo /opt/server-mcp/.venv/bin/python -m pip install --upgrade pip
sudo /opt/server-mcp/.venv/bin/python -m pip install .
sudo chown -R root:root /opt/server-mcp
sudo cp config.example.toml /etc/server-mcp/config.toml
sudo chown root:server-mcp /etc/server-mcp/config.toml
sudo chmod 0640 /etc/server-mcp/config.toml
```

Create the configured workspace directories separately and allow the service user **read-only** access first (e.g. ACLs on a project checkout). Edit `/etc/server-mcp/config.toml` using a root editor: set the issuer/JWKS/resource URLs and existing workspace paths; leave both mutation flags off. The MCP process fails closed if any configured workspace does not exist.

```bash
sudo install -m 0644 systemd/server-mcp.service /etc/systemd/system/server-mcp.service
sudo systemctl daemon-reload
sudo systemctl enable --now server-mcp
sudo systemctl status server-mcp --no-pager
sudo journalctl -u server-mcp -n 100 --no-pager
```

Service listens on **127.0.0.1:8765** only. Never publish that port directly.

## 3. Reverse proxy (example Caddy)

Use your existing HTTPS proxy or install Caddy separately. Set up real TLS, DNS, and certificate automation before connecting ChatGPT.

```caddyfile
mcp.example.com {
    reverse_proxy 127.0.0.1:8765 {
        # MCP's default localhost transport host checks may reject a public Host header.
        header_up Host 127.0.0.1:8765
    }
}
```

Verify that OAuth protected-resource metadata is reachable at:
`https://mcp.example.com/.well-known/oauth-protected-resource/mcp`
It should advertise your configured authorization server. A no-token MCP request to `/mcp` must return **401**, never tools/data.

Ensure TLS, no proxy auth bypass, and that `/.well-known/` is forwarded. If deployed behind a tunnel, check its compatibility with the public MCP URL and OAuth discovery.

## 4. Connect ChatGPT

Create a private custom MCP app / plugin using:

- **MCP URL:** `https://mcp.example.com/mcp`
- **Authentication:** OAuth 2.x via the configured external issuer
- Requested scopes: start with `server:read` only.
- Scan tools, authorize with the IdP, and run `whoami` and `host_status`.
- Once the read-only check succeeds, explicitly authorize `server:write`/`server:operate` for the appropriate identity/roles (if your ChatGPT account/workspace supports write-enabled custom MCP apps). Do not confuse tool discovery with a granted scope.

See https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt for platform-specific access requirements.

## 5. Controlled mutations

To permit source edits:
1. Enable `permissions.workspace_write_enabled=true`.
2. Grant write permissions only to specific workspace files, not `/etc`, `/root`, or credential paths.
3. Review and add the corresponding `ReadWritePaths=/srv/path` to a systemd drop-in (the shipped unit has `ProtectSystem=strict`).
4. Restart the MCP service and explicitly grant `server:write` via the IdP. Edits require a previous `sha256` from `read_text`.

For service/container restarts or admin-defined runbooks:
1. Enable `permissions.operate_enabled=true`; allowlist exact service/container or runbook names.
2. Ensure appropriate OS privileges exist; the service starts unprivileged. For systemctl restarts, prefer a **narrow separate sudoers rule** for the specific exact executable+service, together with a vetted wrapper. Never grant blanket sudo. The shipped service runs plain `systemctl restart`, so on ordinary hosts that requires root and will fail without a deliberately configured privileged broker.
3. Have ChatGPT call `request_operation("service_restart", "example.service")`; it returns a request UUID.
4. On the server console, run:
   ```bash
   sudo -u server-mcp /opt/server-mcp/.venv/bin/server-mcp-approve list
   sudo -u server-mcp /opt/server-mcp/.venv/bin/server-mcp-approve approve REQUEST_UUID
   ```
5. Only after human approval, ChatGPT calls `execute_approved(REQUEST_UUID)`. Requests expire after 5 minutes and are one-use.

**Important:** A workspace runbook executes its configured argv using the unprivileged service user. If it needs privileged operations, build a separately audited restricted broker first. The toolkit never ships a generic root shell.

## 6. Validate and rollback

```bash
sudo systemctl status server-mcp --no-pager
sudo journalctl -u server-mcp -n 100 --no-pager
# Stop immediately without touching workloads:
sudo systemctl disable --now server-mcp
```

Never stop production applications as a routine test. Keep emergency SSH/provider console access. See SECURITY.md.

## Known limitations

- No native GUI; no complete arbitrary root shell; no built-in identity provider.
- Untrusted Docker socket access is dangerous; the default service cannot manage Docker unless OS permissions are intentionally changed.
- Works best on Linux with systemd; other distributions may need adaptations.
- `runbook` calls are synchronous (up to 180 seconds) and **not** a persistent asynchronous job engine.
- Text/log redaction is best-effort; do not use on environments where logs contain unshareable secrets.
- Automated end-to-end OAuth/ChatGPT deployment requires a real IdP and an eligible ChatGPT workspace and is not covered by unit tests.
