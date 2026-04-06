"""FastMCP authentication provider for Bearer token and JWT verification."""

import structlog
from fastmcp.server.auth import AccessToken, AuthProvider
from jose import JWTError, jwt

from app.core.config import settings

logger = structlog.get_logger(__name__)


class BearerTokenAuthProvider(AuthProvider):
    """Custom auth provider supporting static Bearer tokens and JWT verification."""

    async def verify_token(self, token: str) -> AccessToken | None:
        """
        Verify Bearer token or JWT token.
        Returns AccessToken if valid, None otherwise.
        """
        if not token:
            logger.warn("empty_token_provided")
            return None

        # Strip whitespace from token
        token = token.strip()

        static_token = (
            settings.MCP_AUTH_TOKEN.get_secret_value() if settings.MCP_AUTH_TOKEN else None
        )
        jwt_secret = settings.MCP_JWT_SECRET.get_secret_value() if settings.MCP_JWT_SECRET else None

        # Log token attempt (first 10 chars only for security)
        logger.debug(
            "token_verification_attempt", token_prefix=token[:10] if len(token) > 10 else "short"
        )

        # Try static Bearer token first
        if static_token:
            static_token = static_token.strip()
            if token == static_token:
                logger.info("static_token_verified", client_id="api_client")
                return AccessToken(
                    token=token,
                    client_id="api_client",
                    scopes=["read", "write"],
                    expires_at=None,  # Static tokens don't expire
                    claims={"sub": "api_client"},
                )
            else:
                logger.debug(
                    "static_token_mismatch",
                    expected_prefix=static_token[:10] if len(static_token) > 10 else "short",
                    received_prefix=token[:10] if len(token) > 10 else "short",
                )

        # Try JWT verification
        if jwt_secret:
            try:
                payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
                sub = payload.get("sub", "unknown")
                scopes = payload.get("scopes", ["read"])
                exp = payload.get("exp")

                logger.info("jwt_token_verified", sub=sub)
                return AccessToken(
                    token=token,
                    client_id=sub,
                    scopes=scopes if isinstance(scopes, list) else [scopes] if scopes else ["read"],
                    expires_at=exp,
                    claims=payload,
                )
            except JWTError as e:
                logger.warn("jwt_verification_failed", error=str(e))
                return None

        logger.warn(
            "token_verification_failed",
            reason="no_matching_token",
            has_static_token=static_token is not None,
            has_jwt_secret=jwt_secret is not None,
        )
        return None


def get_auth_provider():
    """Get FastMCP auth provider instance."""
    if not settings.MCP_AUTH_ENABLED:
        return None

    return BearerTokenAuthProvider()
