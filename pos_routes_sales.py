print("[POS] pos_routes_sales.py VERSION 2026-04-19-B")

from datetime import datetime
from fastapi import APIRouter, Depends, Request, HTTPException, Header
from sqlalchemy.orm import Session

from db import (
    get_pos_db,
    Product,
    PosPrice,
    PosClientSettings,
    PosCustomer,
    PosSalePrintData,
    Sale,
    SaleItem,
    SaleEvent,
)
from auth import verify_token
from permissions import resolve_context, validate_permission

from schemas import (
    SaleCreate,
    SaleCreatePrintData,
    SaleResponse,
    SalePrintContextResponse,
    SalePrintDataUpsert,
    SalePrintDataResponse,
)

from pos_helpers import (
    build_sale_number,
    get_catalog_source,
    get_catalog_integration_url,
    post_stocks_sale_apply,
    post_stocks_sale_cancel,
    require_pos_admin_for_sales_ops,
    resolve_outbound_authorization,
)

router = APIRouter()


def add_sale_event(
    pos_db: Session,
    *,
    sale_id: int,
    client_id: int,
    event_type: str,
    created_by: str,
    event_status: str = "ok",
    notes: str | None = None,
    reference_type: str | None = None,
    reference_id: int | None = None,
    payload_json: dict | None = None,
):
    pos_db.add(
        SaleEvent(
            sale_id=sale_id,
            client_id=client_id,
            event_type=event_type,
            event_status=event_status,
            notes=notes,
            reference_type=reference_type,
            reference_id=reference_id,
            payload_json=payload_json,
            created_by=created_by,
        )
    )


def _payment_method_label(payment_method: str | None) -> str:
    value = (payment_method or "").strip().lower()

    mapping = {
        "cash": "EFECTIVO",
        "card": "TARJETA",
        "transfer": "TRANSFERENCIA",
    }

    if value in mapping:
        return mapping[value]

    if value:
        return value.upper()

    return "EFECTIVO"


def _calculate_tax_from_included_price(line_total: float, tax_percent: float) -> float:
    line_total = float(line_total or 0.0)
    tax_percent = float(tax_percent or 0.0)

    if line_total <= 0 or tax_percent <= 0:
        return 0.0

    divisor = 1 + (tax_percent / 100.0)
    base_amount = line_total / divisor
    tax_amount = line_total - base_amount
    return float(round(tax_amount, 2))


def _calculate_base_from_included_price(line_total: float, tax_percent: float) -> float:
    line_total = float(line_total or 0.0)
    tax_percent = float(tax_percent or 0.0)

    if line_total <= 0:
        return 0.0

    if tax_percent <= 0:
        return float(round(line_total, 2))

    divisor = 1 + (tax_percent / 100.0)
    base_amount = line_total / divisor
    return float(round(base_amount, 2))


def _resolve_default_print_config(
    settings: PosClientSettings | None,
) -> tuple[str, str]:
    document_type = "ticket"
    template_name = "default.html"

    if settings:
        document_type = (settings.print_document_type or "ticket").strip().lower()
        if document_type not in {"ticket", "sales_note"}:
            document_type = "ticket"

        if document_type == "sales_note":
            template_name = (settings.sales_note_template_name or "").strip() or "sales_note_default.html"
        else:
            document_type = "ticket"
            template_name = (settings.ticket_template_name or "").strip() or "ticket_default.html"

    return document_type, template_name


def _create_default_sale_print_data(
    pos_db: Session,
    *,
    sale: Sale,
    client_id: int,
    created_by: str,
):
    settings = (
        pos_db.query(PosClientSettings)
        .filter(PosClientSettings.client_id == client_id)
        .first()
    )

    document_type, template_name = _resolve_default_print_config(settings)

    payment_method_label = _payment_method_label(sale.payment_method)

    ticket_footer_text = None
    sales_note_text = None
    sales_note_extra_text = None
    services_label = None

    if settings:
        ticket_footer_text = (settings.ticket_footer_text or "").strip() or None

        if document_type == "sales_note":
            sales_note_text = (settings.sales_note_text_default or "").strip() or None
            sales_note_extra_text = (settings.sales_note_extra_text or "").strip() or None
            services_label = (settings.sales_note_services_label or "").strip() or None

    row = PosSalePrintData(
        sale_id=sale.id,
        client_id=client_id,
        document_type=document_type,
        template_name=template_name,
        pos_customer_id=None,
        customer_rfc=None,
        customer_business_name=None,
        customer_contact_name=None,
        customer_phone=None,
        customer_email=None,
        customer_address=None,
        customer_postal_code=None,
        customer_tax_regime=None,
        customer_cfdi_use=None,
        attended_by=None,
        payment_method_label=payment_method_label,
        sales_note_text=sales_note_text,
        ticket_footer_text=ticket_footer_text,
        sales_note_extra_text=sales_note_extra_text,
        services_label=services_label,
        subtotal=float(sale.subtotal_snapshot or 0.0),
        tax_amount=float(sale.tax_amount or 0.0),
        total=float(sale.total_amount or 0.0),
        created_by=created_by,
    )

    pos_db.add(row)
    pos_db.flush()

    return row


