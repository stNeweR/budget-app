from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.deps import HeadContext, get_current_head
from app.core.errors import InvalidCredentials
from app.core.ratelimit import rate_limit
from app.db.session import get_db
from app.schemas.auth import (
    CodeLoginIn,
    FamilyOut,
    LoginIn,
    MeOut,
    PasswordSetIn,
    TokenOut,
    UserOut,
)
from app.services import auth as auth_service
from app.services.families import get_family_for_user

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"


def _cookie_path(settings: Settings) -> str:
    return "/api/auth"


def set_refresh_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw_token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path=_cookie_path(settings),
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE,
        path=_cookie_path(settings),
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )


def _token_response(
    response: Response,
    settings: Settings,
    user,
    family,
    tokens: auth_service.IssuedTokens,
) -> TokenOut:
    set_refresh_cookie(response, tokens.refresh_token, settings)
    return TokenOut(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        user=UserOut.model_validate(user),
        family=family,
    )


@router.post(
    "/code-login",
    response_model=TokenOut,
    dependencies=[Depends(rate_limit("code-login", 20, 300))],
)
async def code_login(
    payload: CodeLoginIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenOut:
    user = await auth_service.consume_login_code(db, payload.code)
    family, _ = await get_family_for_user(db, user.id)
    tokens = await auth_service.issue_tokens(db, user, request.headers.get("user-agent"))
    await db.commit()
    return _token_response(response, settings, user, family, tokens)


@router.post(
    "/login",
    response_model=TokenOut,
    dependencies=[Depends(rate_limit("login", 20, 300))],
)
async def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenOut:
    user = await auth_service.authenticate(db, payload.email, payload.password)
    family, _ = await get_family_for_user(db, user.id)
    tokens = await auth_service.issue_tokens(db, user, request.headers.get("user-agent"))
    await db.commit()
    return _token_response(response, settings, user, family, tokens)


@router.post("/refresh", response_model=TokenOut)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenOut:
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if not raw_token:
        raise InvalidCredentials("Сессия истекла, войдите снова")

    user, tokens = await auth_service.rotate_refresh(
        db, raw_token, request.headers.get("user-agent")
    )
    family, _ = await get_family_for_user(db, user.id)
    await db.commit()
    return _token_response(response, settings, user, family, tokens)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token:
        await auth_service.revoke_refresh(db, raw_token)
        await db.commit()
    clear_refresh_cookie(response, settings)


@router.get("/me", response_model=MeOut)
async def me(ctx: HeadContext = Depends(get_current_head)) -> MeOut:
    return MeOut(
        user=UserOut.model_validate(ctx.user),
        family=FamilyOut.model_validate(ctx.family),
        has_password=ctx.user.has_password,
    )


@router.post("/password", response_model=UserOut)
async def set_password(
    payload: PasswordSetIn,
    ctx: HeadContext = Depends(get_current_head),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user = await auth_service.set_password(
        db,
        ctx.user,
        payload.email,
        payload.password,
        payload.current_password,
    )
    await db.commit()
    return UserOut.model_validate(user)
