from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from auth import verify_token
from collections import defaultdict
from db import PosPrice, Product, Category, get_pos_db, PosCustomer
from permissions import resolve_context, validate_permission, get_role_info
from pos_helpers import (
    get_catalog_source,
    get_client_settings,
    require_catalog_integration_url,
    fetch_stocks_items,
    resolve_outbound_authorization,
)

router = APIRouter(prefix="/api")


def _require_catalog_write_access(
    request: Request,
    user: str,
    app_id: int,
    client_id: int,
    authorization: str | None,
):
    role_info = get_role_info(request, app_id, client_id, authorization)
    if not role_info.get("can_manage_catalogs", False):
        raise HTTPException(
            status_code=403,
            detail="No tienes permisos para modificar catálogos del POS.",
        )


@router.get("/catalog-items")
def get_catalog_items(
    request: Request,
    user: str = Depends(verify_token),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
    db: Session = Depends(get_pos_db),
):
    """
    Catálogo base para altas manuales del catálogo comercial.

    Regla oficial actual:
    - catalog_source = pos    -> consumir Product vivo del POS
    - catalog_source = stocks -> consumir Stocks API viva
    """
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    validate_permission(request, user, app_id, client_id, authorization)

    catalog_source = get_catalog_source(db, client_id)

    if catalog_source == "pos":
        products = (
            db.query(Product)
            .filter(Product.client_id == client_id)
            .order_by(Product.id.asc())
            .all()
        )

        category_ids = list({p.category_id for p in products if p.category_id is not None})
        categories_map = {}

        if category_ids:
            categories = (
                db.query(Category)
                .filter(
                    Category.client_id == client_id,
                    Category.id.in_(category_ids),
                )
                .all()
            )
            categories_map = {c.id: c.name for c in categories}

        result = []
        for product in products:
            result.append(
                {
                    "id": product.id,
                    "client_id": product.client_id,
                    "name": product.name,
                    "sku": product.sku,
                    "category_id": product.category_id,
                    "category_name": categories_map.get(product.category_id) if product.category_id else None,
                    "product_type": product.product_type or "physical",
                    "inventory_mode": product.inventory_mode,
                    "stock_item_id": product.stock_item_id,
                    "is_active": bool(product.is_active),
                    "catalog_source": "pos",
                }
            )

        return result

    # catalog_source = stocks -> API viva con URL explícita por cliente
    catalog_integration_url = require_catalog_integration_url(db, client_id)
    outbound_authorization = resolve_outbound_authorization(request, authorization)
    stock_items = fetch_stocks_items(
        catalog_integration_url,
        outbound_authorization,
        app_id,
        client_id,
    )

    result = []
    for item in stock_items:
        item_id = item.get("id")
        if not item_id:
            continue

        result.append(
            {
                "id": item_id,
                "client_id": item.get("client_id", client_id),
                "name": item.get("name"),
                "sku": item.get("sku"),
                "category_id": item.get("category_id"),
                "category_name": item.get("category_name"),
                "product_type": item.get("item_type") or "physical",
                "inventory_mode": "stocks_api",
                "stock_item_id": item_id,
                "is_active": bool(item.get("is_active", True)),
                "catalog_source": "stocks",
            }
        )

    return result


@router.get("/catalog-items/in-prices")
def get_catalog_items_in_prices(
    request: Request,
    user: str = Depends(verify_token),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
    db: Session = Depends(get_pos_db),
):
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    validate_permission(request, user, app_id, client_id, authorization)

    items = (
        db.query(PosPrice)
        .filter(PosPrice.client_id == client_id)
        .order_by(PosPrice.id.asc())
        .all()
    )

    return [
        {
            "id": item.id,
            "catalog_item_id": item.catalog_item_id,
            "catalog_source": (item.catalog_source or "pos").strip().lower(),
        }
        for item in items
    ]


