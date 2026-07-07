from __future__ import annotations

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.factory import create_app


def make_test_client() -> TestClient:
    router = APIRouter()

    @router.post("/modules/booking/body-validation/extension-upload")
    async def protected_upload() -> dict[str, str]:
        return {"ok": "yes"}

    @router.get("/modules/booking/body-validation")
    async def protected_page() -> dict[str, str]:
        return {"ok": "yes"}

    @router.get("/modules/finance-records")
    async def protected_finance_page() -> dict[str, str]:
        return {"ok": "yes"}

    @router.post("/modules/export-customs/import")
    async def protected_export_import() -> dict[str, str]:
        return {"ok": "yes"}

    @router.post("/process")
    async def protected_legacy_process() -> dict[str, str]:
        return {"ok": "yes"}

    @router.get("/static/app.css")
    async def public_static() -> dict[str, str]:
        return {"ok": "yes"}

    return TestClient(create_app("access-test", routers=[router], init_runtime=False))


def test_access_control_is_disabled_without_token(monkeypatch) -> None:
    monkeypatch.delenv("MY_AUTOWORK_ACCESS_TOKEN", raising=False)

    client = make_test_client()

    response = client.post("/modules/booking/body-validation/extension-upload")

    assert response.status_code == 200


def test_access_control_rejects_protected_route_without_token(monkeypatch) -> None:
    monkeypatch.setenv("MY_AUTOWORK_ACCESS_TOKEN", "shared-secret")

    client = make_test_client()

    response = client.post("/modules/booking/body-validation/extension-upload")

    assert response.status_code == 403


def test_access_control_covers_shared_lan_modules(monkeypatch) -> None:
    monkeypatch.setenv("MY_AUTOWORK_ACCESS_TOKEN", "shared-secret")

    client = make_test_client()

    assert client.get("/modules/finance-records").status_code == 403
    assert client.post("/modules/export-customs/import").status_code == 403
    assert client.post("/process").status_code == 403


def test_access_control_accepts_header_token(monkeypatch) -> None:
    monkeypatch.setenv("MY_AUTOWORK_ACCESS_TOKEN", "shared-secret")

    client = make_test_client()

    response = client.post(
        "/modules/booking/body-validation/extension-upload",
        headers={"x-my-autowork-token": "shared-secret"},
    )

    assert response.status_code == 200
    assert response.cookies.get("my_autowork_access_token") == "shared-secret"


def test_access_control_accepts_query_token_and_sets_cookie(monkeypatch) -> None:
    monkeypatch.setenv("MY_AUTOWORK_ACCESS_TOKEN", "shared-secret")

    client = make_test_client()

    response = client.get("/modules/booking/body-validation?access_token=shared-secret", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/modules/booking/body-validation"
    assert response.cookies.get("my_autowork_access_token") == "shared-secret"


def test_access_control_leaves_static_files_public(monkeypatch) -> None:
    monkeypatch.setenv("MY_AUTOWORK_ACCESS_TOKEN", "shared-secret")

    client = make_test_client()

    response = client.get("/static/app.css")

    assert response.status_code != 403


def test_tms_upload_cors_allows_header_token_preflight(monkeypatch) -> None:
    monkeypatch.setenv("MY_AUTOWORK_ACCESS_TOKEN", "shared-secret")

    client = make_test_client()

    response = client.options(
        "/modules/booking/body-validation/extension-upload",
        headers={
            "origin": "https://smooth.clztoud.com",
            "access-control-request-method": "POST",
            "access-control-request-headers": "x-my-autowork-token,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://smooth.clztoud.com"
    assert response.headers["access-control-allow-credentials"] == "true"
