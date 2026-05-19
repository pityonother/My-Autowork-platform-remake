from __future__ import annotations

from collections.abc import Callable, Iterable

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.paths import APP_DIR, OUTPUT_DIR, STATIC_DIR, TEMPLATES_DIR, UPLOAD_DIR


DatabaseInitializer = Callable[[], None]


def ensure_runtime_dirs() -> None:
    for path in [UPLOAD_DIR, OUTPUT_DIR, APP_DIR]:
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
) -> FastAPI:
    if init_runtime:
        ensure_runtime_dirs()
        init_databases(db_initializers)

    app = FastAPI(title=title)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    for router in routers:
        app.include_router(router)
    return app
