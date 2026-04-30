# pos_routes_maintenance.py

from typing import List

from fastapi import APIRouter, Depends, Request, HTTPException, Header
from sqlalchemy.orm import Session

from db import get_pos_db, Category, Product, PosPrice, PosClientSettings, PosCustomer
from auth import verify_token
from permissions import resolve_context, validate_permission, get_role_info
from schemas import (
    CategoryCreate,
    CategoryResponse,
    ProductCreate,
    ProductResponse,
    PosClientSettingsUpsert,
    PosClientSettingsResponse,
    PosCustomerCreate,
    PosCustomerUpdate,
    PosCustomerResponse,
)

from pos_helpers import (
    get_catalog_source,
    require_catalog_integration_url,
    fetch_stocks_categories,
    fetch_stocks_items,
    normalize_product_type,
    normalize_inventory_mode,
    sync_pos_price_snapshot_for_product,
    resolve_outbound_authorization,
)

router = APIRouter()


def _require_catalog_write_access(
    request: Request,
    user: str,
    app_id: int,
    client_id: int,
    authorization: str | None,
):
    validate_permission(request, user, app_id, client_id, authorization)
    role_info = get_role_info(request, app_id, client_id, authorization)

    # v6.3 oficial:
    # system_admin + app_client_admin = CRUD catálogos
    # member = solo consulta
    if not (role_info.get("is_system_admin", False) or role_info.get("is_app_client_admin", False)):
        raise HTTPException(status_code=403, detail="No tienes permisos para mantenimiento de catálogos.")

    return role_info


def _require_pos_config_read_access(
    request: Request,
    user: str,
    app_id: int,
    client_id: int,
    authorization: str | None,
):
    validate_permission(request, user, app_id, client_id, authorization)
    role_info = get_role_info(request, app_id, client_id, authorization)

    # INV-3B.1 oficial:
    # system_admin + app_client_admin = ven Configuración POS
    # member = no ve / no entra
    if not (role_info.get("is_system_admin", False) or role_info.get("is_app_client_admin", False)):
        raise HTTPException(status_code=403, detail="No tienes permisos para consultar Configuración POS.")

    return role_info


def _require_pos_config_write_access(
    request: Request,
    user: str,
    app_id: int,
    client_id: int,
    authorization: str | None,
):
    validate_permission(request, user, app_id, client_id, authorization)
    role_info = get_role_info(request, app_id, client_id, authorization)

    # INV-3B.1 oficial:
    # solo system_admin edita Configuración POS
    if not role_info.get("is_system_admin", False):
        raise HTTPException(status_code=403, detail="No tienes permisos para editar Configuración POS.")

    return role_info

def _require_pos_customers_access(
    request: Request,
    user: str,
    app_id: int,
    client_id: int,
    authorization: str | None,
):
    # Customers es catálogo operativo del POS:
    # system_admin + app_client_admin + member = permitido
    validate_permission(request, user, app_id, client_id, authorization)
    return get_role_info(request, app_id, client_id, authorization)


def _build_maintenance_products_response(pos_db: Session, client_id: int):
    products = (
        pos_db.query(Product)
        .filter(
            Product.client_id == client_id,
            Product.is_active == True,
        )
        .order_by(Product.name.asc())
        .all()
    )

    if not products:
        return []

    product_ids = [p.id for p in products]
    category_ids = list({p.category_id for p in products if p.category_id is not None})

    categories_map = {}
    if category_ids:
        categories = (
            pos_db.query(Category)
            .filter(
                Category.client_id == client_id,
                Category.id.in_(category_ids),
            )
            .all()
        )
        categories_map = {c.id: c.name for c in categories}

    prices = (
        pos_db.query(PosPrice)
        .filter(
            PosPrice.client_id == client_id,
            PosPrice.catalog_source == "pos",
            PosPrice.catalog_item_id.in_(product_ids),
        )
        .all()
    )
    prices_map = {p.catalog_item_id: p for p in prices}

    rows = []
    for product in products:
        price_row = prices_map.get(product.id)

        rows.append({
            "id": product.id,
            "client_id": product.client_id,
            "name": product.name,
            "description": product.description,
            # sale_price comercial SIEMPRE desde pos_prices si existe
            "sale_price": float(price_row.sale_price if price_row else (getattr(product, "price", 0) or 0.0)),
            "product_type": product.product_type or "physical",
            "track_inventory": bool(product.track_inventory),
            # inventory_mode queda como snapshot / histórico, se conserva por compatibilidad
            "inventory_mode": product.inventory_mode or "pos_legacy",
            "stock_item_id": product.stock_item_id,
            "cost": float(product.cost or 0.0),
            "sku": product.sku,
            "barcode": product.barcode,
            "category_id": product.category_id,
            "category_name": categories_map.get(product.category_id),
            "stock_quantity": int(product.stock_quantity or 0),
            "min_stock": int(product.min_stock or 0),
            # bandera comercial efectiva visible
            "is_active": bool(price_row.is_active) if price_row else bool(product.is_active),
            # NO exponer is_sellable aquí; la regla comercial efectiva ya vive en pos_prices / is_active
            "image_url": product.image_url,
        })

    return rows


