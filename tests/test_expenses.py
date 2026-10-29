from sqlalchemy.ext.asyncio import AsyncSession

from app.services.families import create_family
from tests.factories import add_member, auth_headers, make_head, make_user


async def test_expenses_crud_and_family_scope(client, db: AsyncSession):
    head, family = await make_head(db)
    member = await add_member(db, family)
    headers = auth_headers(head)

    created_for_member = await client.post(
        "/api/expenses",
        headers=headers,
        json={
            "user_id": str(member.id),
            "amount": 350.5,
            "category": "еда",
            "spent_at": "2026-10-01",
            "comment": "кофе",
        },
    )
    assert created_for_member.status_code == 201
    expense_id = created_for_member.json()["id"]
    assert created_for_member.json()["user_id"] == str(member.id)
    assert created_for_member.json()["amount"] == 350.5

    created_for_head = await client.post(
        "/api/expenses",
        headers=headers,
        json={"amount": 1200, "category": "транспорт", "spent_at": "2026-10-02"},
    )
    assert created_for_head.status_code == 201
    assert created_for_head.json()["user_id"] == str(head.id)

    all_expenses = await client.get("/api/expenses", headers=headers)
    assert all_expenses.status_code == 200
    assert len(all_expenses.json()) == 2

    only_member = await client.get(f"/api/expenses?user_id={member.id}", headers=headers)
    assert len(only_member.json()) == 1
    assert only_member.json()[0]["comment"] == "кофе"

    by_category = await client.get("/api/expenses?category=транспорт", headers=headers)
    assert len(by_category.json()) == 1

    updated = await client.patch(
        f"/api/expenses/{expense_id}",
        headers=headers,
        json={"amount": 400, "comment": "кофе и булочка"},
    )
    assert updated.status_code == 200
    assert updated.json()["amount"] == 400.0
    assert updated.json()["comment"] == "кофе и булочка"

    fetched = await client.get(f"/api/expenses/{expense_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["amount"] == 400.0

    deleted = await client.delete(f"/api/expenses/{expense_id}", headers=headers)
    assert deleted.status_code == 204

    missing = await client.get(f"/api/expenses/{expense_id}", headers=headers)
    assert missing.status_code == 404

    invalid_category = await client.post(
        "/api/expenses",
        headers=headers,
        json={"amount": 10, "category": "еда и напитки"},
    )
    assert invalid_category.status_code == 422

    invalid_amount = await client.post(
        "/api/expenses",
        headers=headers,
        json={"amount": 0, "category": "еда"},
    )
    assert invalid_amount.status_code == 422


async def test_cannot_create_expense_for_foreign_user(client, db: AsyncSession):
    head, _ = await make_head(db)
    stranger = await make_user(db, full_name="Чужой", telegram_id=999)
    await create_family(db, stranger)
    await db.commit()

    response = await client.post(
        "/api/expenses",
        headers=auth_headers(head),
        json={
            "user_id": str(stranger.id),
            "amount": 100,
            "category": "другое",
        },
    )
    assert response.status_code == 404


async def test_family_members_endpoint(client, db: AsyncSession):
    head, family = await make_head(db)
    await add_member(db, family)

    response = await client.get("/api/users", headers=auth_headers(head))
    assert response.status_code == 200
    members = response.json()
    assert len(members) == 2
    assert {member["role"] for member in members} == {"head", "member"}

    family_response = await client.get("/api/family", headers=auth_headers(head))
    assert family_response.status_code == 200
    assert family_response.json()["family"]["invite_code"]
    assert len(family_response.json()["members"]) == 2
