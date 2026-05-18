from fastapi import APIRouter, Depends, Request, HTTPException, Header
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from db import get_pos_db, Product
from auth import verify_token
from permissions import resolve_context, validate_permission
from pos_helpers import (
    APP_MENU_URL,
    LOGIN_FALLBACK_URL,
    get_user_or_redirect,
    build_logout_response,
    render_pos_html,
    resolve_inventory_source_for_stocks,
    validate_internal_request,
    build_category_path,
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
        return {
            "ok": True,
            "db_time": str(now)
        }
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

@router.get("/internal/catalog-source")
def internal_catalog_source(
    request: Request,
    pos_db: Session = Depends(get_pos_db),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
    x_internal_request: str | None = Header(alias="X-Internal-Request", default=None),
    x_internal_secret: str | None = Header(alias="X-Internal-Secret",default=None,),
):
    app_id, client_id = resolve_context(
        request,
        x_app_id,
        x_client_id,
    )

    if not app_id or not client_id:
        raise HTTPException(
            status_code=400,
            detail="Faltan app_id o client_id",
        )
        
    validate_internal_request(
        x_internal_request,
        x_internal_secret,
    )

    user = verify_token(
        request,
        authorization,
    )

    validate_permission(
        request,
        user,
        app_id,
        client_id,
        authorization,
    )

    catalog_source = resolve_inventory_source_for_stocks(
        pos_db,
        client_id,
    )

    return {
        "client_id": client_id,
        "catalog_source": catalog_source,
    }
    
@router.get("/internal/inventory/sku/{sku}")
def internal_inventory_by_sku(
    sku: str,
    request: Request,
    pos_db: Session = Depends(get_pos_db),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
    x_internal_request: str | None = Header(alias="X-Internal-Request",default=None),
    x_internal_secret: str | None = Header(alias="X-Internal-Secret",default=None,),
):
    app_id, client_id = resolve_context(
        request,
        x_app_id,
        x_client_id,
    )
    
    validate_internal_request(
        x_internal_request,
        x_internal_secret,
    )

    user = verify_token(
        request,
        authorization,
    )

    validate_permission(
        request,
        user,
        app_id,
        client_id,
        authorization,
    )

    product = (
        pos_db.query(Product)
        .filter(
            Product.client_id == client_id,
            Product.sku == sku,
            Product.is_active == 1,
        )
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Producto no encontrado",
        )

    return {
        "client_id": client_id,
        "sku": product.sku,
        "product_id": product.id,
        "product_name": product.name,

        "category_id": product.category_id,

        "category_name": (
            product.category.name
            if product.category
            else None
        ),

        "category_parent_id": (
            product.category.parent_id
            if product.category
            else None
        ),

        "category_order": (
            product.category.sort_order
            if product.category
            else None
        ),

        "category_path": (
            build_category_path(product.category)
            if product.category
            else None
        ),

        "track_inventory": product.track_inventory,
        "inventory_mode": product.inventory_mode,

        "stock_quantity": product.stock_quantity,

        "updated_at": product.updated_at,
    }
    
@router.get("/internal/inventory/{product_id}")
def internal_inventory_by_id(
    product_id: int,
    request: Request,
    pos_db: Session = Depends(get_pos_db),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
    x_internal_request: str | None = Header(alias="X-Internal-Request",default=None),
    x_internal_secret: str | None = Header(alias="X-Internal-Secret",default=None,),
):
    app_id, client_id = resolve_context(
        request,
        x_app_id,
        x_client_id,
    )

    validate_internal_request(
        x_internal_request,
        x_internal_secret,
    )

    user = verify_token(
        request,
        authorization,
    )

    validate_permission(
        request,
        user,
        app_id,
        client_id,
        authorization,
    )

    product = (
        pos_db.query(Product)
        .options(joinedload(Product.category))
        .filter(
            Product.client_id == client_id,
            Product.id == product_id,
            Product.is_active == 1,
        )
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Producto no encontrado",
        )

    category = product.category

    return {
        "client_id": client_id,
        "sku": product.sku,
        "product_id": product.id,
        "product_name": product.name,

        "category_id": product.category_id,

        "category_name": (
            category.name
            if category
            else None
        ),

        "category_parent_id": (
            category.parent_id
            if category
            else None
        ),

        "category_order": (
            category.sort_order
            if category
            else None
        ),

        "category_path": (
            build_category_path(category)
            if category
            else None
        ),

        "track_inventory": product.track_inventory,
        "inventory_mode": product.inventory_mode,

        "stock_quantity": product.stock_quantity,

        "updated_at": product.updated_at,
    }
    
@router.get("/internal/inventory")
def internal_inventory_list(
    request: Request,
    page: int = 1,
    page_size: int = 100,
    only_active: bool = True,
    only_track_inventory: bool = True,
    user: str = Depends(verify_token),
    pos_db: Session = Depends(get_pos_db),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
    x_internal_request: str | None = Header(alias="X-Internal-Request",default=None),
    x_internal_secret: str | None = Header(alias="X-Internal-Secret",default=None,),
):
    app_id, client_id = resolve_context(
        request,
        x_app_id,
        x_client_id,
    )
    
    validate_internal_request(
        x_internal_request,
        x_internal_secret,
    )

    if not app_id or not client_id:
        raise HTTPException(
            status_code=400,
            detail="Faltan app_id o client_id",
        )

    validate_permission(
        request,
        user,
        app_id,
        client_id,
        authorization,
    )

    query = (
        pos_db.query(Product)
        .options(joinedload(Product.category))
        .filter(Product.client_id == client_id)
    )

    if only_active:
        query = query.filter(Product.is_active == 1)

    if only_track_inventory:
        query = query.filter(Product.track_inventory == 1)

    total = query.count()

    products = (
        query
        .order_by(Product.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []

    for product in products:
        items.append({
            "sku": product.sku,
            "product_id": product.id,
            "product_name": product.name,

            "category_id": product.category_id,

            "category_name": (
                product.category.name
                if product.category
                else None
            ),

            "category_parent_id": (
                product.category.parent_id
                if product.category
                else None
            ),

            "category_order": (
                product.category.sort_order
                if product.category
                else None
            ),

            "category_path": (
                build_category_path(product.category)
                if product.category
                else None
            ),

            "track_inventory": product.track_inventory,
            "inventory_mode": product.inventory_mode,

            "stock_quantity": product.stock_quantity,

            "updated_at": product.updated_at,
        })

    return {
        "client_id": client_id,
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": items,
    }