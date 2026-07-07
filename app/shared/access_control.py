from __future__ import annotations

import os
import secrets
from urllib.parse import urlencode
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse, RedirectResponse, Response


ACCESS_TOKEN_ENV = "MY_AUTOWORK_ACCESS_TOKEN"
ACCESS_TOKEN_COOKIE = "my_autowork_access_token"
ACCESS_TOKEN_HEADER = "x-my-autowork-token"
ACCESS_TOKEN_QUERY = "access_token"
CORS_ORIGINS_ENV = "MY_AUTOWORK_CORS_ORIGINS"

PROTECTED_PATH_PREFIXES = (
    "/download",
    "/modules/booking/body-validation",
    "/modules/booking/generate",
    "/modules/booking/flex-texas-review-tiff",
    "/modules/booking/warehouse-mail",
    "/modules/booking/flex-texas-reply-mail",
    "/modules/billing",
    "/modules/ufo-mail",
    "/modules/dispatch-mail",
    "/modules/export-customs",
    "/modules/finance-records",
    "/modules/import-customs",
    "/modules/mail-classifier",
    "/process",
    "/session",
)

PUBLIC_PATH_PREFIXES = (
    "/static",
)


def configured_access_token() -> str:
    return os.environ.get(ACCESS_TOKEN_ENV, "").strip()


def configured_cors_origins() -> list[str]:
    raw = os.environ.get(CORS_ORIGINS_ENV, "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return [
        "https://smooth.clztoud.com",
        "http://www.clztoud.com:8008",
    ]


def is_protected_path(path: str) -> bool:
    if path == "/" or any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES):
        return False
    return any(path.startswith(prefix) for prefix in PROTECTED_PATH_PREFIXES)


def request_access_token(request: Request) -> str:
    return (
        request.headers.get(ACCESS_TOKEN_HEADER, "").strip()
        or request.cookies.get(ACCESS_TOKEN_COOKIE, "").strip()
        or request.query_params.get(ACCESS_TOKEN_QUERY, "").strip()
    )


def has_valid_access_token(request: Request, expected_token: str) -> bool:
    supplied = request_access_token(request)
    return bool(supplied) and secrets.compare_digest(supplied, expected_token)


def install_tms_upload_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configured_cors_origins(),
        allow_methods=["POST", "OPTIONS"],
        allow_headers=["content-type", ACCESS_TOKEN_HEADER],
        allow_credentials=True,
    )


def set_access_cookie(response: Response, token: str, *, cross_site: bool = False) -> None:
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        token,
        httponly=True,
        samesite="none" if cross_site else "lax",
        secure=cross_site,
    )


def clean_access_token_url(request: Request) -> str:
    query_items = [
        (key, value)
        for key, value in request.query_params.multi_items()
        if key != ACCESS_TOKEN_QUERY
    ]
    query = urlencode(query_items)
    return f"{request.url.path}?{query}" if query else request.url.path


def install_access_control(app: FastAPI) -> None:
    @app.middleware("http")
    async def access_control_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        expected_token = configured_access_token()
        if not expected_token or not is_protected_path(request.url.path):
            return await call_next(request)

        if not has_valid_access_token(request, expected_token):
            return PlainTextResponse("Access token required.", status_code=403)

        query_token = request.query_params.get(ACCESS_TOKEN_QUERY, "").strip()
        if query_token and secrets.compare_digest(query_token, expected_token) and request.method in {"GET", "HEAD"}:
            response = RedirectResponse(clean_access_token_url(request), status_code=303)
            set_access_cookie(response, query_token)
            return response

        response = await call_next(request)
        header_token = request.headers.get(ACCESS_TOKEN_HEADER, "").strip()
        if header_token and secrets.compare_digest(header_token, expected_token):
            set_access_cookie(
                response,
                header_token,
                cross_site=bool(request.headers.get("origin")) and request.url.scheme == "https",
            )
            return response
        if query_token and secrets.compare_digest(query_token, expected_token):
            set_access_cookie(response, query_token)
        return response
