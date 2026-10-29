import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import auth, expenses, family, health, telegram
from app.bot.runtime import create_runtime
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import engine

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.bot_runtime = None
    app.state.bot_tasks = set()

    runtime = None
    if settings.telegram_enabled:
        try:
            runtime = create_runtime(settings)
            await runtime.start()
            app.state.bot_runtime = runtime
        except Exception:
            logger.exception("failed to start Telegram bot; API will run without it")

    try:
        yield
    finally:
        if runtime is not None:
            await runtime.stop()
        for task in list(app.state.bot_tasks):
            task.cancel()
        await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Учёт семейных расходов: REST API, Telegram-бот и панель главы семьи.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.message})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "loc": list(error.get("loc", [])),
                "msg": error.get("msg", "invalid value"),
                "type": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"error": "Ошибка валидации данных", "details": details},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})

    api_router = APIRouter(prefix="/api")
    api_router.include_router(auth.router)
    api_router.include_router(family.router)
    api_router.include_router(expenses.router)
    api_router.include_router(health.router)
    app.include_router(api_router)
    app.include_router(telegram.create_router(settings))

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {"service": settings.app_name, "docs": "/docs"}

    return app


app = create_app()