def _create_sale_print_data_from_payload(
    pos_db: Session,
    *,
    sale: Sale,
    client_id: int,
    created_by: str,
    payload: SaleCreatePrintData,
):
    settings = (
    pos_db.query(PosClientSettings)
        .filter(PosClientSettings.client_id == client_id)
        .first()
    )

    document_type, template_name = _resolve_default_print_config(settings)
    
    print(f"[POS][DEBUG] _create_sale_print_data_from_payload sale_id={sale.id} client_id={client_id}")

    print(f"[POS][DEBUG] settings_found={bool(settings)}")
    if settings:
        print(f"[POS][DEBUG] settings.client_id={settings.client_id}")
        print(f"[POS][DEBUG] settings.print_document_type={settings.print_document_type}")
        print(f"[POS][DEBUG] settings.ticket_template_name={settings.ticket_template_name}")
        print(f"[POS][DEBUG] settings.sales_note_template_name={settings.sales_note_template_name}")

    print(f"[POS][DEBUG] resolved document_type={document_type} template_name={template_name}")

    default_ticket_cfdi_use = (
        (settings.default_ticket_cfdi_use or "").strip()
        if settings and getattr(settings, "default_ticket_cfdi_use", None)
        else "S01"
    ) or "S01"

    default_ticket_tax_regime = (
        (settings.default_ticket_tax_regime or "").strip()
        if settings and getattr(settings, "default_ticket_tax_regime", None)
        else "616"
    ) or "616"

    default_ticket_footer_text = (
        (settings.ticket_footer_text or "").strip()
        if settings and getattr(settings, "ticket_footer_text", None)
        else ""
    )

    default_sales_note_text = (
        (settings.sales_note_text_default or "").strip()
        if settings and getattr(settings, "sales_note_text_default", None)
        else ""
    )

    default_sales_note_extra_text = (
        (settings.sales_note_extra_text or "").strip()
        if settings and getattr(settings, "sales_note_extra_text", None)
        else ""
    )

    default_services_label = (
        (settings.sales_note_services_label or "").strip()
        if settings and getattr(settings, "sales_note_services_label", None)
        else ""
    )

    pos_customer = None
    pos_customer_id = payload.pos_customer_id

    if document_type == "sales_note" and not pos_customer_id:
        raise HTTPException(
            status_code=400,
            detail="Para sales_note debes enviar pos_customer_id"
        )

    if pos_customer_id:
        pos_customer = (
            pos_db.query(PosCustomer)
            .filter(
                PosCustomer.id == pos_customer_id,
                PosCustomer.client_id == client_id,
            )
            .first()
        )

        if not pos_customer:
            raise HTTPException(status_code=404, detail="Cliente POS no encontrado")

        if pos_customer.is_active is not True:
            raise HTTPException(
                status_code=400,
                detail="No se puede usar un customer inactivo para impresión"
            )

    payment_method_label = (payload.payment_method_label or "").strip() or _payment_method_label(sale.payment_method)
    attended_by = (payload.attended_by or "").strip() or None
    sales_note_text = (payload.sales_note_text or "").strip() or None
    ticket_footer_text = (payload.ticket_footer_text or "").strip() or None
    sales_note_extra_text = (payload.sales_note_extra_text or "").strip() or None
    services_label = (payload.services_label or "").strip() or None

    if ticket_footer_text is None and default_ticket_footer_text:
        ticket_footer_text = default_ticket_footer_text

    if document_type == "sales_note":
        if sales_note_text is None and default_sales_note_text:
            sales_note_text = default_sales_note_text

        if sales_note_extra_text is None and default_sales_note_extra_text:
            sales_note_extra_text = default_sales_note_extra_text

        if services_label is None and default_services_label:
            services_label = default_services_label
    else:
        sales_note_text = None
        sales_note_extra_text = None
        services_label = None

    row = PosSalePrintData(
        sale_id=sale.id,
        client_id=client_id,
        document_type=document_type,
        template_name=template_name,
        created_by=created_by,
        attended_by=attended_by,
        payment_method_label=payment_method_label,
        sales_note_text=sales_note_text,
        ticket_footer_text=ticket_footer_text,
        sales_note_extra_text=sales_note_extra_text,
        services_label=services_label,
        subtotal=float(sale.subtotal_snapshot or 0.0),
        tax_amount=float(sale.tax_amount or 0.0),
        total=float(sale.total_amount or 0.0),
    )

    if pos_customer:
        row.pos_customer_id = pos_customer.id
        row.customer_rfc = (pos_customer.rfc or "").strip().upper() or None
        row.customer_business_name = (pos_customer.business_name or "").strip() or None
        row.customer_contact_name = (pos_customer.contact_name or "").strip() or None
        row.customer_phone = (pos_customer.phone or "").strip() or None
        row.customer_email = (pos_customer.email or "").strip() or None
        row.customer_address = (pos_customer.address or "").strip() or None
        row.customer_postal_code = (pos_customer.postal_code or "").strip() or None
        row.customer_tax_regime = (pos_customer.tax_regime or "").strip() or None
        row.customer_cfdi_use = (pos_customer.cfdi_use or "").strip() or None
    else:
        row.pos_customer_id = None
        row.customer_rfc = "XAXX010101000"
        row.customer_business_name = "PÚBLICO EN GENERAL"
        row.customer_contact_name = None
        row.customer_phone = None
        row.customer_email = None
        row.customer_address = None
        row.customer_postal_code = None
        row.customer_tax_regime = default_ticket_tax_regime
        row.customer_cfdi_use = default_ticket_cfdi_use

    pos_db.add(row)
    pos_db.flush()

    return row


def _build_sale_item_response(item: SaleItem) -> dict:
    return {
        "id": item.id,
        "pos_price_id": item.pos_price_id,
        "catalog_source": item.catalog_source,
        "catalog_item_id": item.catalog_item_id,
        "product_name": item.product_name_snapshot,
        "quantity": float(item.quantity or 0.0),
        "unit_price": float(item.unit_price or 0.0),
        "tax_percent": float(item.tax_percent or 0.0),
        "total_price": float(item.total_price or 0.0),
        "catalog_source_snapshot": item.catalog_source_snapshot,
        "catalog_item_id_snapshot": item.catalog_item_id_snapshot,
        "sku_snapshot": item.sku_snapshot,
        "category_name_snapshot": item.category_name_snapshot,
        "product_type_snapshot": item.product_type_snapshot,
        "inventory_mode_snapshot": item.inventory_mode_snapshot,
        "stock_item_id_snapshot": item.stock_item_id_snapshot,
        "unit_price_snapshot": float(item.unit_price_snapshot or 0.0),
        "line_total_snapshot": float(item.line_total_snapshot or 0.0),
    }


