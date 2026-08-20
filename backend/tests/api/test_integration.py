"""
Integration tests — registration, login, logout, token refresh, and health.

These tests exercise the full HTTP stack (Litestar app + all middleware,
guards, DI, and plugins) through the AsyncTestClient.  The Valkey store is
mocked (autouse fixture in conftest.py) so tests run without a live cache.

Coverage
--------
GET  /health                          – liveness probe
POST /api/v1/users/register           – registration → 201 UserRead
POST /api/v1/auth/login               – exchange credentials → JWT
GET  /api/v1/users/me                 – authenticated profile fetch
POST /api/v1/auth/logout              – revoke token → 200
GET  /api/v1/users/me (after logout)  – revoked token → 401
POST /api/v1/auth/login (replay)      – fresh token after logout still works
Edge cases:
  - Login with non-existent email
  - Login with correct email but wrong password
  - Accessing protected route with no token
  - Accessing protected route with tampered token
  - Registering duplicate email (idempotency guard)
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Endpoint constants
# ---------------------------------------------------------------------------
_HEALTH_URL   = "/health"
_REGISTER_URL = "/api/v1/users/register"
_LOGIN_URL    = "/api/v1/auth/login"
_LOGOUT_URL   = "/api/v1/auth/logout"
_ME_URL       = "/api/v1/users/me"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _unique_user() -> dict[str, str]:
    uid = uuid.uuid4().hex[:8]
    return {
        "email": f"integration_{uid}@example.com",
        "password": "IntegrationPass!2026",
        "full_name": f"Integration User {uid}",
    }


async def _register_and_login(client: AsyncClient) -> tuple[dict, str]:
    """Register a fresh user and return (user_body, token)."""
    payload = _unique_user()
    reg = await client.post(_REGISTER_URL, json=payload)
    assert reg.status_code == 201, reg.text

    login = await client.post(
        _LOGIN_URL,
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert login.status_code == 201, login.text
    return reg.json(), login.json()["access_token"]


# ---------------------------------------------------------------------------
# Health probe
# ---------------------------------------------------------------------------

class TestHealthEndpoint:

    async def test_health_returns_ok(self, async_client: AsyncClient):
        resp = await async_client.get(_HEALTH_URL)
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_health_no_auth_required(self, async_client: AsyncClient):
        """Health must be reachable without any credentials."""
        resp = await async_client.get(_HEALTH_URL)
        assert resp.status_code == 200

    async def test_health_json_content_type(self, async_client: AsyncClient):
        resp = await async_client.get(_HEALTH_URL)
        assert "application/json" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestRegistrationIntegration:

    async def test_register_success(self, async_client: AsyncClient):
        payload = _unique_user()
        resp = await async_client.post(_REGISTER_URL, json=payload)

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["email"] == payload["email"]
        assert body["full_name"] == payload["full_name"]
        assert body["is_active"] is True
        assert body["is_superuser"] is False
        assert "id" in body
        assert "hashed_password" not in body
        assert "password" not in body

    async def test_register_duplicate_email_returns_409(self, async_client: AsyncClient):
        payload = _unique_user()
        r1 = await async_client.post(_REGISTER_URL, json=payload)
        assert r1.status_code == 201
        r2 = await async_client.post(_REGISTER_URL, json=payload)
        assert r2.status_code == 409

    async def test_register_invalid_payload_returns_400_or_422(
        self, async_client: AsyncClient
    ):
        resp = await async_client.post(_REGISTER_URL, json={"email": "only@email.com"})
        assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class TestLoginIntegration:

    async def test_login_returns_bearer_token(self, async_client: AsyncClient):
        payload = _unique_user()
        await async_client.post(_REGISTER_URL, json=payload)

        resp = await async_client.post(
            _LOGIN_URL,
            json={"email": payload["email"], "password": payload["password"]},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        # JWT has three dot-separated segments
        assert body["access_token"].count(".") == 2

    async def test_login_wrong_password_returns_401(self, async_client: AsyncClient):
        payload = _unique_user()
        await async_client.post(_REGISTER_URL, json=payload)
        resp = await async_client.post(
            _LOGIN_URL,
            json={"email": payload["email"], "password": "WrongPassword!"},
        )
        assert resp.status_code == 401

    async def test_login_nonexistent_email_returns_401(self, async_client: AsyncClient):
        resp = await async_client.post(
            _LOGIN_URL,
            json={"email": "ghost@nowhere.test", "password": "DoesNotMatter"},
        )
        assert resp.status_code == 401

    async def test_login_issues_new_token_each_call(self, async_client: AsyncClient):
        payload = _unique_user()
        await async_client.post(_REGISTER_URL, json=payload)

        creds = {"email": payload["email"], "password": payload["password"]}
        r1 = await async_client.post(_LOGIN_URL, json=creds)
        r2 = await async_client.post(_LOGIN_URL, json=creds)

        assert r1.status_code == r2.status_code == 201
        # Different jti claims → different tokens
        assert r1.json()["access_token"] != r2.json()["access_token"]


# ---------------------------------------------------------------------------
# Authenticated profile (GET /me)
# ---------------------------------------------------------------------------

class TestProfileIntegration:

    async def test_get_me_returns_own_profile(self, async_client: AsyncClient):
        payload = _unique_user()
        await async_client.post(_REGISTER_URL, json=payload)
        login = await async_client.post(
            _LOGIN_URL,
            json={"email": payload["email"], "password": payload["password"]},
        )
        token = login.json()["access_token"]

        me = await async_client.get(_ME_URL, headers=_bearer(token))
        assert me.status_code == 200, me.text
        assert me.json()["email"] == payload["email"]

    async def test_get_me_no_token_returns_401(self, async_client: AsyncClient):
        resp = await async_client.get(_ME_URL)
        assert resp.status_code == 401

    async def test_get_me_tampered_token_returns_401(self, async_client: AsyncClient):
        resp = await async_client.get(_ME_URL, headers=_bearer("not.a.jwt"))
        assert resp.status_code == 401

    async def test_get_me_missing_bearer_prefix_returns_401(
        self, async_client: AsyncClient
    ):
        resp = await async_client.get(
            _ME_URL, headers={"Authorization": "Token abc123"}
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logout + token revocation
# ---------------------------------------------------------------------------

class TestLogoutIntegration:

    async def test_logout_returns_200(self, async_client: AsyncClient):
        _, token = await _register_and_login(async_client)
        resp = await async_client.post(_LOGOUT_URL, headers=_bearer(token))
        assert resp.status_code == 200
        assert "revoked" in resp.json().get("detail", "").lower()

    async def test_token_rejected_after_logout(self, async_client: AsyncClient):
        """Token must be rejected with 401 on any protected route after logout."""
        _, token = await _register_and_login(async_client)

        # Confirm it works before logout
        me_before = await async_client.get(_ME_URL, headers=_bearer(token))
        assert me_before.status_code == 200

        # Logout
        await async_client.post(_LOGOUT_URL, headers=_bearer(token))

        # Same token must now fail
        me_after = await async_client.get(_ME_URL, headers=_bearer(token))
        assert me_after.status_code == 401

    async def test_new_login_works_after_logout(self, async_client: AsyncClient):
        """A fresh login after logout must succeed and issue a usable token."""
        payload = _unique_user()
        await async_client.post(_REGISTER_URL, json=payload)

        creds = {"email": payload["email"], "password": payload["password"]}
        first_login = await async_client.post(_LOGIN_URL, json=creds)
        token1 = first_login.json()["access_token"]

        await async_client.post(_LOGOUT_URL, headers=_bearer(token1))

        second_login = await async_client.post(_LOGIN_URL, json=creds)
        assert second_login.status_code == 201
        token2 = second_login.json()["access_token"]
        assert token2 != token1   # new jti

        me = await async_client.get(_ME_URL, headers=_bearer(token2))
        assert me.status_code == 200

    async def test_logout_without_token_returns_401(self, async_client: AsyncClient):
        resp = await async_client.post(_LOGOUT_URL)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Token refresh (simulate: re-login after expiry)
# ---------------------------------------------------------------------------

class TestTokenRefreshIntegration:

    async def test_second_login_issues_fresh_token(self, async_client: AsyncClient):
        """
        We don't have a /refresh endpoint yet; re-login is the refresh flow.
        Verify the new token is different and still grants access.
        """
        payload = _unique_user()
        await async_client.post(_REGISTER_URL, json=payload)

        creds = {"email": payload["email"], "password": payload["password"]}
        r1 = await async_client.post(_LOGIN_URL, json=creds)
        # Small sleep ensures different iat timestamp if tokens are time-based
        time.sleep(0.05)
        r2 = await async_client.post(_LOGIN_URL, json=creds)

        t1, t2 = r1.json()["access_token"], r2.json()["access_token"]
        assert t1 != t2  # different jti → different token string

        # Both tokens must be individually valid
        m1 = await async_client.get(_ME_URL, headers=_bearer(t1))
        m2 = await async_client.get(_ME_URL, headers=_bearer(t2))
        assert m1.status_code == 200
        assert m2.status_code == 200
