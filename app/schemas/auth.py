import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr | None
    full_name: str
    tg_username: str
    telegram_id: int | None
    has_password: bool


class FamilyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    invite_code: str


class FamilyMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    tg_username: str
    telegram_id: int | None
    role: str


class CodeLoginIn(BaseModel):
    code: str = Field(min_length=1, max_length=256)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class PasswordSetIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    current_password: str | None = Field(default=None, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
    family: FamilyOut


class MeOut(BaseModel):
    user: UserOut
    family: FamilyOut
    has_password: bool
