from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.errors import Forbidden
from app.core.security import hash_token
from app.models import LoginCode
from app.services.auth import issue_login_code
from tests.factories import DEFAULT_PASSWORD, add_member, auth_headers, make_head, make_user


async def test_health(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_code_login_is_single_use(client, db: AsyncSession):
    head, _ = await make_head(db)
    code = await issue_login_code(db, head)
    await db.commit()

    response = await client.post("/api/auth/code-login", json={"code": code})
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["user"]["email"] == "head@example.com"
    assert body["user"]["has_password"] is True

    reused = await client.post("/api/auth/code-login", json={"code": code})
    assert reused.status_code == 401


async def test_expired_code_is_rejected(client, db: AsyncSession):
    head, _ = await make_head(db)
    db.add(
        LoginCode(
            user_id=head.id,
            code_hash=hash_token("expired-code"),
            expires_at=utcnow() - timedelta(seconds=1),
        )
    )
    await db.commit()

    response = await client.post("/api/auth/code-login", json={"code": "expired-code"})
    assert response.status_code == 401


async def test_password_login_refresh_and_logout(client, db: AsyncSession):
    await make_head(db)

    bad = await client.post(
        "/api/auth/login",
        json={"email": "head@example.com", "password": "wrong-password"},
    )
    assert bad.status_code == 401
    assert bad.json()["error"] == "Неверный email или пароль"

    response = await client.post(
        "/api/auth/login",
        json={"email": "HEAD@example.com", "password": DEFAULT_PASSWORD},
    )
    assert response.status_code == 200
    body = response.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    me = await client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["user"]["full_name"] == "Анна Петрова"
    assert me.json()["family"]["name"] == "Петровы"

    refreshed = await client.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != body["access_token"]

    logout = await client.post("/api/auth/logout", headers=headers)
    assert logout.status_code == 204

    after_logout = await client.post("/api/auth/refresh")
    assert after_logout.status_code == 401


async def test_set_password_for_passwordless_head(client, db: AsyncSession):
    user = await make_user(db, full_name="Без Пароля", telegram_id=42)
    from app.services.families import create_family

    await create_family(db, user)
    await db.commit()

    response = await client.post(
        "/api/auth/password",
        headers=auth_headers(user),
        json={"email": "new@example.com", "password": "newpassword123"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "new@example.com"
    assert response.json()["has_password"] is True

    login = await client.post(
        "/api/auth/login",
        json={"email": "new@example.com", "password": "newpassword123"},
    )
    assert login.status_code == 200

    change = await client.post(
        "/api/auth/password",
        headers=auth_headers(user),
        json={"email": "new@example.com", "password": "anotherpassword"},
    )
    assert change.status_code == 400
    assert change.json()["error"] == "Неверный текущий пароль"


async def test_member_cannot_access_panel(client, db: AsyncSession):
    _, family = await make_head(db)
    member = await add_member(db, family)

    me = await client.get("/api/auth/me", headers=auth_headers(member))
    assert me.status_code == 403
    assert "только главе" in me.json()["error"]

    expenses = await client.get("/api/expenses", headers=auth_headers(member))
    assert expenses.status_code == 403

    with pytest.raises(Forbidden):
        await issue_login_code(db, member)

    db.add(
        LoginCode(
            user_id=member.id,
            code_hash=hash_token("member-code"),
            expires_at=utcnow() + timedelta(minutes=5),
        )
    )
    await db.commit()

    code_login = await client.post("/api/auth/code-login", json={"code": "member-code"})
    assert code_login.status_code == 403