@router.get("/pos-prices")
def get_pos_prices(
    request: Request,
    user: str = Depends(verify_token),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
    db: Session = Depends(get_pos_db),
):
    """
    Regla oficial:
    - La tabla del modal SIEMPRE muestra pos_prices del cliente.
    - catalog_source=pos => enriquece desde Product vivo.
    - catalog_source=stocks => enriquece desde Stocks API viva cuando sea posible.
      Si el item ya no existe en Stocks, conserva snapshots SOLO para mostrar bitácora comercial.
    """
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    validate_permission(request, user, app_id, client_id, authorization)

    items = (
        db.query(PosPrice)
        .filter(PosPrice.client_id == client_id)
        .order_by(PosPrice.id.asc())
        .all()
    )

    pos_product_ids = list(
        {
            item.catalog_item_id
            for item in items
            if (item.catalog_source or "pos").strip().lower() == "pos"
            and item.catalog_item_id is not None
        }
    )

    stocks_item_ids = list(
        {
            item.catalog_item_id
            for item in items
            if (item.catalog_source or "pos").strip().lower() == "stocks"
            and item.catalog_item_id is not None
        }
    )

    products_map = {}
    categories_map = {}
    stocks_items_map = {}

    if pos_product_ids:
        products = (
            db.query(Product)
            .filter(
                Product.client_id == client_id,
                Product.id.in_(pos_product_ids),
            )
            .all()
        )
        products_map = {p.id: p for p in products}

        category_ids = list({p.category_id for p in products if p.category_id is not None})
        if category_ids:
            categories = (
                db.query(Category)
                .filter(
                    Category.client_id == client_id,
                    Category.id.in_(category_ids),
                )
                .all()
            )
            categories_map = {c.id: c.name for c in categories}

    if stocks_item_ids:
        catalog_integration_url = require_catalog_integration_url(db, client_id)
        outbound_authorization = resolve_outbound_authorization(request, authorization)
        stock_items = fetch_stocks_items(
            catalog_integration_url,
            outbound_authorization,
            app_id,
            client_id,
        )
        stocks_items_map = {
            int(si.get("id")): si
            for si in stock_items
            if si.get("id") is not None
        }
        
    result = []

    for item in items:
        catalog_source = (item.catalog_source or "pos").strip().lower()

        if catalog_source == "pos":
            product = products_map.get(item.catalog_item_id) if item.catalog_item_id is not None else None

            result.append(
                {
                    "id": item.id,
                    "client_id": item.client_id,
                    "catalog_item_id": item.catalog_item_id,
                    "catalog_source": "pos",
                    "sale_price": float(item.sale_price or 0),
                    "tax_percent": float(item.tax_percent or 0),
                    "is_active": bool(item.is_active),
                    

                    # Fuente operativa viva
                    "product_name": product.name if product else None,
                    "sku": product.sku if product else None,
                    "category_id": product.category_id if product else None,
                    "category_name": categories_map.get(product.category_id) if product and product.category_id else None,
                    "product_type": (product.product_type or "physical") if product else None,
                    "inventory_mode": product.inventory_mode if product else None,
                    "stock_item_id": product.stock_item_id if product else None,
                    "product_is_active": bool(product.is_active) if product else None,

                    # Inconsistencia referencial
                    "product_missing": product is None,
                }
            )
            continue

        stock_item = stocks_items_map.get(item.catalog_item_id) if item.catalog_item_id is not None else None

        if stock_item:
            result.append(
                {
                    "id": item.id,
                    "client_id": item.client_id,
                    "catalog_item_id": item.catalog_item_id,
                    "catalog_source": "stocks",
                    "sale_price": float(item.sale_price or 0),
                    "tax_percent": float(item.tax_percent or 0),    
                    "is_active": bool(item.is_active),

                    # Fuente viva Stocks
                    "product_name": stock_item.get("name"),
                    "sku": stock_item.get("sku"),
                    "category_id": stock_item.get("category_id"),
                    "category_name": stock_item.get("category_name"),
                    "product_type": stock_item.get("item_type") or "physical",
                    "inventory_mode": "stocks_api",
                    "stock_item_id": stock_item.get("id"),
                    "product_is_active": bool(stock_item.get("is_active", True)),
                    "product_missing": False,
                    "integration_error": False,
                }
            )
            continue

        # Fallback comercial válido:
        # Si el item ya no existe en Stocks, pos_prices sigue mandando.
        # Usamos snapshot como representación comercial de respaldo.
        result.append(
            {
                "id": item.id,
                "client_id": item.client_id,
                "catalog_item_id": item.catalog_item_id,
                "catalog_source": "stocks",
                "sale_price": float(item.sale_price or 0),
                "tax_percent": float(item.tax_percent or 0),
                "is_active": bool(item.is_active),

                # Representación comercial fallback (no origen vivo)
                "product_name": item.display_name_snapshot or f"Item {item.catalog_item_id}",
                "sku": item.sku_snapshot,
                "category_id": None,
                "category_name": item.category_name_snapshot,
                "product_type": item.product_type_snapshot or "physical",
                "inventory_mode": item.inventory_mode_snapshot,
                "stock_item_id": item.stock_item_id_snapshot,
                "product_is_active": None,

                # Estado real
                "product_missing": True,
                "integration_error": False,

                # Señal explícita para UI
                "using_snapshot_fallback": True,

                # Snapshots explícitos (compatibilidad / auditoría)
                "snapshot_product_name": item.display_name_snapshot,
                "snapshot_sku": item.sku_snapshot,
                "snapshot_category_name": item.category_name_snapshot,
                "snapshot_product_type": item.product_type_snapshot,
                "snapshot_inventory_mode": item.inventory_mode_snapshot,
                "snapshot_stock_item_id": item.stock_item_id_snapshot,
            }
        )

    return result


