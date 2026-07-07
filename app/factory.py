from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.paths import OUTPUT_DIR, RUNTIME_DIR, STATIC_DIR, TEMPLATES_DIR, UPLOAD_DIR
from app.shared.access_control import install_access_control, install_tms_upload_cors
from app.shared.state import SESSION_STORE


DatabaseInitializer = Callable[[], None]


def ensure_runtime_dirs() -> None:
    for path in [RUNTIME_DIR, UPLOAD_DIR, OUTPUT_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def init_databases(initializers: Iterable[DatabaseInitializer] = ()) -> None:
    for initializer in initializers:
        initializer()


def create_templates() -> Jinja2Templates:
    return Jinja2Templates(directory=str(TEMPLATES_DIR))


def create_app(
    title: str,
    *,
    db_initializers: Iterable[DatabaseInitializer] = (),
    routers: Iterable[APIRouter] = (),
    init_runtime: bool = True,
    lifespan: Any = None,
) -> FastAPI:
    if init_runtime:
        ensure_runtime_dirs()
        init_databases(db_initializers)

    app = FastAPI(title=title, lifespan=lifespan)

    @app.middleware("http")
    async def cleanup_expired_sessions(request: Any, call_next: Any) -> Any:
        SESSION_STORE.cleanup_if_due()
        return await call_next(request)

    install_access_control(app)
    install_tms_upload_cors(app)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    for router in routers:
        app.include_router(router)
    return app
