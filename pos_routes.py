from fastapi import APIRouter, Depends, Request, HTTPException, Header
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import get_pos_db
from auth import verify_token
from permissions import resolve_context, validate_permission
from pos_helpers import (
    APP_MENU_URL,
    LOGIN_FALLBACK_URL,
    get_user_or_redirect,
    build_logout_response,
    render_pos_html,
)

from pos_routes_catalog import router as catalog_router
from pos_routes_maintenance import router as maintenance_router
from pos_routes_sales import router as sales_router

router = APIRouter()

router.include_router(catalog_router)
router.include_router(maintenance_router)
router.include_router(sales_router)


@router.get("/health")
def health(db: Session = Depends(get_pos_db)):
    try:
        now = db.execute(text("SELECT NOW()")).fetchone()[0]
        return {"status": "ok", "db_time": str(now)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")


@router.get("/", response_class=HTMLResponse)
def root(
    request: Request,
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
):
    user = get_user_or_redirect(request, authorization)
    if not user:
        return RedirectResponse(url=LOGIN_FALLBACK_URL, status_code=302)

    return render_pos_html(request, user, authorization, x_app_id, x_client_id)


@router.get("/pos", response_class=HTMLResponse)
def pos_interface(
    request: Request,
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
):
    user = get_user_or_redirect(request, authorization)
    if not user:
        return RedirectResponse(url=LOGIN_FALLBACK_URL, status_code=302)

    return render_pos_html(request, user, authorization, x_app_id, x_client_id)


@router.post("/logout")
def logout():
    return build_logout_response()


@router.post("/pos/logout")
def logout_pos():
    return build_logout_response()


@router.get("/apps-menu")
def apps_menu():
    return RedirectResponse(url=APP_MENU_URL, status_code=302)


@router.get("/pos/apps-menu")
def apps_menu_pos():
    return RedirectResponse(url=APP_MENU_URL, status_code=302)


@router.get("/me")
def me(
    user: str = Depends(verify_token),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
):
    return {"user": user, "app_id": x_app_id, "client_id": x_client_id}


@router.get("/session-check")
def session_check(
    request: Request,
    authorization: str | None = Header(default=None),
):
    user = get_user_or_redirect(request, authorization)
    if not user:
        return RedirectResponse(url=LOGIN_FALLBACK_URL, status_code=302)

    return {"ok": True}


@router.get("/entry")
def entry(
    request: Request,
    user: str = Depends(verify_token),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
):
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    if not app_id or not client_id:
        raise HTTPException(status_code=400, detail="Faltan app_id o client_id")

    validate_permission(request, user, app_id, client_id, authorization)

    return {"ok": True, "user": user, "app_id": app_id, "client_id": client_id}