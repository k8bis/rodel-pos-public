from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from auth import verify_token
from db import (
    get_pos_db,
    PosClientSettings,
    Sale,
    SaleItem,
    PosSalePrintData,
)
from permissions import resolve_context, validate_permission


router = APIRouter(tags=["POS Print"])


# ============================================================
# DIRECTORIOS DE TEMPLATES
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
PRINTABLES_DIR = BASE_DIR / "templates" / "printables"
SALES_NOTE_DIR = PRINTABLES_DIR / "sales_note"
TICKETS_DIR = PRINTABLES_DIR / "tickets"

templates = Jinja2Templates(directory=str(PRINTABLES_DIR))


# ============================================================
# HELPERS DE TEMPLATES
# ============================================================

def get_print_template_dir(document_type: str) -> Path:
    if document_type == "sales_note":
        return SALES_NOTE_DIR
    return TICKETS_DIR


def get_print_template_fallback(document_type: str) -> str:
    if document_type == "sales_note":
        return "sales_note_default.html"
    return "ticket_default.html"


def sanitize_template_name(template_name: Optional[str], fallback: str) -> str:
    if not template_name:
        return fallback

    safe_name = Path(template_name).name

    # evita rutas tipo ../archivo.html
    if safe_name != template_name:
        return fallback

    if not safe_name.endswith(".html"):
        return fallback

    return safe_name


def resolve_sale_print_template_name(
    client_settings: Optional[PosClientSettings],
    print_data: Optional[PosSalePrintData],
    document_type: str,
) -> str:
    # Con tu DB actual, el template configurado real vive en pos_sale_print_data.template_name
    # print("client_settings.print_document_type:",{client_settings.sales_note_template_name})
    if print_data and getattr(print_data, "template_name", None):
        return print_data.template_name

    return get_print_template_fallback(document_type)

def resolve_template_relative_path(document_type: str, template_name: Optional[str]) -> str:
    fallback = get_print_template_fallback(document_type)
    safe_name = sanitize_template_name(template_name, fallback)

    template_dir = get_print_template_dir(document_type)
    template_path = template_dir / safe_name

    if not template_path.exists() or not template_path.is_file():
        safe_name = fallback
        template_path = template_dir / safe_name

    if not template_path.exists() or not template_path.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"No existe plantilla de impresión: {safe_name}"
        )

    if document_type == "sales_note":
        return f"sales_note/{safe_name}"
    return f"tickets/{safe_name}"


# ============================================================
# HELPERS DE DATOS
# ============================================================

def _get_sale_or_404(pos_db: Session, sale_id: int, client_id: int) -> Sale:
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

    return sale


def _get_sale_print_data(pos_db: Session, sale_id: int, client_id: int) -> Optional[PosSalePrintData]:
    return (
        pos_db.query(PosSalePrintData)
        .filter(
            PosSalePrintData.sale_id == sale_id,
            PosSalePrintData.client_id == client_id,
        )
        .first()
    )


def _get_client_settings(pos_db: Session, client_id: int) -> Optional[PosClientSettings]:
    return (
        pos_db.query(PosClientSettings)
        .filter(PosClientSettings.client_id == client_id)
        .first()
    )


def _get_sale_items(pos_db: Session, sale_id: int):
    return (
        pos_db.query(SaleItem)
        .filter(SaleItem.sale_id == sale_id)
        .order_by(SaleItem.id.asc())
        .all()
    )


