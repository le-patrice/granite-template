"""
Tests for auth and user management endpoints.

Coverage
--------
POST /api/v1/users/register
    • Happy path — returns 201 + UserRead body
    • Duplicate email — returns 409
    • Missing required field — returns 400 / 422

POST /api/v1/auth/login
    • Valid credentials — returns 201 + token
    • Wrong password — returns 401
    • Non-existent email — returns 401

GET /api/v1/users/me
    • Authenticated — returns 200 + own profile
    • No token — returns 401
    • Tampered token — returns 401

PATCH /api/v1/users/me
    • Update full_name — returns 200 + updated profile
    • Update password and re-login — new token works
    • No token — returns 401
"""

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_REGISTER_URL = "/api/v1/users/register"
_LOGIN_URL = "/api/v1/auth/login"
_ME_URL = "/api/v1/users/me"

_BASE_USER = {
    "email": "alice@example.com",
    "password": "AliceSecure!2026",
    "full_name": "Alice Example",
}


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(_LOGIN_URL, json={"email": email, "password": password})
    return resp.json().get("access_token", "")


# ─────────────────────────────────────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────────────────────────────────────


class TestRegistration:
    async def test_register_happy_path(self, async_client: AsyncClient):
        user_payload = {
            "email": f"alice.{uuid.uuid4().hex[:6]}@example.com",
            "password": "AliceSecure!2026",
            "full_name": "Alice Example",
        }
        resp = await async_client.post(_REGISTER_URL, json=user_payload)

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["email"] == user_payload["email"]
        assert body["full_name"] == user_payload["full_name"]
        assert body["is_active"] is True
        assert body["is_superuser"] is False
        # hashed_password must NOT be exposed
        assert "hashed_password" not in body
        assert "password" not in body
        # id must be a valid UUID string
        assert "id" in body and len(body["id"]) == 36

    async def test_register_duplicate_email(self, async_client: AsyncClient):
        user_payload = {
            "email": f"dup.{uuid.uuid4().hex[:6]}@example.com",
            "password": "AliceSecure!2026",
            "full_name": "Alice Example",
        }
        await async_client.post(_REGISTER_URL, json=user_payload)
        resp = await async_client.post(_REGISTER_URL, json=user_payload)
        assert resp.status_code == 409

    async def test_register_missing_email(self, async_client: AsyncClient):
        payload = {"password": "NoEmail!2026", "full_name": "No Email"}
        resp = await async_client.post(_REGISTER_URL, json=payload)
        assert resp.status_code in (400, 422)

    async def test_register_missing_password(self, async_client: AsyncClient):
        payload = {"email": "nopass@example.com", "full_name": "No Password"}
        resp = await async_client.post(_REGISTER_URL, json=payload)
        assert resp.status_code in (400, 422)


# ─────────────────────────────────────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────────────────────────────────────


class TestLogin:
    async def test_login_valid_credentials(self, async_client: AsyncClient):
        # Register first so the user exists
        await async_client.post(_REGISTER_URL, json=_BASE_USER)

        resp = await async_client.post(
            _LOGIN_URL,
            json={"email": _BASE_USER["email"], "password": _BASE_USER["password"]},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert len(body["access_token"]) > 20  # non-trivial JWT

    async def test_login_wrong_password(self, async_client: AsyncClient):
        await async_client.post(_REGISTER_URL, json=_BASE_USER)
        resp = await async_client.post(
            _LOGIN_URL,
            json={"email": _BASE_USER["email"], "password": "WrongPassword!"},
        )
        assert resp.status_code == 401

    async def test_login_nonexistent_email(self, async_client: AsyncClient):
        resp = await async_client.post(
            _LOGIN_URL,
            json={"email": "ghost@example.com", "password": "DoesNotMatter"},
        )
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# /me – profile retrieval
# ─────────────────────────────────────────────────────────────────────────────


class TestGetMe:
    async def test_get_me_authenticated(self, registered_user, async_client: AsyncClient):
        resp = await async_client.get(
            _ME_URL,
            headers=_auth_headers(registered_user["token"]),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["email"] == registered_user["email"]
        assert body["full_name"] == registered_user["full_name"]
        assert body["is_active"] is True

    async def test_get_me_no_token(self, async_client: AsyncClient):
        resp = await async_client.get(_ME_URL)
        assert resp.status_code == 401

    async def test_get_me_tampered_token(self, async_client: AsyncClient):
        resp = await async_client.get(
            _ME_URL,
            headers={"Authorization": "Bearer this.is.not.a.valid.token"},
        )
        assert resp.status_code == 401

    async def test_get_me_malformed_header(self, async_client: AsyncClient):
        # Correct header name but missing "Bearer " prefix
        resp = await async_client.get(
            _ME_URL,
            headers={"Authorization": "Token abc123"},
        )
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# /me – profile update
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateMe:
    async def test_update_full_name(self, registered_user, async_client: AsyncClient):
        resp = await async_client.patch(
            _ME_URL,
            json={"full_name": "Alice Updated"},
            headers=_auth_headers(registered_user["token"]),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["full_name"] == "Alice Updated"

    async def test_update_password_and_relogin(self, registered_user, async_client: AsyncClient):
        new_password = "NewAlicePass!2026"

        # Change password
        patch_resp = await async_client.patch(
            _ME_URL,
            json={"password": new_password},
            headers=_auth_headers(registered_user["token"]),
        )
        assert patch_resp.status_code == 200, patch_resp.text

        # Old password should fail
        old_resp = await async_client.post(
            _LOGIN_URL,
            json={"email": registered_user["email"], "password": registered_user["password"]},
        )
        assert old_resp.status_code == 401

        # New password should succeed
        new_resp = await async_client.post(
            _LOGIN_URL,
            json={"email": registered_user["email"], "password": new_password},
        )
        assert new_resp.status_code == 201
        assert "access_token" in new_resp.json()

    async def test_update_me_no_token(self, async_client: AsyncClient):
        resp = await async_client.patch(_ME_URL, json={"full_name": "Hacker"})
        assert resp.status_code == 401

    async def test_update_me_partial_only_name(self, registered_user, async_client: AsyncClient):
        """PATCH with only full_name must not wipe out the password field."""
        resp = await async_client.patch(
            _ME_URL,
            json={"full_name": "Partial Update Only"},
            headers=_auth_headers(registered_user["token"]),
        )
        assert resp.status_code == 200
        # Confirm original password still works
        login = await async_client.post(
            _LOGIN_URL,
            json={
                "email": registered_user["email"],
                "password": registered_user["password"],
            },
        )
        assert login.status_code == 201
