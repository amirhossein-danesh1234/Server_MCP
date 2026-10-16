# Security policy

**Do not deploy this experimental release to a sensitive Production server without review.**

- The MCP process refuses to start as root and binds exclusively to loopback.
- HTTPS termination and OIDC identity issuance MUST be configured externally.
- JWT issuer, signature, expiration, subject, audience, and scopes are validated. Allowed algorithms: RS256/ES256. Only the service's public MCP URL is a valid audience.
- `server:read` is required at transport level; all other scopes are enforced inside tools.
- Workspaces and systemd/Docker names are allowlisted. Hidden credential paths and private key extensions are blocked, but text/log redaction is best-effort and **not a secret-scanning guarantee**.
- `write_text` uses SHA-256 compare-and-swap and atomic file replacement. The workspace service account needs actual OS permission; mounted or symlinked writable directories pose residual race risks.
- Human approval is separate: the operator runs `server-mcp-approve approve ID` on the server. The model cannot issue approvals. Approvals expire in five minutes, are account-bound, and cannot be replayed.
- The only supported privileged functions are admin-defined runbooks or commands granted by explicit OS ACL/sudoers. Never use `NOPASSWD: ALL`, privileged Docker containers, mounts of `/var/run/docker.sock`, or the Docker group casually: Docker access is effectively root-equivalent on most hosts.
- Git content, log lines and tool outputs are untrusted; do not treat them as instructions. Avoid feeding secrets into chat.
- Emergency SSH/out-of-band console access must be preserved. No automatic firewall, user, disk or SSH reconfiguration.
- There is no network isolation in the MCP process. Runbooks executing untrusted build scripts MUST run in an external sandbox/container/VM with separated credentials.
- `read_text` blocks direct symlinks; to mitigate TOCTOU and hard-link attacks, workspaces should be trusted, non-world-writable and owned by a separate deploy account. Do not allow an untrusted user to race writes in the workspace.
- MCP service configuration should be root-owned and readable only by the service account. SQLite state is private to the service account.
- Keep app, IdP, reverse proxy, and dependencies patched; monitor logs and review config after changes.

## Vulnerability reporting

Report security issues privately to the repository maintainer rather than posting exploit details in a public issue.