def build_sale_print_context(pos_db: Session, sale_id: int, client_id: int) -> dict:
    sale = _get_sale_or_404(pos_db, sale_id, client_id)
    print_data = _get_sale_print_data(pos_db, sale_id, client_id)
    items = _get_sale_items(pos_db, sale_id)

    client_settings = _get_client_settings(pos_db, client_id)

    # En una impresion el document_type se toma de client_settings, validar reimpresion porque lo deberia tomar de print_data
    document_type = (
        (client_settings.print_document_type if client_settings and getattr(client_settings, "print_document_type", None) else None)
        or "ticket"
    )

    context = {
        "sale_id": sale.id,
        "client_id": sale.client_id,
        "sale_number": sale.sale_number,
        "document_type": document_type,

        # template real
        "template_name": (
            print_data.template_name
            if print_data and getattr(print_data, "template_name", None)
            else None
        ),

        # branding / textos
        "company_display_name": (
            (client_settings.company_display_name if client_settings and getattr(client_settings, "company_display_name", None) else None)
            or "RodelSoft"
        ),
        "ticket_footer_text": (
            (print_data.ticket_footer_text if print_data and getattr(print_data, "ticket_footer_text", None) else None)
            or (client_settings.ticket_footer_text if client_settings and getattr(client_settings, "ticket_footer_text", None) else None)
            or "Gracias por su compra"
        ),
        "sales_note_text": (
            print_data.sales_note_text
            if print_data and getattr(print_data, "sales_note_text", None)
            else None
        ),
        "sales_note_extra_text": (
            print_data.sales_note_extra_text
            if print_data and getattr(print_data, "sales_note_extra_text", None)
            else None
        ),
        "services_label": (
            print_data.services_label
            if print_data and getattr(print_data, "services_label", None)
            else None
        ),

        # pago / totales (tu fuente principal aquí debe ser print_data)
        "payment_method": sale.payment_method,
        "payment_method_label": (
            (print_data.payment_method_label if print_data and getattr(print_data, "payment_method_label", None) else None)
            or sale.payment_method
            or "cash"
        ),
        "subtotal": float(
            (print_data.subtotal if print_data and getattr(print_data, "subtotal", None) is not None else sale.subtotal_snapshot) or 0
        ),
        "tax_amount": float(
            (print_data.tax_amount if print_data and getattr(print_data, "tax_amount", None) is not None else sale.tax_amount) or 0
        ),
        "total": float(
            (print_data.total if print_data and getattr(print_data, "total", None) is not None else sale.total_amount) or 0
        ),

        # snapshots encabezado
        "customer_name_snapshot": (
            (sale.customer_name_snapshot if getattr(sale, "customer_name_snapshot", None) else None)
        ),
        "cashier_name_snapshot": (
            (print_data.attended_by if print_data and getattr(print_data, "attended_by", None) else None)
            or sale.cashier_name_snapshot
        ),

        # datos cliente fiscal / comercial
        "customer_business_name": (
            print_data.customer_business_name
            if print_data and getattr(print_data, "customer_business_name", None)
            else None
        ),
        "customer_contact_name": (
            print_data.customer_contact_name
            if print_data and getattr(print_data, "customer_contact_name", None)
            else None
        ),
        "customer_rfc": (
            print_data.customer_rfc
            if print_data and getattr(print_data, "customer_rfc", None)
            else None
        ),
        "customer_phone": (
            print_data.customer_phone
            if print_data and getattr(print_data, "customer_phone", None)
            else None
        ),
        "customer_email": (
            print_data.customer_email
            if print_data and getattr(print_data, "customer_email", None)
            else None
        ),
        "customer_address": (
            print_data.customer_address
            if print_data and getattr(print_data, "customer_address", None)
            else None
        ),
        "customer_postal_code": (
            print_data.customer_postal_code
            if print_data and getattr(print_data, "customer_postal_code", None)
            else None
        ),
        "customer_tax_regime": (
            print_data.customer_tax_regime
            if print_data and getattr(print_data, "customer_tax_regime", None)
            else None
        ),
        "customer_cfdi_use": (
            print_data.customer_cfdi_use
            if print_data and getattr(print_data, "customer_cfdi_use", None)
            else None
        ),

        # fecha
        "created_at": sale.created_at.isoformat() if sale.created_at else None,

        # items
        "items": [],
    }

    for item in items:
        context["items"].append({
            "id": item.id,
            "pos_price_id": item.pos_price_id,
            "catalog_source": item.catalog_source,
            "catalog_item_id": item.catalog_item_id,

            "product_name": item.product_name_snapshot,
            "quantity": float(item.quantity or 0),
            "unit_price": float(item.unit_price or 0),
            "tax_percent": float(item.tax_percent or 0),
            "total_price": float(item.total_price or 0),

            # snapshots
            "catalog_source_snapshot": item.catalog_source_snapshot,
            "catalog_item_id_snapshot": item.catalog_item_id_snapshot,
            "sku_snapshot": item.sku_snapshot,
            "category_name_snapshot": item.category_name_snapshot,
            "product_type_snapshot": item.product_type_snapshot,
            "inventory_mode_snapshot": item.inventory_mode_snapshot,
            "stock_item_id_snapshot": item.stock_item_id_snapshot,
            "unit_price_snapshot": float(item.unit_price_snapshot or 0),
            "line_total_snapshot": float(item.line_total_snapshot or 0),
        })

    return context


def build_sale_print_template_context(print_context: dict) -> dict:
    return {
        "sale": {
            "id": print_context["sale_id"],
            "number": print_context["sale_number"],
            "document_type": print_context["document_type"],
            "created_at": print_context["created_at"],
            "payment_method": print_context["payment_method"],
            "payment_method_label": print_context["payment_method_label"],
            "subtotal": print_context["subtotal"],
            "tax_amount": print_context["tax_amount"],
            "total": print_context["total"],
            "customer_name": print_context["customer_name_snapshot"],
            "cashier_name": print_context["cashier_name_snapshot"],
        },
        "company": {
            "display_name": print_context["company_display_name"],
        },
        "labels": {
            "ticket_footer_text": print_context["ticket_footer_text"],
            "sales_note_text": print_context["sales_note_text"],
            "sales_note_extra_text": print_context["sales_note_extra_text"],
            "services_label": print_context["services_label"],
        },
        "customer": {
            "business_name": print_context["customer_business_name"],
            "contact_name": print_context["customer_contact_name"],
            "rfc": print_context["customer_rfc"],
            "phone": print_context["customer_phone"],
            "email": print_context["customer_email"],
            "address": print_context["customer_address"],
            "postal_code": print_context["customer_postal_code"],
            "tax_regime": print_context["customer_tax_regime"],
            "cfdi_use": print_context["customer_cfdi_use"],
        },
        "items": [
            {
                "name": item["product_name"],
                "qty": item["quantity"],
                "unit_price": item["unit_price"],
                "tax_percent": item["tax_percent"],
                "total_price": item["total_price"],
                "sku": item.get("sku_snapshot"),
                "category_name": item.get("category_name_snapshot"),
                "product_type": item.get("product_type_snapshot"),
            }
            for item in print_context.get("items", [])
        ]
    }


# ============================================================
# ENDPOINT
# ============================================================

@router.get("/api/sales/{sale_id}/print-html", response_class=HTMLResponse)
def get_sale_print_html(
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

    print_context = build_sale_print_context(pos_db, sale_id, client_id)
    client_settings = _get_client_settings(pos_db, client_id)
    print_data = _get_sale_print_data(pos_db, sale_id, client_id)

    document_type = print_context["document_type"]
    raw_template_name = resolve_sale_print_template_name(client_settings, print_data, document_type)

    template_context = build_sale_print_template_context(print_context)
    template_path = resolve_template_relative_path(document_type, raw_template_name)
    
    #print(template_path)

    template_context["request"] = request

    return templates.TemplateResponse(
        request,
        template_path,
        template_context,
    )