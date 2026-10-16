import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from server_mcp.auth import OIDCTokenVerifier
from server_mcp.settings import Settings


def config(tmp_path: Path) -> Settings:
    return Settings(
        issuer="https://idp.test", resource="https://mcp.test/mcp", jwks_url="https://idp.test/jwks",
        host="127.0.0.1", port=8765, roots={"test":tmp_path},
        services=frozenset(), containers=frozenset(), runbooks={}, commands_cwd={},
        state_dir=tmp_path/"state", operate_enabled=False, workspace_write_enabled=False,
    )


def test_jwt_signature_issuer_audience_and_scope(tmp_path: Path):
    cfg = config(tmp_path)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = OIDCTokenVerifier(cfg)
    verifier.jwks = SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key()))
    claims = {
        "iss": cfg.issuer, "aud": cfg.resource, "sub": "alice", "client_id": "chatgpt",
        "scope": "server:read server:operate", "iat": int(time.time()), "exp": int(time.time()) + 300,
    }
    signed = jwt.encode(claims, private, algorithm="RS256")
    valid = asyncio.run(verifier.verify_token(signed))
    assert valid is not None and valid.subject == "alice"
    assert "server:operate" in valid.scopes
    assert asyncio.run(verifier.verify_token(jwt.encode({**claims, "aud": "https://evil.test"}, private, algorithm="RS256"))) is None
    assert asyncio.run(verifier.verify_token(jwt.encode({**claims, "scope": "server:operate"}, private, algorithm="RS256"))) is None
