"""
Comprehensive RBAC and OpenAPI Security Tests.

Tests:
1. OAuth2 Form Data login vs JSON login.
2. OpenAPI security schemes definition (BearerAuth, OAuth2Password).
3. Superadmin RBAC enforcement:
   - Unauthenticated -> 401 Unauthorized
   - Regular User -> 403 Forbidden on admin routes
   - Superadmin -> 200/201 Success on admin routes
4. User role updates and admin deletion.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestOpenAPISecuritySchemes:
    async def test_openapi_schema_contains_security_schemes(self, async_client: AsyncClient):
        resp = await async_client.get("/docs/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        components = schema.get("components", {})
        security_schemes = components.get("securitySchemes", {})
        assert "BearerAuth" in security_schemes
        assert "OAuth2Password" in security_schemes
        assert security_schemes["BearerAuth"]["type"] == "http"
        assert security_schemes["BearerAuth"]["scheme"] == "bearer"
        assert security_schemes["OAuth2Password"]["type"] == "oauth2"


@pytest.mark.asyncio
class TestOAuth2LoginFlow:
    async def test_form_data_login_success(self, registered_user: dict, async_client: AsyncClient):
        form_payload = {
            "username": registered_user["email"],
            "password": registered_user["password"],
        }
        resp = await async_client.post(
            "/api/v1/auth/login",
            data=form_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data

    async def test_json_login_success(self, registered_user: dict, async_client: AsyncClient):
        json_payload = {
            "email": registered_user["email"],
            "password": registered_user["password"],
        }
        resp = await async_client.post(
            "/api/v1/auth/login",
            json=json_payload,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0


@pytest.mark.asyncio
class TestSuperadminRBAC:
    async def test_unauthenticated_admin_endpoints_return_401(self, async_client: AsyncClient):
        # POST /users
        resp = await async_client.post(
            "/api/v1/users", json={"email": "a@b.com", "password": "1", "full_name": "A"}
        )
        assert resp.status_code == 401

        # GET /users
        resp = await async_client.get("/api/v1/users")
        assert resp.status_code == 401

        # DELETE /users/{id}
        resp = await async_client.delete(f"/api/v1/users/{uuid.uuid4()}")
        assert resp.status_code == 401

    async def test_regular_user_forbidden_on_admin_endpoints(
        self,
        registered_user: dict,
        async_client: AsyncClient,
    ):
        headers = _auth_headers(registered_user["token"])

        # Regular user attempting to provision another user -> 403
        resp = await async_client.post(
            "/api/v1/users",
            json={
                "email": f"hacked.{uuid.uuid4().hex[:8]}@example.com",
                "password": "Password123!",
                "full_name": "Hacked User",
                "is_superuser": True,
            },
            headers=headers,
        )
        assert resp.status_code == 403

        # Regular user attempting to list all users -> 403
        resp = await async_client.get("/api/v1/users", headers=headers)
        assert resp.status_code == 403

        # Regular user attempting to delete another user -> 403
        resp = await async_client.delete(f"/api/v1/users/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 403

        # Regular user attempting to modify another user's role -> 403
        resp = await async_client.patch(
            f"/api/v1/users/{registered_user['id']}/role",
            json={"is_superuser": True},
            headers=headers,
        )
        assert resp.status_code == 403

    async def test_superadmin_user_permitted_on_admin_endpoints(
        self,
        async_client: AsyncClient,
    ):
        admin_id = str(uuid.uuid4())
        admin_token = create_access_token(subject=admin_id, is_superuser=True)
        admin_headers = _auth_headers(admin_token)

        # 1. Superadmin creates a new user
        new_email = f"provisioned.{uuid.uuid4().hex[:8]}@example.com"
        create_resp = await async_client.post(
            "/api/v1/users",
            json={
                "email": new_email,
                "password": "ProvisionedPass123!",
                "full_name": "Provisioned User",
                "is_superuser": False,
            },
            headers=admin_headers,
        )
        assert create_resp.status_code == 201
        created_user = create_resp.json()
        target_user_id = created_user["id"]

        # 2. Superadmin lists all users
        list_resp = await async_client.get("/api/v1/users", headers=admin_headers)
        assert list_resp.status_code == 200
        assert any(u["id"] == target_user_id for u in list_resp.json())

        # 3. Superadmin promotes user to superuser
        patch_resp = await async_client.patch(
            f"/api/v1/users/{target_user_id}/role",
            json={"is_superuser": True},
            headers=admin_headers,
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["is_superuser"] is True

        # 4. Superadmin deletes user
        del_resp = await async_client.delete(
            f"/api/v1/users/{target_user_id}",
            headers=admin_headers,
        )
        assert del_resp.status_code == 200
