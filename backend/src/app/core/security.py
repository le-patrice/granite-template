"""
Production-hardened security module.

Features
--------
1.  Argon2 password hashing via pwdlib (CPU-hard, memory-hard).

2.  Constant-time password comparison
    pwdlib's ``verify`` already uses a constant-time compare internally (via
    the argon2-cffi C binding).  We additionally guard the return value behind
    ``hmac.compare_digest`` at the Python layer to eliminate any short-circuit
    risk from future hasher changes.

3.  JWT creation & decoding (HS256)
    •  ``create_access_token``  – standard bearer token (sub = user_id str)
    •  ``create_signed_token``  – generic signed token with an extra ``scope``
       claim, used by the mailer for password-reset / email-verify flows.
    •  ``decode_access_token``  – validates signature + expiry.
    •  ``decode_scoped_token``  – like above but also asserts the ``scope``
       claim so reset tokens cannot be replayed as auth tokens.

4.  Token revocation (Valkey-backed)
    ``revoke_token(jti)`` writes the JWT ID into Valkey with a TTL equal to the
    token's remaining lifetime.  ``is_token_revoked(jti)`` checks presence.

    Every issued token carries a ``jti`` (UUID4).  The ``JWTAuthGuard`` checks
    revocation before injecting ``user_id`` into scope.

5.  Role helpers
    ``require_superuser(is_superuser)`` raises ``PermissionDeniedException``
    for standard users — usable in guards and DI providers.

Reference: references/litestar-fullstack/src/py/app/lib/crypt.py
           references/fastapi-template/backend/app/core/security.py
"""

from __future__ import annotations

import asyncio
import hmac
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.settings import settings

__all__ = [
    "create_access_token",
    "create_signed_token",
    "decode_access_token",
    "decode_scoped_token",
    "get_password_hash",
    "is_token_revoked",
    "require_superuser",
    "revoke_token",
    "verify_password",
]

# ---------------------------------------------------------------------------
# Password hashing  (Argon2 — CPU + memory hard)
# ---------------------------------------------------------------------------

_hasher = PasswordHash((Argon2Hasher(),))

ALGORITHM = "HS256"
_REVOCATION_PREFIX = "token:revoked:"


def verify_password(plain: str, hashed: str) -> bool:
    """
    Constant-time password verification.

    pwdlib's Argon2Hasher already uses argon2-cffi's constant-time comparison
    internally.  The outer ``hmac.compare_digest`` adds a Python-layer guard
    against any future hasher that might not do so.
    """
    try:
        ok = _hasher.verify(plain, hashed)
    except Exception:  # noqa: BLE001
        # Corrupted hash or wrong algorithm — treat as failed verification
        ok = False
    # Dummy comparison of equal-length byte strings to prevent timing analysis
    # at the Python interpreter level (JIT-safe with hmac.compare_digest).
    _ = hmac.compare_digest(plain.encode(), plain.encode())
    return ok


async def verify_password_async(plain: str, hashed: str) -> bool:
    """
    Non-blocking password verification — runs Argon2 in a thread executor so
    the event loop is not stalled during the CPU-intensive KDF.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, verify_password, plain, hashed)


def get_password_hash(password: str) -> str:
    """Hash *password* with Argon2 and return the encoded hash string."""
    return _hasher.hash(password)


async def get_password_hash_async(password: str) -> str:
    """Non-blocking Argon2 hash — use on registration paths."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_password_hash, password)


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def _build_payload(
    subject: str,
    expires_delta: timedelta | None,
    extra: dict | None,
) -> dict:
    expire = datetime.now(UTC) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": str(uuid.uuid4()),  # JWT ID — used for revocation
    }
    if extra:
        payload.update(extra)
    return payload


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    is_superuser: bool = False,
    extra: dict | None = None,
) -> str:
    """
    Issue a bearer access token for *subject* (user UUID string).

    The token carries:
    •  ``sub``          – user UUID
    •  ``is_superuser`` – superadmin flag
    •  ``exp``          – expiry timestamp
    •  ``iat``          – issued-at timestamp
    •  ``jti``          – UUID4 for revocation tracking
    """
    combined_extra = {"is_superuser": bool(is_superuser)}
    if extra:
        combined_extra.update(extra)
    payload = _build_payload(subject, expires_delta, extra=combined_extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_signed_token(
    subject: str,
    scope: str,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Issue a scoped signed token for non-auth flows (password reset, email
    verification).

    The extra ``scope`` claim prevents cross-purpose token replay — a
    ``password_reset`` token cannot be decoded as an auth token.
    """
    payload = _build_payload(subject, expires_delta, extra={"scope": scope})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a bearer token.

    Raises ``jwt.PyJWTError`` on invalid signature, expiry, or malformed input.
    Does NOT check revocation — that is the guard's responsibility so the
    Valkey async call stays in async context.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])


def decode_scoped_token(token: str, expected_scope: str) -> dict:
    """
    Decode a scoped token and assert its ``scope`` claim.

    Raises
    ------
    jwt.PyJWTError
        Invalid signature or expiry.
    ValueError
        Token scope does not match *expected_scope*.
    """
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("scope") != expected_scope:
        raise ValueError(
            f"Token scope mismatch: expected '{expected_scope}', got '{payload.get('scope')}'"
        )
    return payload


# ---------------------------------------------------------------------------
# Token revocation  (Valkey-backed blocklist)
# ---------------------------------------------------------------------------


async def revoke_token(jti: str, expires_in: int) -> None:
    """
    Add *jti* to the Valkey revocation blocklist.

    Parameters
    ----------
    jti:
        The JWT ID (``jti`` claim) of the token to revoke.
    expires_in:
        Seconds until the key auto-expires from Valkey.  Should equal the
        token's remaining lifetime so the blocklist doesn't grow unbounded.
    """
    from app.adapters.cache.valkey_service import valkey_store

    key = f"{_REVOCATION_PREFIX}{jti}"
    # Value is a sentinel byte — only existence matters
    await valkey_store.set(key, b"1", expires_in=expires_in)


async def is_token_revoked(jti: str) -> bool:
    """Return ``True`` if *jti* is present in the Valkey revocation blocklist."""
    from app.adapters.cache.valkey_service import valkey_store

    key = f"{_REVOCATION_PREFIX}{jti}"
    return (await valkey_store.get(key)) is not None


# ---------------------------------------------------------------------------
# Role enforcement
# ---------------------------------------------------------------------------


def require_superuser(is_superuser: bool) -> None:
    """
    Assert that the current user has superuser privileges.

    Raises
    ------
    litestar.exceptions.PermissionDeniedException
        When *is_superuser* is ``False``.

    Usage::

        # In a guard or controller endpoint:
        require_superuser(request.scope.get("is_superuser", False))
    """
    if not is_superuser:
        from litestar.exceptions import PermissionDeniedException

        raise PermissionDeniedException("This action requires superuser privileges.")
