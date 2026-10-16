"""Verify real OIDC JWTs: issuer, audience, signature, expiry and scopes."""
from __future__ import annotations

import logging

import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.middleware.auth_context import get_access_token

from .settings import Settings

log = logging.getLogger(__name__)


class OIDCTokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if not settings.jwks_url.startswith("https://"):
            raise ValueError("JWKS must use HTTPS")
        self.jwks = PyJWKClient(settings.jwks_url, cache_jwk_set=True, lifespan=300)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token, key.key, algorithms=["RS256", "ES256"],
                audience=self.settings.resource, issuer=self.settings.issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
                leeway=30,
            )
            raw_scopes = claims.get("scope", claims.get("scp", ""))
            scopes = raw_scopes.split() if isinstance(raw_scopes, str) else list(raw_scopes)
            if not all(isinstance(s, str) for s in scopes):
                return None
            if "server:read" not in scopes:
                return None
            subject = claims["sub"]
            if not isinstance(subject, str) or not subject:
                return None
            return AccessToken(
                token=token, client_id=str(claims.get("client_id", claims.get("azp", "unknown"))),
                scopes=scopes, subject=subject,
                expires_at=int(claims["exp"]), resource=self.settings.resource,
                claims={"iss": claims["iss"], "sub": subject},
            )
        except (jwt.PyJWTError, ValueError, TypeError, OSError) as exc:
            log.warning("OAuth access token rejected: %s", type(exc).__name__)
            return None


def require_scope(scope: str) -> str:
    token = get_access_token()
    if token is None or scope not in token.scopes:
        raise PermissionError(f"Required OAuth scope: {scope}")
    return token.subject or token.client_id