@router.get("/api/categories", response_model=List[CategoryResponse])
def get_categories(
    request: Request,
    user: str = Depends(verify_token),
    pos_db: Session = Depends(get_pos_db),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
):
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    if not app_id or not client_id:
        raise HTTPException(status_code=400, detail="Faltan app_id o client_id")

    validate_permission(request, user, app_id, client_id, authorization)

    catalog_source = get_catalog_source(pos_db, client_id)

    # Flujo POS original: categorías locales
    if catalog_source == "pos":
        categories = (
            pos_db.query(Category)
            .filter(
                Category.client_id == client_id,
                Category.is_active == True,
            )
            .order_by(Category.name.asc())
            .all()
        )

        return [
            {
                "id": category.id,
                "client_id": category.client_id,
                "name": category.name,
                "description": category.description,
                "color": category.color or "#6B7280",
                "is_active": bool(category.is_active),
                "created_at": getattr(category, "created_at", None),
                "updated_at": getattr(category, "updated_at", None),
            }
            for category in categories
        ]

    # Flujo Stocks: categorías vivas desde Stocks API
    catalog_integration_url = require_catalog_integration_url(pos_db, client_id)
    outbound_authorization = resolve_outbound_authorization(request, authorization)

    raw_items = fetch_stocks_categories(
        catalog_integration_url=catalog_integration_url,
        authorization=outbound_authorization,
        app_id=app_id,
        client_id=client_id,
    )

    return [
        {
            "id": item["id"],
            "client_id": item.get("client_id", client_id),
            "name": item["name"],
            "description": item.get("description"),
            "color": item.get("color") or "#6B7280",
            "is_active": bool(item.get("is_active", True)),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
        for item in raw_items
        if item.get("id") is not None
    ]


@router.post("/api/categories", response_model=CategoryResponse)
def create_category(
    data: CategoryCreate,
    request: Request,
    user: str = Depends(verify_token),
    pos_db: Session = Depends(get_pos_db),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
):
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    if not app_id or not client_id:
        raise HTTPException(status_code=400, detail="Faltan app_id o client_id")

    _require_catalog_write_access(request, user, app_id, client_id, authorization)

    category = Category(
        client_id=client_id,
        name=data.name,
        description=data.description,
        color=data.color,
    )
    pos_db.add(category)
    pos_db.commit()
    pos_db.refresh(category)
    return category


@router.put("/api/categories/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    data: CategoryCreate,
    request: Request,
    user: str = Depends(verify_token),
    pos_db: Session = Depends(get_pos_db),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
):
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    if not app_id or not client_id:
        raise HTTPException(status_code=400, detail="Faltan app_id o client_id")

    _require_catalog_write_access(request, user, app_id, client_id, authorization)

    category = (
        pos_db.query(Category)
        .filter(
            Category.id == category_id,
            Category.client_id == client_id,
            Category.is_active == True,
        )
        .first()
    )
    if not category:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    category.name = data.name
    category.description = data.description
    category.color = data.color

    related_products = (
        pos_db.query(Product)
        .filter(
            Product.client_id == client_id,
            Product.category_id == category_id,
        )
        .all()
    )

    for product in related_products:
        sync_pos_price_snapshot_for_product(pos_db, client_id, product)

    pos_db.commit()
    pos_db.refresh(category)
    return category


@router.get("/api/products", response_model=List[ProductResponse])
def get_products(
    request: Request,
    user: str = Depends(verify_token),
    pos_db: Session = Depends(get_pos_db),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
):
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    if not app_id or not client_id:
        raise HTTPException(status_code=400, detail="Faltan app_id o client_id")

    validate_permission(request, user, app_id, client_id, authorization)

    catalog_source = get_catalog_source(pos_db, client_id)

    if catalog_source == "pos":
        prices = (
            pos_db.query(PosPrice)
            .filter(
                PosPrice.client_id == client_id,
                PosPrice.catalog_source == "pos",
                PosPrice.is_active == True,
            )
            .order_by(PosPrice.display_name_snapshot.asc())
            .all()
        )

        product_ids = [p.catalog_item_id for p in prices if p.catalog_item_id is not None]
        products_map = {}
        categories_map = {}

        if product_ids:
            products = (
                pos_db.query(Product)
                .filter(
                    Product.client_id == client_id,
                    Product.id.in_(product_ids),
                    Product.is_active == True,
                )
                .all()
            )
            products_map = {p.id: p for p in products}

            category_ids = list({p.category_id for p in products if p.category_id is not None})

            if category_ids:
                categories = (
                    pos_db.query(Category)
                    .filter(
                        Category.client_id == client_id,
                        Category.id.in_(category_ids),
                    )
                    .all()
                )
                categories_map = {c.id: c.name for c in categories}

        result = []
        for price in prices:
            product = products_map.get(price.catalog_item_id)
            if not product:
                continue

            result.append({
                "id": price.id,
                "client_id": price.client_id,
                "name": product.name,
                "description": product.description,
                "sale_price": float(price.sale_price or 0.0),
                "product_type": product.product_type or "physical",
                "track_inventory": bool(product.track_inventory),
                # inventory_mode se conserva solo como snapshot / compatibilidad
                "inventory_mode": product.inventory_mode or "pos_legacy",
                "stock_item_id": product.stock_item_id,
                "cost": float(product.cost or 0.0),
                "sku": product.sku,
                "barcode": product.barcode,
                "category_id": product.category_id,
                "category_name": categories_map.get(product.category_id),
                # SOLO si catalog_source = pos, el frontend leerá stock_quantity local
                "stock_quantity": int(product.stock_quantity or 0),
                "min_stock": int(product.min_stock or 0),
                # bandera comercial efectiva
                "is_active": bool(price.is_active),
                "image_url": product.image_url,
            })

        return result

    # catalog_source = stocks -> fuente viva desde Stocks API
    catalog_integration_url = require_catalog_integration_url(pos_db, client_id)
    outbound_authorization = resolve_outbound_authorization(request, authorization)

    stock_items = fetch_stocks_items(
        catalog_integration_url=catalog_integration_url,
        authorization=outbound_authorization,
        app_id=app_id,
        client_id=client_id,
    )

    return [
        {
            # IMPORTANTE:
            # en stocks el id del response es el id vivo del item, no pos_price.id
            "id": int(item["id"]),
            "client_id": int(item.get("client_id", client_id)),
            "name": item.get("name"),
            "description": item.get("description"),
            # En modal de productos esto es catálogo base, no catálogo comercial
            "sale_price": 0.0,
            "product_type": item.get("item_type") or "physical",
            "track_inventory": bool(item.get("track_inventory", True)),
            "inventory_mode": "stocks_api",
            "stock_item_id": int(item["id"]),
            "cost": float(item.get("cost") or 0.0),
            "sku": item.get("sku"),
            "barcode": item.get("barcode"),
            "category_id": item.get("category_id"),
            "category_name": item.get("category_name"),
            # Para prueba de conectividad sí mostrar stock vivo
            "stock_quantity": int(item.get("on_hand_qty") or item.get("stock", 0) or 0),
            "min_stock": int(item.get("min_stock") or 0),
            "is_active": bool(item.get("is_active", True)),
            "image_url": None,
        }
        for item in stock_items
        if item.get("id") is not None
    ]


@router.get("/api/maintenance/products", response_model=List[ProductResponse])
def get_maintenance_products(
    request: Request,
    user: str = Depends(verify_token),
    pos_db: Session = Depends(get_pos_db),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
):
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    if not app_id or not client_id:
        raise HTTPException(status_code=400, detail="Faltan app_id o client_id")

    validate_permission(request, user, app_id, client_id, authorization)

    catalog_source = get_catalog_source(pos_db, client_id)

    # Flujo POS original: se conserva intacto
    if catalog_source == "pos":
        return _build_maintenance_products_response(pos_db, client_id)

    # Flujo Stocks: catálogo base vivo desde Stocks API
    catalog_integration_url = require_catalog_integration_url(pos_db, client_id)
    outbound_authorization = resolve_outbound_authorization(request, authorization)

    stock_items = fetch_stocks_items(
        catalog_integration_url=catalog_integration_url,
        authorization=outbound_authorization,
        app_id=app_id,
        client_id=client_id,
    )

    return [
        {
            # Para mantenimiento en modo stocks, el id visible es el id vivo del item
            "id": int(item["id"]),
            "client_id": int(item.get("client_id", client_id)),
            "name": item.get("name"),
            "description": item.get("description"),
            # Modal de productos = catálogo base, no catálogo comercial
            "sale_price": 0.0,
            "product_type": item.get("item_type") or "physical",
            "track_inventory": bool(item.get("track_inventory", True)),
            "inventory_mode": "stocks_api",
            "stock_item_id": int(item["id"]),
            "cost": float(item.get("cost") or 0.0),
            "sku": item.get("sku"),
            "barcode": item.get("barcode"),
            "category_id": item.get("category_id"),
            "category_name": item.get("category_name"),
            "stock_quantity": int(item.get("on_hand_qty") or item.get("stock", 0) or 0),
            "min_stock": int(item.get("min_stock") or 0),
            "is_active": bool(item.get("is_active", True)),
            "image_url": None,
        }
        for item in stock_items
        if item.get("id") is not None
    ]


@router.post("/api/maintenance/products", response_model=ProductResponse)
def create_product(
    data: ProductCreate,
    request: Request,
    user: str = Depends(verify_token),
    pos_db: Session = Depends(get_pos_db),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
):
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    if not app_id or not client_id:
        raise HTTPException(status_code=400, detail="Faltan app_id o client_id")

    _require_catalog_write_access(request, user, app_id, client_id, authorization)

    product = Product(
        client_id=client_id,
        name=data.name,
        description=data.description,
        cost=float(getattr(data, "cost", 0) or 0),
        sku=getattr(data, "sku", None),
        barcode=getattr(data, "barcode", None),
        category_id=getattr(data, "category_id", None),
        stock_quantity=int(getattr(data, "stock_quantity", 0) or 0),
        min_stock=int(getattr(data, "min_stock", 0) or 0),
        image_url=getattr(data, "image_url", None),
        product_type=normalize_product_type(getattr(data, "product_type", None)),
        track_inventory=bool(getattr(data, "track_inventory", True)),
        # Se conserva por compatibilidad / snapshot, NO como switch operativo
        inventory_mode=normalize_inventory_mode(getattr(data, "inventory_mode", None)),
        stock_item_id=getattr(data, "stock_item_id", None),
        is_active=bool(getattr(data, "is_active", True)),
    )

    pos_db.add(product)
    pos_db.flush()

    # Crea / actualiza snapshot comercial en pos_prices
    sync_pos_price_snapshot_for_product(pos_db, client_id, product)

    pos_db.commit()

    rows = _build_maintenance_products_response(pos_db, client_id)
    created = next((x for x in rows if x["id"] == product.id), None)
    if not created:
        raise HTTPException(status_code=500, detail="No se pudo reconstruir el producto creado.")

    return created


@router.put("/api/maintenance/products/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    data: ProductCreate,
    request: Request,
    user: str = Depends(verify_token),
    pos_db: Session = Depends(get_pos_db),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
):
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    if not app_id or not client_id:
        raise HTTPException(status_code=400, detail="Faltan app_id o client_id")

    _require_catalog_write_access(request, user, app_id, client_id, authorization)

    product = (
        pos_db.query(Product)
        .filter(
            Product.id == product_id,
            Product.client_id == client_id,
            Product.is_active == True,
        )
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    product.name = data.name
    product.description = data.description
    product.cost = float(getattr(data, "cost", 0) or 0)
    product.sku = getattr(data, "sku", None)
    product.barcode = getattr(data, "barcode", None)
    product.category_id = getattr(data, "category_id", None)
    product.stock_quantity = int(getattr(data, "stock_quantity", 0) or 0)
    product.min_stock = int(getattr(data, "min_stock", 0) or 0)
    product.image_url = getattr(data, "image_url", None)
    product.product_type = normalize_product_type(getattr(data, "product_type", None))
    product.track_inventory = bool(getattr(data, "track_inventory", True))
    # Se conserva por compatibilidad / snapshot, NO como switch operativo
    product.inventory_mode = normalize_inventory_mode(getattr(data, "inventory_mode", None))
    product.stock_item_id = getattr(data, "stock_item_id", None)
    product.is_active = bool(getattr(data, "is_active", True))

    sync_pos_price_snapshot_for_product(pos_db, client_id, product)

    pos_db.commit()

    rows = _build_maintenance_products_response(pos_db, client_id)
    updated = next((x for x in rows if x["id"] == product.id), None)
    if not updated:
        raise HTTPException(status_code=500, detail="No se pudo reconstruir el producto actualizado.")

    return updated


@router.get("/api/pos-settings", response_model=PosClientSettingsResponse)
def get_pos_settings(
    request: Request,
    user: str = Depends(verify_token),
    pos_db: Session = Depends(get_pos_db),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
):
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    if not app_id or not client_id:
        raise HTTPException(status_code=400, detail="Faltan app_id o client_id")

    _require_pos_config_read_access(request, user, app_id, client_id, authorization)

    settings = (
        pos_db.query(PosClientSettings)
        .filter(PosClientSettings.client_id == client_id)
        .first()
    )

    if not settings:
        return {
            "id": 0,
            "client_id": client_id,
            "company_display_name": None,
            "ticket_footer_text": None,
            "catalog_source": "pos",
            "catalog_integration_url": None,
            "print_document_type": "ticket",
            "ticket_template_name": None,
            "sales_note_template_name": None,
            "default_tax_percent": 0.0,
            "default_ticket_cfdi_use": "S01",
            "default_ticket_tax_regime": "616",
            "sales_note_text_default": None,
            "sales_note_extra_text": None,
            "sales_note_services_label": None,
        }

    catalog_source = (settings.catalog_source or "pos").strip().lower()
    if catalog_source not in {"pos", "stocks"}:
        catalog_source = "pos"

    print_document_type = (settings.print_document_type or "ticket").strip().lower()
    if print_document_type not in {"ticket", "sales_note"}:
        print_document_type = "ticket"

    return {
        "id": settings.id,
        "client_id": settings.client_id,
        "company_display_name": settings.company_display_name,
        "ticket_footer_text": settings.ticket_footer_text,
        "catalog_source": catalog_source,
        "catalog_integration_url": settings.catalog_integration_url,
        "print_document_type": print_document_type,
        "ticket_template_name": settings.ticket_template_name,
        "sales_note_template_name": settings.sales_note_template_name,
        "default_tax_percent": float(settings.default_tax_percent or 0.0),
        "default_ticket_cfdi_use": settings.default_ticket_cfdi_use or "S01",
        "default_ticket_tax_regime": settings.default_ticket_tax_regime or "616",
        "sales_note_text_default": settings.sales_note_text_default,
        "sales_note_extra_text": settings.sales_note_extra_text,
        "sales_note_services_label": settings.sales_note_services_label,
    }


@router.put("/api/pos-settings")
def save_pos_settings(
    payload: PosClientSettingsUpsert,
    request: Request,
    user: str = Depends(verify_token),
    pos_db: Session = Depends(get_pos_db),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
):
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    if not app_id or not client_id:
        raise HTTPException(status_code=400, detail="Faltan app_id o client_id")

    _require_pos_config_write_access(request, user, app_id, client_id, authorization)

    company_display_name = (payload.company_display_name or "").strip() or None
    ticket_footer_text = (payload.ticket_footer_text or "").strip() or None

    catalog_source = (payload.catalog_source or "pos").strip().lower()
    if catalog_source not in {"pos", "stocks"}:
        raise HTTPException(status_code=400, detail="catalog_source inválido. Permitidos: pos, stocks")

    catalog_integration_url = (payload.catalog_integration_url or "").strip() or None

    print_document_type = (payload.print_document_type or "ticket").strip().lower()
    if print_document_type not in {"ticket", "sales_note"}:
        raise HTTPException(status_code=400, detail="print_document_type inválido. Permitidos: ticket, sales_note")

    ticket_template_name = (payload.ticket_template_name or "").strip() or None
    sales_note_template_name = (payload.sales_note_template_name or "").strip() or None

    default_tax_percent = float(payload.default_tax_percent or 0.0)
    if default_tax_percent < 0:
        raise HTTPException(status_code=400, detail="default_tax_percent no puede ser negativo")

    default_ticket_cfdi_use = (payload.default_ticket_cfdi_use or "S01").strip() or "S01"
    default_ticket_tax_regime = (payload.default_ticket_tax_regime or "616").strip() or "616"

    sales_note_text_default = (payload.sales_note_text_default or "").strip() or None
    sales_note_extra_text = (payload.sales_note_extra_text or "").strip() or None
    sales_note_services_label = (payload.sales_note_services_label or "").strip() or None

    settings = (
        pos_db.query(PosClientSettings)
        .filter(PosClientSettings.client_id == client_id)
        .first()
    )

    if not settings:
        settings = PosClientSettings(
            client_id=client_id,
            company_display_name=company_display_name,
            ticket_footer_text=ticket_footer_text,
            catalog_source=catalog_source,
            catalog_integration_url=catalog_integration_url,
            print_document_type=print_document_type,
            ticket_template_name=ticket_template_name,
            sales_note_template_name=sales_note_template_name,
            default_tax_percent=default_tax_percent,
            default_ticket_cfdi_use=default_ticket_cfdi_use,
            default_ticket_tax_regime=default_ticket_tax_regime,
            sales_note_text_default=sales_note_text_default,
            sales_note_extra_text=sales_note_extra_text,
            sales_note_services_label=sales_note_services_label,
        )
        pos_db.add(settings)
    else:
        settings.company_display_name = company_display_name
        settings.ticket_footer_text = ticket_footer_text
        settings.catalog_source = catalog_source
        settings.catalog_integration_url = catalog_integration_url
        settings.print_document_type = print_document_type
        settings.ticket_template_name = ticket_template_name
        settings.sales_note_template_name = sales_note_template_name
        settings.default_tax_percent = default_tax_percent
        settings.default_ticket_cfdi_use = default_ticket_cfdi_use
        settings.default_ticket_tax_regime = default_ticket_tax_regime
        settings.sales_note_text_default = sales_note_text_default
        settings.sales_note_extra_text = sales_note_extra_text
        settings.sales_note_services_label = sales_note_services_label

    pos_db.commit()
    pos_db.refresh(settings)

    normalized_source = (settings.catalog_source or "pos").strip().lower()
    if normalized_source not in {"pos", "stocks"}:
        normalized_source = "pos"

    normalized_document_type = (settings.print_document_type or "ticket").strip().lower()
    if normalized_document_type not in {"ticket", "sales_note"}:
        normalized_document_type = "ticket"

    return {
        "ok": True,
        "message": "Configuración POS guardada correctamente.",
        "item": {
            "id": settings.id,
            "client_id": settings.client_id,
            "company_display_name": settings.company_display_name,
            "ticket_footer_text": settings.ticket_footer_text,
            "catalog_source": normalized_source,
            "catalog_integration_url": settings.catalog_integration_url,
            "print_document_type": normalized_document_type,
            "ticket_template_name": settings.ticket_template_name,
            "sales_note_template_name": settings.sales_note_template_name,
            "default_tax_percent": float(settings.default_tax_percent or 0.0),
            "default_ticket_cfdi_use": settings.default_ticket_cfdi_use or "S01",
            "default_ticket_tax_regime": settings.default_ticket_tax_regime or "616",
            "sales_note_text_default": settings.sales_note_text_default,
            "sales_note_extra_text": settings.sales_note_extra_text,
            "sales_note_services_label": settings.sales_note_services_label,
        }
    }

@router.get("/api/pos-customers", response_model=List[PosCustomerResponse])
def get_pos_customers(
    request: Request,
    search: str | None = None,
    include_inactive: bool = False,
    user: str = Depends(verify_token),
    pos_db: Session = Depends(get_pos_db),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
):
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    if not app_id or not client_id:
        raise HTTPException(status_code=400, detail="Faltan app_id o client_id")

    validate_permission(request, user, app_id, client_id, authorization)

    query = (
        pos_db.query(PosCustomer)
        .filter(PosCustomer.client_id == client_id)
    )

    if not include_inactive:
        query = query.filter(PosCustomer.is_active == True)

    if search:
        search_like = f"%{search.strip()}%"
        query = query.filter(
            (PosCustomer.rfc.ilike(search_like)) |
            (PosCustomer.business_name.ilike(search_like)) |
            (PosCustomer.contact_name.ilike(search_like))
        )

    rows = (
        query
        .order_by(PosCustomer.business_name.asc(), PosCustomer.id.asc())
        .all()
    )

    return rows

@router.post("/api/pos-customers", response_model=PosCustomerResponse)
def create_pos_customer(
    data: PosCustomerCreate,
    request: Request,
    user: str = Depends(verify_token),
    pos_db: Session = Depends(get_pos_db),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
):
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    if not app_id or not client_id:
        raise HTTPException(status_code=400, detail="Faltan app_id o client_id")

    _require_pos_customers_access(request, user, app_id, client_id, authorization)

    rfc = (data.rfc or "").strip().upper()
    business_name = (data.business_name or "").strip()

    if not rfc:
        raise HTTPException(status_code=400, detail="RFC es obligatorio")
    if not business_name:
        raise HTTPException(status_code=400, detail="Razón social / nombre es obligatorio")

    existing = (
        pos_db.query(PosCustomer)
        .filter(
            PosCustomer.client_id == client_id,
            PosCustomer.rfc == rfc,
            PosCustomer.is_active == True,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Ya existe un cliente POS activo con ese RFC")

    row = PosCustomer(
        client_id=client_id,
        rfc=rfc,
        business_name=business_name,
        contact_name=(data.contact_name or "").strip() or None,
        phone=(data.phone or "").strip() or None,
        email=(data.email or "").strip() or None,
        address=(data.address or "").strip() or None,
        postal_code=(data.postal_code or "").strip() or None,
        tax_regime=(data.tax_regime or "").strip() or None,
        cfdi_use=(data.cfdi_use or "").strip() or None,
        is_active=True,
        created_by=user,
    )

    pos_db.add(row)
    pos_db.commit()
    pos_db.refresh(row)
    return row

@router.put("/api/pos-customers/{customer_id}", response_model=PosCustomerResponse)
def update_pos_customer(
    customer_id: int,
    data: PosCustomerUpdate,
    request: Request,
    user: str = Depends(verify_token),
    pos_db: Session = Depends(get_pos_db),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
):
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    if not app_id or not client_id:
        raise HTTPException(status_code=400, detail="Faltan app_id o client_id")

    _require_pos_customers_access(request, user, app_id, client_id, authorization)

    row = (
        pos_db.query(PosCustomer)
        .filter(
            PosCustomer.id == customer_id,
            PosCustomer.client_id == client_id,
        )
        .first()
    )
    
    if not row:
        raise HTTPException(status_code=404, detail="Cliente POS no encontrado")

    if data.rfc is not None:
        new_rfc = data.rfc.strip().upper()
        if not new_rfc:
            raise HTTPException(status_code=400, detail="RFC no puede quedar vacío")

        duplicate = (
            pos_db.query(PosCustomer)
            .filter(
                PosCustomer.client_id == client_id,
                PosCustomer.rfc == new_rfc,
                PosCustomer.id != customer_id,
                PosCustomer.is_active == True,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=400, detail="Ya existe otro cliente POS activo con ese RFC")

        row.rfc = new_rfc

    if data.business_name is not None:
        business_name = data.business_name.strip()
        if not business_name:
            raise HTTPException(status_code=400, detail="Razón social / nombre no puede quedar vacío")
        row.business_name = business_name

    if data.contact_name is not None:
        row.contact_name = data.contact_name.strip() or None

    if data.phone is not None:
        row.phone = data.phone.strip() or None

    if data.email is not None:
        row.email = data.email.strip() or None

    if data.address is not None:
        row.address = data.address.strip() or None

    if data.postal_code is not None:
        row.postal_code = data.postal_code.strip() or None

    if data.tax_regime is not None:
        row.tax_regime = data.tax_regime.strip() or None

    if data.cfdi_use is not None:
        row.cfdi_use = data.cfdi_use.strip() or None

    if data.is_active is not None:
        row.is_active = bool(data.is_active)

    pos_db.commit()
    pos_db.refresh(row)
    return row