def apply_local_sale_cancel(
    pos_db: Session,
    *,
    sale: Sale,
    client_id: int,
):
    for sale_item in sale.items:
        if (sale_item.product_type_snapshot or "physical").strip().lower() != "physical":
            continue

        if (sale_item.catalog_source_snapshot or "").strip().lower() != "pos":
            continue

        product = (
            pos_db.query(Product)
            .filter(
                Product.id == sale_item.catalog_item_id_snapshot,
                Product.client_id == client_id,
                Product.is_active == True,
            )
            .first()
        )

        if not product:
            continue

        if not bool(product.track_inventory):
            continue

        if (product.inventory_mode or "pos_legacy").strip().lower() != "pos_legacy":
            continue

        product.stock_quantity = int(product.stock_quantity or 0) + int(sale_item.quantity or 0)


@router.post("/api/sales", response_model=SaleResponse)
def create_sale(
    data: SaleCreate,
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

    if not data.items:
        raise HTTPException(status_code=400, detail="La venta debe contener al menos un producto")

    try:
        subtotal = 0.0
        discount = 0.0
        total = 0.0
        tax_total = 0.0
        sale_items = []

        for item in data.items:
            pos_price = (
                pos_db.query(PosPrice)
                .filter(
                    PosPrice.id == item.pos_price_id,
                    PosPrice.client_id == client_id,
                    PosPrice.is_active == True,
                )
                .first()
            )
            if not pos_price:
                raise HTTPException(status_code=404, detail=f"Ítem comercial {item.pos_price_id} no encontrado")

            qty = float(item.quantity)
            if qty <= 0:
                raise HTTPException(status_code=400, detail="La cantidad debe ser mayor a 0")

            unit_price = float(pos_price.sale_price or 0.0)
            item_total = float(round(unit_price * qty, 2))
            item_tax_percent = float(pos_price.tax_percent or 0.0)

            item_subtotal = _calculate_base_from_included_price(item_total, item_tax_percent)
            item_tax_amount = float(round(item_total - item_subtotal, 2))

            subtotal += item_subtotal
            total += item_total
            tax_total += item_tax_amount

            sale_items.append({
                "pos_price": pos_price,
                "quantity": qty,
                "unit_price": unit_price,              # precio unitario vendido (con IVA)
                "tax_percent": item_tax_percent,
                "tax_amount": item_tax_amount,         # IVA de la línea
                "line_subtotal": item_subtotal,        # subtotal de línea SIN IVA
                "total_price": item_total,             # total de línea CON IVA
            })

        subtotal = float(round(subtotal, 2))
        total = float(round(total, 2))
        tax_total = float(round(tax_total, 2))
        current_catalog_source = get_catalog_source(pos_db, client_id)
        current_catalog_integration_url = (
            get_catalog_integration_url(pos_db, client_id)
            if current_catalog_source == "stocks"
            else None
        )

        if current_catalog_source == "stocks" and not current_catalog_integration_url:
            raise HTTPException(
                status_code=409,
                detail="Cliente configurado con catálogo Stocks pero sin catalog_integration_url.",
            )

        outbound_authorization = resolve_outbound_authorization(request, authorization)

        catalog_source_snapshot = current_catalog_source
        catalog_integration_url_snapshot = current_catalog_integration_url

        if current_catalog_source == "pos":
            for item in sale_items:
                pos_price = item["pos_price"]

                if pos_price.catalog_source != "pos":
                    continue

                product = (
                    pos_db.query(Product)
                    .filter(
                        Product.id == pos_price.catalog_item_id,
                        Product.client_id == client_id,
                        Product.is_active == True,
                    )
                    .first()
                )

                if product:
                    if (product.product_type or "physical") == "physical" and bool(product.track_inventory):
                        if (product.inventory_mode or "pos_legacy") == "pos_legacy":
                            available = int(product.stock_quantity or 0)
                            requested = int(item["quantity"])
                            if available < requested:
                                raise HTTPException(
                                    status_code=400,
                                    detail=f"Stock insuficiente para {product.name}. Disponible: {available}",
                                )

        sale = Sale(
            sale_number=build_sale_number(),
            client_id=client_id,
            app_id=app_id,
            created_by=user,
            subtotal_snapshot=subtotal,
            discount_snapshot=discount,
            total_snapshot=total,
            customer_name_snapshot=data.customer_name,
            cashier_name_snapshot=user,
            catalog_source_snapshot=catalog_source_snapshot,
            catalog_integration_url_snapshot=catalog_integration_url_snapshot,
            total_amount=total,
            tax_amount=float(round(tax_total, 2)),
            discount_amount=0.0,
            payment_method=data.payment_method,
            notes=data.notes,
        )

        pos_db.add(sale)
        pos_db.flush()

        add_sale_event(
            pos_db,
            sale_id=sale.id,
            client_id=client_id,
            event_type="sale_created",
            created_by=user,
            notes="Venta creada en POS",
            reference_type="sale",
            reference_id=sale.id,
            payload_json={
                "sale_number": sale.sale_number,
                "catalog_source": catalog_source_snapshot,
                "total_amount": total,
                "tax_amount": float(round(tax_total, 2)),
                "items_count": len(sale_items),
            },
        )

        created_items = []
        stocks_payload_items = []
        stocks_physical_items_count = 0
        has_stocks_item_mapping_error = False

        add_sale_event(
            pos_db,
            sale_id=sale.id,
            client_id=client_id,
            event_type="inventory_apply_attempt",
            created_by=user,
            notes=(
                "Inicio de aplicación de inventario POS legacy"
                if current_catalog_source == "pos"
                else "Inicio de aplicación de inventario vía Stocks API"
            ),
            reference_type="inventory",
            reference_id=sale.id,
            payload_json={
                "mode": "pos_legacy" if current_catalog_source == "pos" else "stocks_api",
                "catalog_source": catalog_source_snapshot,
                "items_count": len(sale_items),
            },
        )

        for item in sale_items:
            pos_price = item["pos_price"]

            if current_catalog_source == "pos":
                if pos_price.catalog_source == "pos":
                    product = (
                        pos_db.query(Product)
                        .filter(
                            Product.id == pos_price.catalog_item_id,
                            Product.client_id == client_id,
                            Product.is_active == True,
                        )
                        .first()
                    )

                    if product:
                        if (product.product_type or "physical") == "physical" and bool(product.track_inventory):
                            if (product.inventory_mode or "pos_legacy") == "pos_legacy":
                                product.stock_quantity = int(product.stock_quantity or 0) - int(item["quantity"])

            sale_item = SaleItem(
                sale_id=sale.id,
                pos_price_id=pos_price.id,
                catalog_source=pos_price.catalog_source,
                catalog_item_id=pos_price.catalog_item_id,
                catalog_source_snapshot=pos_price.catalog_source,
                catalog_item_id_snapshot=pos_price.catalog_item_id,
                product_name_snapshot=pos_price.display_name_snapshot,
                sku_snapshot=pos_price.sku_snapshot,
                category_name_snapshot=pos_price.category_name_snapshot,
                product_type_snapshot=pos_price.product_type_snapshot,
                inventory_mode_snapshot=pos_price.inventory_mode_snapshot,
                stock_item_id_snapshot=pos_price.stock_item_id_snapshot,
                quantity=item["quantity"],
                unit_price_snapshot=item["unit_price"],          # precio unitario vendido (con IVA)
                line_total_snapshot=item["line_subtotal"],       # subtotal de línea SIN IVA
                unit_price=item["unit_price"],                   # precio unitario vendido (con IVA)
                tax_percent=item["tax_percent"],
                total_price=item["total_price"],                 # total de línea CON IVA
            )
            pos_db.add(sale_item)
            pos_db.flush()

            if current_catalog_source == "pos":
                add_sale_event(
                    pos_db,
                    sale_id=sale.id,
                    client_id=client_id,
                    event_type="inventory_process_success",
                    created_by=user,
                    notes=f"Inventario aplicado para item comercial {pos_price.id}",
                    reference_type="sale_item",
                    reference_id=sale_item.id,
                    payload_json={
                        "pos_price_id": pos_price.id,
                        "catalog_source": pos_price.catalog_source,
                        "catalog_item_id": pos_price.catalog_item_id,
                        "quantity": item["quantity"],
                        "product_name": pos_price.display_name_snapshot,
                        "inventory_mode": pos_price.inventory_mode_snapshot,
                        "stock_item_id_snapshot": pos_price.stock_item_id_snapshot,
                    },
                )
            else:
                product_type = (pos_price.product_type_snapshot or "physical").strip().lower()

                if product_type != "physical":
                    add_sale_event(
                        pos_db,
                        sale_id=sale.id,
                        client_id=client_id,
                        event_type="inventory_process_success",
                        created_by=user,
                        notes=f"Sin afectación de inventario para item comercial {pos_price.id}",
                        reference_type="sale_item",
                        reference_id=sale_item.id,
                        payload_json={
                            "pos_price_id": pos_price.id,
                            "catalog_source": pos_price.catalog_source,
                            "catalog_item_id": pos_price.catalog_item_id,
                            "quantity": item["quantity"],
                            "product_name": pos_price.display_name_snapshot,
                            "inventory_mode": pos_price.inventory_mode_snapshot,
                            "stock_item_id_snapshot": pos_price.stock_item_id_snapshot,
                            "reason": "non_physical",
                        },
                    )
                else:
                    stocks_physical_items_count += 1

                    if not pos_price.stock_item_id_snapshot:
                        has_stocks_item_mapping_error = True

                        add_sale_event(
                            pos_db,
                            sale_id=sale.id,
                            client_id=client_id,
                            event_type="inventory_apply_failed",
                            created_by=user,
                            event_status="error",
                            notes=f"Ítem comercial {pos_price.id} sin stock_item_id para Stocks",
                            reference_type="sale_item",
                            reference_id=sale_item.id,
                            payload_json={
                                "pos_price_id": pos_price.id,
                                "catalog_source": pos_price.catalog_source,
                                "catalog_item_id": pos_price.catalog_item_id,
                                "quantity": item["quantity"],
                                "product_name": pos_price.display_name_snapshot,
                            },
                        )
                    else:
                        stocks_payload_items.append(
                            {
                                "stock_item_id": int(pos_price.stock_item_id_snapshot),
                                "quantity": float(item["quantity"]),
                            }
                        )

            created_items.append(_build_sale_item_response(sale_item))

        if current_catalog_source == "stocks":
            if has_stocks_item_mapping_error:
                sale.status = "pending_inventory"

                add_sale_event(
                    pos_db,
                    sale_id=sale.id,
                    client_id=client_id,
                    event_type="sale_pending_inventory",
                    created_by=user,
                    event_status="warning",
                    notes="Venta registrada con pendiente de inventario en Stocks por items sin stock_item_id",
                    reference_type="sale",
                    reference_id=sale.id,
                    payload_json={
                        "sale_number": sale.sale_number,
                        "reason": "missing_stock_item_id",
                        "items_count": len(stocks_payload_items),
                    },
                )

            elif stocks_physical_items_count > 0:
                try:
                    stocks_result = post_stocks_sale_apply(
                        catalog_integration_url=current_catalog_integration_url,
                        authorization=outbound_authorization,
                        app_id=app_id,
                        client_id=client_id,
                        payload={
                            "movement_type": "sale_exit",
                            "reference_type": "pos_sale",
                            "reference_id": sale.id,
                            "source_app": "rodelsoft-pos",
                            "source_app_id": app_id,
                            "notes": data.notes or f"Venta POS {sale.sale_number}",
                            "items": stocks_payload_items,
                        },
                    )

                    add_sale_event(
                        pos_db,
                        sale_id=sale.id,
                        client_id=client_id,
                        event_type="inventory_process_success",
                        created_by=user,
                        notes="Inventario aplicado correctamente en Stocks API",
                        reference_type="inventory",
                        reference_id=sale.id,
                        payload_json={
                            "mode": "stocks_api",
                            "items_count": len(stocks_payload_items),
                            "stocks_result": stocks_result,
                        },
                    )

                    sale.status = "completed"

                except HTTPException as exc:
                    sale.status = "pending_inventory"

                    add_sale_event(
                        pos_db,
                        sale_id=sale.id,
                        client_id=client_id,
                        event_type="inventory_apply_failed",
                        created_by=user,
                        event_status="error",
                        notes=str(exc.detail),
                        reference_type="inventory",
                        reference_id=sale.id,
                        payload_json={
                            "mode": "stocks_api",
                            "items_count": len(stocks_payload_items),
                        },
                    )

                    add_sale_event(
                        pos_db,
                        sale_id=sale.id,
                        client_id=client_id,
                        event_type="sale_pending_inventory",
                        created_by=user,
                        event_status="warning",
                        notes="Venta registrada con pendiente de inventario en Stocks",
                        reference_type="sale",
                        reference_id=sale.id,
                        payload_json={
                            "sale_number": sale.sale_number,
                            "reason": "stocks_api_failed",
                            "items_count": len(stocks_payload_items),
                        },
                    )

            else:
                sale.status = "completed"

                add_sale_event(
                    pos_db,
                    sale_id=sale.id,
                    client_id=client_id,
                    event_type="inventory_process_success",
                    created_by=user,
                    notes="Venta sin artículos físicos para afectar en Stocks",
                    reference_type="inventory",
                    reference_id=sale.id,
                    payload_json={
                        "mode": "stocks_api",
                        "items_count": 0,
                    },
                )

        else:
            sale.status = "completed"

        print(f"[POS][DEBUG]antes create_sale sale_id={sale.id} client_id={client_id} has_print_data={bool(data.print_data)}")
        if data.print_data:
            print(f"[POS][DEBUG]entra create_sale sale_id={sale.id} client_id={client_id} has_print_data={bool(data.print_data)}")
            _create_sale_print_data_from_payload(
                pos_db,
                sale=sale,
                client_id=client_id,
                created_by=user,
                payload=data.print_data,
            )
        else:
            _create_default_sale_print_data(
                pos_db,
                sale=sale,
                client_id=client_id,
                created_by=user,
            )
        
        if sale.status == "completed":
            add_sale_event(
                pos_db,
                sale_id=sale.id,
                client_id=client_id,
                event_type="sale_completed",
                created_by=user,
                notes="Venta completada en POS",
                reference_type="sale",
                reference_id=sale.id,
                payload_json={
                    "sale_number": sale.sale_number,
                    "status": sale.status or "completed",
                    "total_amount": float(sale.total_amount or 0.0),
                    "tax_amount": float(sale.tax_amount or 0.0),
                },
            )

        pos_db.commit()
        pos_db.refresh(sale)

        return {
            "id": sale.id,
            "sale_number": sale.sale_number,
            "client_id": sale.client_id,
            "app_id": sale.app_id,
            "created_by": sale.created_by,
            "catalog_source_snapshot": sale.catalog_source_snapshot or "pos",
            "catalog_integration_url_snapshot": sale.catalog_integration_url_snapshot,
            "subtotal_snapshot": float(sale.subtotal_snapshot or 0.0),
            "discount_snapshot": float(sale.discount_snapshot or 0.0),
            "total_snapshot": float(sale.total_snapshot or 0.0),
            "total_amount": float(sale.total_amount or 0.0),
            "tax_amount": float(sale.tax_amount or 0.0),
            "discount_amount": float(sale.discount_amount or 0.0),
            "payment_method": sale.payment_method,
            "status": sale.status or "completed",
            "notes": sale.notes,
            "created_at": sale.created_at,
            "items": created_items,
        }

    except HTTPException:
        pos_db.rollback()
        raise
    except Exception as e:
        pos_db.rollback()
        print(f"[POS] Error inesperado en create_sale: {e}")
        raise HTTPException(status_code=500, detail="Error interno al procesar la venta")

@router.get("/api/sales/by-ticket/{sale_number}")
def get_sale_by_ticket(
    sale_number: str,
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

    require_pos_admin_for_sales_ops(
        request=request,
        authorization=authorization,
        app_id=app_id,
        client_id=client_id,
    )

    sale = (
        pos_db.query(Sale)
        .filter(
            Sale.sale_number == sale_number,
            Sale.client_id == client_id,
        )
        .first()
    )

    if not sale:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")

    return {
        "id": sale.id,
        "sale_number": sale.sale_number,
        "status": sale.status,
        "catalog_source_snapshot": sale.catalog_source_snapshot or "pos",
        "total_amount": float(sale.total_amount or 0.0),
        "created_at": sale.created_at,
        "cancelled_at": sale.cancelled_at,
        "cancelled_by": sale.cancelled_by,
        "cancellation_reason": sale.cancellation_reason,
        "items": [
            {
                "id": item.id,
                "product_name_snapshot": item.product_name_snapshot,
                "quantity": float(item.quantity or 0.0),
                "product_type_snapshot": item.product_type_snapshot,
                "catalog_source_snapshot": item.catalog_source_snapshot,
                "stock_item_id_snapshot": item.stock_item_id_snapshot,
            }
            for item in sale.items
        ],
    }


@router.get("/api/sales/retries")
def get_sales_retries(
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

    require_pos_admin_for_sales_ops(
        request=request,
        authorization=authorization,
        app_id=app_id,
        client_id=client_id,
    )

    tracked_attempt_events = {"inventory_apply_attempt", "inventory_cancel_attempt"}
    success_event = "inventory_process_success"

    events = (
        pos_db.query(SaleEvent)
        .filter(
            SaleEvent.client_id == client_id,
            SaleEvent.event_type.in_(list(tracked_attempt_events | {success_event})),
        )
        .order_by(SaleEvent.sale_id.desc(), SaleEvent.id.desc())
        .all()
    )

    grouped: dict[int, dict] = {}

    for event in events:
        sale_id = int(event.sale_id)

        if sale_id not in grouped:
            grouped[sale_id] = {
                "sale_id": sale_id,
                "has_attempt": False,
                "has_success": False,
                "latest_attempt": None,
            }

        bucket = grouped[sale_id]

        if event.event_type in tracked_attempt_events:
            bucket["has_attempt"] = True
            if bucket["latest_attempt"] is None:
                bucket["latest_attempt"] = event

        elif event.event_type == success_event:
            bucket["has_success"] = True

    pending_sale_ids = [
        sale_id
        for sale_id, bucket in grouped.items()
        if bucket["has_attempt"] and not bucket["has_success"] and bucket["latest_attempt"] is not None
    ]

    if not pending_sale_ids:
        return {"items": []}

    sales = (
        pos_db.query(Sale)
        .filter(
            Sale.client_id == client_id,
            Sale.id.in_(pending_sale_ids),
        )
        .all()
    )

    sales_map = {int(sale.id): sale for sale in sales}

    items = []

    for sale_id in pending_sale_ids:
        bucket = grouped.get(sale_id)
        latest_attempt = bucket.get("latest_attempt") if bucket else None
        sale = sales_map.get(sale_id)

        if not latest_attempt:
            continue

        sale_number = None
        sale_status = None
        total_amount = 0.0
        catalog_source = "pos"

        if sale:
            sale_number = sale.sale_number
            sale_status = sale.status
            total_amount = float(sale.total_amount or 0.0)
            catalog_source = (sale.catalog_source_snapshot or "pos").strip().lower()
        else:
            payload = latest_attempt.payload_json or {}
            if isinstance(payload, dict):
                sale_number = payload.get("sale_number")
                catalog_source = str(payload.get("catalog_source") or "pos").strip().lower()

        event_payload = latest_attempt.payload_json or {}
        if not isinstance(event_payload, dict):
            event_payload = {}

        retry_type = "venta"
        if latest_attempt.event_type == "inventory_cancel_attempt":
            retry_type = "cancelación"

        reason_parts = []

        if latest_attempt.event_type == "inventory_cancel_attempt":
            cancel_reason = event_payload.get("reason")
            if cancel_reason:
                reason_parts.append(f"Motivo cancelación: {cancel_reason}")

        if latest_attempt.notes:
            reason_parts.append(str(latest_attempt.notes))

        error_message = event_payload.get("error") or event_payload.get("detail") or event_payload.get("message")
        if error_message:
            reason_parts.append(str(error_message))

        display_reason = " | ".join([part for part in reason_parts if part]).strip()
        if not display_reason:
            display_reason = "Pendiente de reintento de inventario"

        items.append(
            {
                "sale_id": sale_id,
                "sale_number": sale_number or f"SALE-{sale_id}",
                "sale_status": sale_status or "unknown",
                "catalog_source": catalog_source,
                "retry_type": retry_type,
                "event_type": latest_attempt.event_type,
                "message": display_reason,
                "event_id": int(latest_attempt.id),
                "created_at": latest_attempt.created_at.isoformat() if latest_attempt.created_at else None,
                "total_amount": total_amount,
                "can_retry": False,
            }
        )

    items.sort(
        key=lambda x: (
            x.get("created_at") or "",
            x.get("event_id") or 0,
        ),
        reverse=True,
    )

    return {"items": items}


@router.post("/api/sales/{sale_id}/cancel")
def cancel_sale(
    sale_id: int,
    payload: dict,
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

    require_pos_admin_for_sales_ops(
        request=request,
        authorization=authorization,
        app_id=app_id,
        client_id=client_id,
    )

    sale = (
        pos_db.query(Sale)
        .filter(
            Sale.id == sale_id,
            Sale.client_id == client_id,
        )
        .first()
    )

    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    if (sale.status or "").strip().lower() == "cancelled":
        raise HTTPException(status_code=409, detail="La venta ya está cancelada")

    cancellation_reason = (payload.get("reason") or "").strip()
    if not cancellation_reason:
        raise HTTPException(status_code=400, detail="Debes capturar el motivo de cancelación")

    try:
        add_sale_event(
            pos_db,
            sale_id=sale.id,
            client_id=client_id,
            event_type="inventory_cancel_attempt",
            created_by=user,
            notes=f"Inicio de cancelación de venta. Motivo: {cancellation_reason}",
            reference_type="sale",
            reference_id=sale.id,
            payload_json={
                "sale_number": sale.sale_number,
                "catalog_source": sale.catalog_source_snapshot or "pos",
                "reason": cancellation_reason,
            },
        )

        catalog_source = (sale.catalog_source_snapshot or "pos").strip().lower()

        if catalog_source == "pos":
            apply_local_sale_cancel(
                pos_db,
                sale=sale,
                client_id=client_id,
            )

            add_sale_event(
                pos_db,
                sale_id=sale.id,
                client_id=client_id,
                event_type="inventory_process_success",
                created_by=user,
                notes="Cancelación aplicada correctamente en inventario POS local",
                reference_type="inventory",
                reference_id=sale.id,
                payload_json={
                    "mode": "pos_legacy_cancel",
                },
            )

        else:
            catalog_integration_url = sale.catalog_integration_url_snapshot
            if not catalog_integration_url:
                raise HTTPException(
                    status_code=409,
                    detail="La venta no tiene catalog_integration_url_snapshot para cancelar en Stocks",
                )

            outbound_authorization = resolve_outbound_authorization(request, authorization)

            stocks_payload_items = []

            for sale_item in sale.items:
                if (sale_item.product_type_snapshot or "physical").strip().lower() != "physical":
                    continue

                if not sale_item.stock_item_id_snapshot:
                    raise HTTPException(
                        status_code=409,
                        detail=f"El item {sale_item.id} no tiene stock_item_id_snapshot para cancelación en Stocks",
                    )

                stocks_payload_items.append(
                    {
                        "stock_item_id": int(sale_item.stock_item_id_snapshot),
                        "quantity": float(sale_item.quantity or 0.0),
                    }
                )

            if stocks_payload_items:
                post_stocks_sale_cancel(
                    catalog_integration_url=catalog_integration_url,
                    authorization=outbound_authorization,
                    app_id=app_id,
                    client_id=client_id,
                    payload={
                        "movement_type": "sale_cancel_reversal",
                        "reference_type": "pos_sale",
                        "reference_id": sale.id,
                        "source_app": "rodelsoft-pos",
                        "source_app_id": app_id,
                        "notes": f"Cancelación POS {sale.sale_number}: {cancellation_reason}",
                        "items": stocks_payload_items,
                    },
                )

                add_sale_event(
                    pos_db,
                    sale_id=sale.id,
                    client_id=client_id,
                    event_type="inventory_process_success",
                    created_by=user,
                    notes="Cancelación aplicada correctamente en Stocks API",
                    reference_type="inventory",
                    reference_id=sale.id,
                    payload_json={
                        "mode": "stocks_api_cancel",
                        "items_count": len(stocks_payload_items),
                    },
                )
            else:
                add_sale_event(
                    pos_db,
                    sale_id=sale.id,
                    client_id=client_id,
                    event_type="inventory_process_success",
                    created_by=user,
                    notes="Cancelación sin artículos físicos para afectar en Stocks",
                    reference_type="inventory",
                    reference_id=sale.id,
                    payload_json={
                        "mode": "stocks_api_cancel",
                        "items_count": 0,
                    },
                )

        sale.status = "cancelled"
        sale.cancelled_by = user
        sale.cancellation_reason = cancellation_reason
        sale.cancelled_at = sale.cancelled_at or datetime.utcnow()
        sale.inventory_reverted_at = sale.cancelled_at

        add_sale_event(
            pos_db,
            sale_id=sale.id,
            client_id=client_id,
            event_type="sale_cancelled",
            created_by=user,
            notes="Venta cancelada correctamente",
            reference_type="sale",
            reference_id=sale.id,
            payload_json={
                "sale_number": sale.sale_number,
                "reason": cancellation_reason,
                "status": "cancelled",
            },
        )

        pos_db.commit()
        pos_db.refresh(sale)

        return {
            "ok": True,
            "id": sale.id,
            "sale_number": sale.sale_number,
            "status": sale.status,
            "cancelled_at": sale.cancelled_at,
            "cancelled_by": sale.cancelled_by,
            "cancellation_reason": sale.cancellation_reason,
        }

    except HTTPException as exc:
        pos_db.rollback()

        try:
            add_sale_event(
                pos_db,
                sale_id=sale.id,
                client_id=client_id,
                event_type="inventory_cancel_failed",
                created_by=user,
                event_status="error",
                notes=str(exc.detail),
                reference_type="inventory",
                reference_id=sale.id,
                payload_json={
                    "mode": "cancel",
                    "sale_number": sale.sale_number,
                },
            )
            pos_db.commit()
        except Exception as log_exc:
            pos_db.rollback()
            print(f"[POS] No se pudo registrar inventory_cancel_failed para sale_id={sale.id}: {log_exc}")

        raise

    except Exception as e:
        print(f"[POS] Error inesperado en cancel_sale: {e}")
        pos_db.rollback()
        raise HTTPException(status_code=500, detail="Error interno al cancelar la venta")

@router.get("/api/sales/{sale_id}/print-context", response_model=SalePrintContextResponse)
def get_sale_print_context(
    sale_id: int,
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

    sale = (
        pos_db.query(Sale)
        .filter(
            Sale.id == sale_id,
            Sale.client_id == client_id,
        )
        .first()
    )

    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    settings = (
        pos_db.query(PosClientSettings)
        .filter(PosClientSettings.client_id == client_id)
        .first()
    )

    document_type_default = "ticket"
    ticket_template_name = None
    sales_note_template_name = None
    company_display_name = None
    ticket_footer_text = None
    sales_note_text_default = None
    sales_note_extra_text = None
    sales_note_services_label = None
    default_ticket_cfdi_use = "S01"
    default_ticket_tax_regime = "616"

    if settings:
        document_type_default = (settings.print_document_type or "ticket").strip().lower()
        if document_type_default not in {"ticket", "sales_note"}:
            document_type_default = "ticket"

        ticket_template_name = settings.ticket_template_name
        sales_note_template_name = settings.sales_note_template_name
        company_display_name = settings.company_display_name
        ticket_footer_text = settings.ticket_footer_text
        sales_note_text_default = settings.sales_note_text_default
        sales_note_extra_text = settings.sales_note_extra_text
        sales_note_services_label = settings.sales_note_services_label
        default_ticket_cfdi_use = settings.default_ticket_cfdi_use or "S01"
        default_ticket_tax_regime = settings.default_ticket_tax_regime or "616"

    items = [_build_sale_item_response(item) for item in sale.items]

    return {
        "sale_id": sale.id,
        "client_id": sale.client_id,
        "sale_number": sale.sale_number,
        "document_type_default": document_type_default,
        "ticket_template_name": ticket_template_name,
        "sales_note_template_name": sales_note_template_name,
        "company_display_name": company_display_name,
        "ticket_footer_text": ticket_footer_text,
        "sales_note_text_default": sales_note_text_default,
        "sales_note_extra_text": sales_note_extra_text,
        "sales_note_services_label": sales_note_services_label,
        "default_ticket_cfdi_use": default_ticket_cfdi_use,
        "default_ticket_tax_regime": default_ticket_tax_regime,
        "payment_method": sale.payment_method,
        "payment_method_label": _payment_method_label(sale.payment_method),
        "subtotal": float(sale.subtotal_snapshot or 0.0),
        "tax_amount": float(sale.tax_amount or 0.0),
        "total": float(sale.total_amount or 0.0),
        "customer_name_snapshot": sale.customer_name_snapshot,
        "cashier_name_snapshot": sale.cashier_name_snapshot,
        "items": items,
    }


@router.get("/api/sales/{sale_id}/print-data", response_model=SalePrintDataResponse)
def get_sale_print_data(
    sale_id: int,
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

    sale = (
        pos_db.query(Sale)
        .filter(
            Sale.id == sale_id,
            Sale.client_id == client_id,
        )
        .first()
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    row = (
        pos_db.query(PosSalePrintData)
        .filter(
            PosSalePrintData.sale_id == sale_id,
            PosSalePrintData.client_id == client_id,
        )
        .first()
    )

    if not row:
        raise HTTPException(status_code=404, detail="Print data no encontrada")

    return row


@router.put("/api/sales/{sale_id}/print-data", response_model=SalePrintDataResponse)
def upsert_sale_print_data(
    sale_id: int,
    payload: SalePrintDataUpsert,
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

    sale = (
        pos_db.query(Sale)
        .filter(
            Sale.id == sale_id,
            Sale.client_id == client_id,
        )
        .first()
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    settings = (
        pos_db.query(PosClientSettings)
        .filter(PosClientSettings.client_id == client_id)
        .first()
    )

    # SIEMPRE usar snapshot de settings al momento de guardar
    document_type, template_name = _resolve_default_print_config(settings)
    
    print(f"[POS][DEBUG] upsert_sale_print_data sale_id={sale_id} client_id={client_id}")
    print(f"[POS][DEBUG] payload.document_type={payload.document_type}")
    print(f"[POS][DEBUG] payload.template_name={payload.template_name}")
    if settings:
        print(f"[POS][DEBUG] settings.print_document_type={settings.print_document_type}")
        print(f"[POS][DEBUG] settings.ticket_template_name={settings.ticket_template_name}")
        print(f"[POS][DEBUG] settings.sales_note_template_name={settings.sales_note_template_name}")
    print(f"[POS][DEBUG] resolved document_type={document_type} template_name={template_name}")
    
    

    default_ticket_cfdi_use = (
        (settings.default_ticket_cfdi_use or "").strip()
        if settings and getattr(settings, "default_ticket_cfdi_use", None)
        else "S01"
    ) or "S01"

    default_ticket_tax_regime = (
        (settings.default_ticket_tax_regime or "").strip()
        if settings and getattr(settings, "default_ticket_tax_regime", None)
        else "616"
    ) or "616"

    default_ticket_footer_text = (
        (settings.ticket_footer_text or "").strip()
        if settings and getattr(settings, "ticket_footer_text", None)
        else ""
    )

    default_sales_note_text = (
        (settings.sales_note_text_default or "").strip()
        if settings and getattr(settings, "sales_note_text_default", None)
        else ""
    )

    default_sales_note_extra_text = (
        (settings.sales_note_extra_text or "").strip()
        if settings and getattr(settings, "sales_note_extra_text", None)
        else ""
    )

    default_services_label = (
        (settings.sales_note_services_label or "").strip()
        if settings and getattr(settings, "sales_note_services_label", None)
        else ""
    )

    # customer opcional para ticket, obligatorio para sales_note
    pos_customer = None
    pos_customer_id = payload.pos_customer_id

    if document_type == "sales_note" and not pos_customer_id:
        raise HTTPException(
            status_code=400,
            detail="Para sales_note debes enviar pos_customer_id"
        )

    if pos_customer_id:
        pos_customer = (
            pos_db.query(PosCustomer)
            .filter(
                PosCustomer.id == pos_customer_id,
                PosCustomer.client_id == client_id,
            )
            .first()
        )

        if not pos_customer:
            raise HTTPException(status_code=404, detail="Cliente POS no encontrado")

        if pos_customer.is_active is not True:
            raise HTTPException(
                status_code=400,
                detail="No se puede usar un customer inactivo para impresión"
            )

    row = (
        pos_db.query(PosSalePrintData)
        .filter(
            PosSalePrintData.sale_id == sale_id,
            PosSalePrintData.client_id == client_id,
        )
        .first()
    )

    payment_method_label = (payload.payment_method_label or "").strip() or _payment_method_label(sale.payment_method)
    attended_by = (payload.attended_by or "").strip() or None
    sales_note_text = (payload.sales_note_text or "").strip() or None
    ticket_footer_text = (payload.ticket_footer_text or "").strip() or None
    sales_note_extra_text = (payload.sales_note_extra_text or "").strip() or None
    services_label = (payload.services_label or "").strip() or None

    if ticket_footer_text is None and default_ticket_footer_text:
        ticket_footer_text = default_ticket_footer_text

    if document_type == "sales_note":
        if sales_note_text is None and default_sales_note_text:
            sales_note_text = default_sales_note_text

        if sales_note_extra_text is None and default_sales_note_extra_text:
            sales_note_extra_text = default_sales_note_extra_text

        if services_label is None and default_services_label:
            services_label = default_services_label
    else:
        sales_note_text = None
        sales_note_extra_text = None
        services_label = None

    if not row:
        row = PosSalePrintData(
            sale_id=sale.id,
            client_id=client_id,
            document_type=document_type,
            template_name=template_name,
            created_by=user,
        )
        pos_db.add(row)

    row.document_type = document_type
    row.template_name = template_name

    row.attended_by = attended_by
    row.payment_method_label = payment_method_label
    row.sales_note_text = sales_note_text
    row.ticket_footer_text = ticket_footer_text
    row.sales_note_extra_text = sales_note_extra_text
    row.services_label = services_label

    row.subtotal = float(sale.subtotal_snapshot or 0.0)
    row.tax_amount = float(sale.tax_amount or 0.0)
    row.total = float(sale.total_amount or 0.0)

    if pos_customer:
        row.pos_customer_id = pos_customer.id
        row.customer_rfc = (pos_customer.rfc or "").strip().upper() or None
        row.customer_business_name = (pos_customer.business_name or "").strip() or None
        row.customer_contact_name = (pos_customer.contact_name or "").strip() or None
        row.customer_phone = (pos_customer.phone or "").strip() or None
        row.customer_email = (pos_customer.email or "").strip() or None
        row.customer_address = (pos_customer.address or "").strip() or None
        row.customer_postal_code = (pos_customer.postal_code or "").strip() or None
        row.customer_tax_regime = (pos_customer.tax_regime or "").strip() or None
        row.customer_cfdi_use = (pos_customer.cfdi_use or "").strip() or None
    else:
        # Fallback ticket / público general
        row.pos_customer_id = None
        row.customer_rfc = "XAXX010101000"
        row.customer_business_name = "PÚBLICO EN GENERAL"
        row.customer_contact_name = None
        row.customer_phone = None
        row.customer_email = None
        row.customer_address = None
        row.customer_postal_code = None
        row.customer_tax_regime = default_ticket_tax_regime
        row.customer_cfdi_use = default_ticket_cfdi_use

    pos_db.commit()
    pos_db.refresh(row)

    return row