@router.post("/pos-prices")
def create_pos_price(
    payload: dict,
    request: Request,
    user: str = Depends(verify_token),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
    db: Session = Depends(get_pos_db),
):
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    _require_catalog_write_access(request, user, app_id, client_id, authorization)

    catalog_item_id = payload.get("catalog_item_id")
    if not catalog_item_id:
        raise HTTPException(status_code=400, detail="catalog_item_id es requerido.")

    catalog_source = str(payload.get("catalog_source") or "pos").strip().lower()

    if catalog_source not in {"pos", "stocks"}:
        raise HTTPException(
            status_code=400,
            detail="catalog_source inválido. Solo se permite 'pos' o 'stocks'.",
        )

    # Validar contra configuración real del cliente
    current_catalog_source = get_catalog_source(db, client_id)
    if current_catalog_source != catalog_source:
        raise HTTPException(
            status_code=409,
            detail="La configuración actual del cliente no coincide con el origen del catálogo comercial.",
        )

    existing = (
        db.query(PosPrice)
        .filter(
            PosPrice.client_id == client_id,
            PosPrice.catalog_source == catalog_source,
            PosPrice.catalog_item_id == catalog_item_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Ese producto base ya existe en el catálogo comercial.",
        )

    if catalog_source == "pos":
        product = (
            db.query(Product)
            .filter(
                Product.client_id == client_id,
                Product.id == int(catalog_item_id),
            )
            .first()
        )

        if not product:
            raise HTTPException(
                status_code=404,
                detail="El producto base de POS no existe para este cliente.",
            )

        category_name = None
        if product.category_id is not None:
            category = (
                db.query(Category)
                .filter(
                    Category.client_id == client_id,
                    Category.id == product.category_id,
                )
                .first()
            )
            category_name = category.name if category else None

        item = PosPrice(
            client_id=client_id,
            catalog_item_id=int(catalog_item_id),
            sale_price=payload.get("sale_price", 0),
            is_active=bool(payload.get("is_active", True)),
            catalog_source="pos",
            tax_percent=payload.get("tax_percent", 0),

            # Snapshot solo de compatibilidad / trazabilidad
            display_name_snapshot=product.name or f"Producto {catalog_item_id}",
            sku_snapshot=product.sku,
            category_name_snapshot=category_name,
            product_type_snapshot=product.product_type or "physical",
            inventory_mode_snapshot=product.inventory_mode,
            stock_item_id_snapshot=product.stock_item_id,
        )
    else:
        # Resolver item vivo desde Stocks API (SIN snapshots operativos como origen)
        catalog_integration_url = require_catalog_integration_url(db, client_id)
        outbound_authorization = resolve_outbound_authorization(request, authorization)
        stock_items = fetch_stocks_items(
            catalog_integration_url,
            outbound_authorization,
            app_id,
            client_id,
        )
        stock_item = next(
            (si for si in stock_items if str(si.get("id")) == str(catalog_item_id)),
            None,
        )

        if not stock_item:
            raise HTTPException(
                status_code=404,
                detail="El item de Stocks no existe o no está disponible para este cliente.",
            )

        item = PosPrice(
            client_id=client_id,
            catalog_item_id=int(catalog_item_id),
            sale_price=payload.get("sale_price", 0),
            is_active=bool(payload.get("is_active", True)),
            catalog_source="stocks",
            tax_percent=payload.get("tax_percent",0.0),

            # Snapshot solo de compatibilidad / trazabilidad
            display_name_snapshot=stock_item.get("name") or f"Item {catalog_item_id}",
            sku_snapshot=stock_item.get("sku"),
            category_name_snapshot=stock_item.get("category_name"),
            product_type_snapshot=stock_item.get("item_type") or "physical",
            inventory_mode_snapshot="stocks_api",
            stock_item_id_snapshot=stock_item.get("id"),
        )

    db.add(item)
    db.commit()
    db.refresh(item)

    return {"ok": True, "item_id": item.id}


@router.put("/pos-prices/{price_id}")
def update_pos_price(
    price_id: int,
    payload: dict,
    request: Request,
    user: str = Depends(verify_token),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
    db: Session = Depends(get_pos_db),
):
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    _require_catalog_write_access(request, user, app_id, client_id, authorization)

    item = (
        db.query(PosPrice)
        .filter(
            PosPrice.id == price_id,
            PosPrice.client_id == client_id,
        )
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Registro de precio no encontrado.")

    if "sale_price" in payload:
        item.sale_price = payload["sale_price"]
    
    if "tax_percent" in payload:
        item.tax_percent = payload["tax_percent"]

    if "is_active" in payload:
        item.is_active = bool(payload["is_active"])

    db.commit()
    db.refresh(item)

    return {"ok": True, "item_id": item.id}


@router.get("/sale-products")
def get_sale_products(
    request: Request,
    user: str = Depends(verify_token),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
    db: Session = Depends(get_pos_db),
):
    """
    Catálogo principal de venta (regla oficial INV-3B.3 / pre-INV-4A)

    Fuente maestra:
    - SIEMPRE parte de pos_prices del cliente
    - SOLO registros activos en pos_prices (is_active = true)

    Reglas:
    - Si está activo en pos_prices, SE MUESTRA
    - product.is_active NO manda la visibilidad comercial
    - sale_price=0 es válido
    - Servicios se pueden vender aunque no tengan stock
    - Físicos sin stock se muestran, pero no se pueden vender
    - Si item de Stocks ya no existe:
        * se sigue mostrando si sigue activo en pos_prices
        * si es servicio -> vendible
        * si es físico -> no vendible
    """
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    validate_permission(request, user, app_id, client_id, authorization)

    prices = (
        db.query(PosPrice)
        .filter(
            PosPrice.client_id == client_id,
            PosPrice.is_active == True,
        )
        .order_by(PosPrice.id.asc())
        .all()
    )

    if not prices:
        return []

    pos_ids = list(
        {
            p.catalog_item_id
            for p in prices
            if (p.catalog_source or "pos").strip().lower() == "pos"
            and p.catalog_item_id is not None
        }
    )

    stocks_ids = list(
        {
            p.catalog_item_id
            for p in prices
            if (p.catalog_source or "pos").strip().lower() == "stocks"
            and p.catalog_item_id is not None
        }
    )

    products_map = {}
    categories_map = {}
    stocks_items_map = {}

    # POS local
    if pos_ids:
        pos_products = (
            db.query(Product)
            .filter(
                Product.client_id == client_id,
                Product.id.in_(pos_ids),
            )
            .all()
        )
        products_map = {p.id: p for p in pos_products}

        category_ids = list({p.category_id for p in pos_products if p.category_id is not None})
        if category_ids:
            categories = (
                db.query(Category)
                .filter(
                    Category.client_id == client_id,
                    Category.id.in_(category_ids),
                )
                .all()
            )
            categories_map = {c.id: c.name for c in categories}

    # Stocks API
    if stocks_ids:
        catalog_integration_url = require_catalog_integration_url(db, client_id)
        outbound_authorization = resolve_outbound_authorization(request, authorization)
        stock_items = fetch_stocks_items(
            catalog_integration_url,
            outbound_authorization,
            app_id,
            client_id,
        )
        stocks_items_map = {
            int(item.get("id")): item
            for item in stock_items
            if item.get("id") is not None
        }

    result = []

    for price in prices:
        catalog_source = (price.catalog_source or "pos").strip().lower()

        if catalog_source == "pos":
            product = products_map.get(price.catalog_item_id) if price.catalog_item_id is not None else None

            if product:
                product_type = (product.product_type or "physical").strip().lower()
                stock_qty = float(product.stock_quantity or 0)
                source_exists = True

                product_name = product.name
                sku = product.sku
                category_id = product.category_id
                category_name = categories_map.get(product.category_id) if product.category_id else None
                stock_item_id = product.stock_item_id
                source_is_active = bool(product.is_active)
            else:
                # Si POS local ya no existe, fallback comercial visual (sin usar snapshot como fuente operativa)
                product_type = (price.product_type_snapshot or "physical").strip().lower()
                stock_qty = 0.0
                source_exists = False

                product_name = price.display_name_snapshot or f"Producto {price.catalog_item_id}"
                sku = price.sku_snapshot
                category_id = None
                category_name = price.category_name_snapshot
                stock_item_id = price.stock_item_id_snapshot
                source_is_active = None

            if product_type == "service":
                sellable_now = True
                disabled_reason = None
            else:
                sellable_now = stock_qty > 0
                disabled_reason = None if sellable_now else "Sin existencia"

            result.append(
                {
                    "id": price.id,
                    "price_id": price.id,
                    "client_id": price.client_id,
                    "catalog_item_id": price.catalog_item_id,
                    "catalog_source": "pos",
                    "sale_price": float(price.sale_price or 0),
                    "price": float(price.sale_price or 0),

                    "name": product_name,
                    "product_name": product_name,
                    "sku": sku,
                    "category_id": category_id,
                    "category_name": category_name,

                    "product_type": product_type,
                    "stock_item_id": stock_item_id,
                    "stock_quantity": stock_qty,

                    "source_exists": source_exists,
                    "source_is_active": source_is_active,

                    "is_active": True,  # viene filtrado desde pos_prices
                    "sellable_now": sellable_now,
                    "disabled_reason": disabled_reason,
                }
            )
            continue

        # catalog_source = stocks
        stock_item = stocks_items_map.get(price.catalog_item_id) if price.catalog_item_id is not None else None

        if stock_item:
            product_type = (stock_item.get("item_type") or "physical").strip().lower()

            on_hand_qty = float(stock_item.get("on_hand_qty") or 0)
            reserved_qty = float(stock_item.get("reserved_qty") or 0)
            stock_qty = max(on_hand_qty - reserved_qty, 0)

            product_name = stock_item.get("name")
            sku = stock_item.get("sku")
            category_id = stock_item.get("category_id")
            category_name = stock_item.get("category_name")
            stock_item_id = stock_item.get("id")
            source_exists = True
            source_is_active = bool(stock_item.get("is_active", True))
        else:
            # Item ya no existe en Stocks, pero pos_prices sigue mandando
            product_type = (price.product_type_snapshot or "physical").strip().lower()

            on_hand_qty = 0.0
            reserved_qty = 0.0
            stock_qty = 0.0

            product_name = price.display_name_snapshot or f"Item {price.catalog_item_id}"
            sku = price.sku_snapshot
            category_id = None
            category_name = price.category_name_snapshot
            stock_item_id = price.stock_item_id_snapshot

            source_exists = False
            source_is_active = None

        if product_type == "service":
            sellable_now = True
            disabled_reason = None
        else:
            sellable_now = stock_qty > 0
            disabled_reason = None if sellable_now else "Sin existencia"

        result.append(
            {
                "id": price.id,
                "price_id": price.id,
                "client_id": price.client_id,
                "catalog_item_id": price.catalog_item_id,
                "catalog_source": "stocks",
                "sale_price": float(price.sale_price or 0),
                "price": float(price.sale_price or 0),

                "name": product_name,
                "product_name": product_name,
                "sku": sku,
                "category_id": category_id,
                "category_name": category_name,

                "product_type": product_type,
                "stock_item_id": stock_item_id,

                "on_hand_qty": on_hand_qty,
                "reserved_qty": reserved_qty,
                "stock_quantity": stock_qty,

                "source_exists": source_exists,
                "source_is_active": source_is_active,

                "is_active": True,  # viene filtrado desde pos_prices
                "sellable_now": sellable_now,
                "disabled_reason": disabled_reason,
            }
        )

    return result


@router.get("/catalog-settings")
def get_catalog_settings(
    request: Request,
    user: str = Depends(verify_token),
    authorization: str | None = Header(default=None),
    x_app_id: int | None = Header(alias="X-App-Id", default=None),
    x_client_id: int | None = Header(alias="X-Client-Id", default=None),
    db: Session = Depends(get_pos_db),
):
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)
    validate_permission(request, user, app_id, client_id, authorization)

    settings = get_client_settings(db, client_id)

    if not settings:
        return {
            "client_id": client_id,
            "company_display_name": None,
            "ticket_footer_text": None,

            "catalog_source": "pos",
            "catalog_integration_url": None,
            "stocks_service_configured": False,

            "allow_manual_create": False,
            "allow_price_edit": True,
            "allow_status_toggle": True,

            # INV-5A documental
            "print_document_type": "ticket",
            "ticket_template_name": "ticket_default.html",
            "sales_note_template_name": "default.html",

            "default_tax_percent": 0.0,
            "default_ticket_cfdi_use": "S01",
            "default_ticket_tax_regime": "616",
            "default_customer_id": None,

            "sales_note_text_default": None,
            "sales_note_extra_text": None,
            "sales_note_services_label": None,
        }

    catalog_source = (getattr(settings, "catalog_source", None) or "pos").strip().lower()
    if catalog_source not in {"pos", "stocks"}:
        catalog_source = "pos"

    print_document_type = (getattr(settings, "print_document_type", None) or "ticket").strip().lower()
    if print_document_type not in {"ticket", "sales_note"}:
        print_document_type = "ticket"

    ticket_template_name = (getattr(settings, "ticket_template_name", None) or "").strip() or "ticket_default.html"
    sales_note_template_name = (getattr(settings, "sales_note_template_name", None) or "").strip() or "default.html"

    catalog_integration_url = (getattr(settings, "catalog_integration_url", None) or "").strip() or None
    
    default_customer_id = getattr(settings, "default_customer_id", None)

    default_customer = None
    default_customer_name = None

    if default_customer_id:
        default_customer = (
            db.query(PosCustomer)
            .filter(
                PosCustomer.client_id == client_id,
                PosCustomer.id == default_customer_id,
            )
            .first()
        )

        if default_customer:
            default_customer_name = (
                default_customer.business_name
                or default_customer.contact_name
                or f"Cliente {default_customer.id}"
            )

    return {
        "client_id": client_id,
        "company_display_name": (getattr(settings, "company_display_name", None) or "").strip() or None,
        "ticket_footer_text": (getattr(settings, "ticket_footer_text", None) or "").strip() or None,

        "catalog_source": catalog_source,
        "catalog_integration_url": catalog_integration_url,
        "stocks_service_configured": bool(catalog_integration_url) if catalog_source == "stocks" else False,

        "allow_manual_create": catalog_source == "stocks",
        "allow_price_edit": True,
        "allow_status_toggle": True,

        # INV-5A documental
        "print_document_type": print_document_type,
        "ticket_template_name": ticket_template_name,
        "sales_note_template_name": sales_note_template_name,

        "default_tax_percent": float(getattr(settings, "default_tax_percent", 0.0) or 0.0),
        "default_ticket_cfdi_use": (getattr(settings, "default_ticket_cfdi_use", None) or "S01").strip() or "S01",
        "default_ticket_tax_regime": (getattr(settings, "default_ticket_tax_regime", None) or "616").strip() or "616",
        "default_customer_id": (default_customer_id or None),
        "default_customer_name": (default_customer_name or None),

        "sales_note_text_default": (getattr(settings, "sales_note_text_default", None) or "").strip() or None,
        "sales_note_extra_text": (getattr(settings, "sales_note_extra_text", None) or "").strip() or None,
        "sales_note_services_label": (getattr(settings, "sales_note_services_label", None) or "").strip() or None,
    }