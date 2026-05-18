import os
from pathlib import Path
from datetime import datetime

import requests

from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from db import (
    Category,
    Product,
    PosClientSettings,
    PosPrice,
    STOCKS_TIMEOUT,
)
from auth import verify_token
from permissions import (
    resolve_context,
    validate_permission,
    get_context_info,
    get_session_context as fetch_session_context,
    get_role_info,
)


APP_BASE_PATH = os.getenv("APP_BASE_PATH", "/pos")
APP_MENU_URL = os.getenv("APP_MENU_URL", "/")
LOGOUT_URL = os.getenv("LOGOUT_URL", f"{APP_BASE_PATH}/logout")
LOGIN_FALLBACK_URL = os.getenv("LOGIN_FALLBACK_URL", "/")
SESSION_CHECK_URL = os.getenv("SESSION_CHECK_URL", f"{APP_BASE_PATH}/session-check")
INTERNAL_SHARED_SECRET = (os.getenv("INTERNAL_SHARED_SECRET", "").strip())

def build_contract_error_response(
    *,
    error_code: str,
    detail: str,
    status_code: int = 400,
    upstream: str | None = None,
    context: dict | None = None,
):
    payload = {
        "ok": False,
        "error_code": error_code,
        "detail": detail,
    }

    if upstream:
        payload["upstream"] = upstream

    if context:
        payload["context"] = context

    return {
        "status_code": status_code,
        "payload": payload,
    }

def raise_upstream_contract_error(
    *,
    response,
    upstream: str,
    default_detail: str,
    status_code: int = 502,
):
    body = None

    try:
        body = response.json()
    except Exception:
        body = None

    if isinstance(body, dict):

        if (
            body.get("ok") is False
            and body.get("error_code")
        ):
            raise HTTPException(
                status_code=status_code,
                detail=body,
            )

        detail = (
            body.get("detail")
            or body.get("message")
            or default_detail
        )

    else:
        detail = default_detail

    raise HTTPException(
        status_code=status_code,
        detail=build_contract_error_response(
            error_code="UPSTREAM_REQUEST_FAILED",
            detail=detail,
            status_code=status_code,
            upstream=upstream,
        )["payload"],
    )

def get_user_or_redirect(
    request: Request,
    authorization: str | None = None,
) -> str | None:
    token = None

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]

    if not token:
        token = request.cookies.get("jwt")

    if not token:
        return None

    try:
        user = verify_token(request, authorization)
        return user
    except HTTPException:
        return None


def build_logout_response() -> RedirectResponse:
    response = RedirectResponse(url=LOGIN_FALLBACK_URL, status_code=302)
    response.delete_cookie("jwt", path="/")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

def build_category_path(category):
    """
    Construye path jerárquico textual congelado.

    Ejemplo:
    Electronica > Estereos > Autoestereos
    """

    if not category:
        return None

    visited = set()
    parts = []

    current = category

    while current:
        if current.id in visited:
            break

        visited.add(current.id)

        if current.name:
            parts.append(current.name.strip())

        current = getattr(current, "parent", None)

    parts.reverse()

    return " > ".join(parts)


def normalize_product_type(value: str | None) -> str:
    allowed = {"physical", "service"}
    normalized = (value or "physical").strip().lower()
    if normalized not in allowed:
        raise HTTPException(
            status_code=400,
            detail="product_type inválido. Permitidos: physical, service",
        )
    return normalized

def validate_category_parent(
    *,
    pos_db,
    client_id: int,
    category_id: int | None,
    parent_id: int | None,
):
    """
    Reglas oficiales:

    - parent_id puede ser NULL
    - parent debe existir
    - parent debe pertenecer al mismo client_id
    - no puede apuntarse a sí misma
    - no puede generar loops recursivos
    """

    if parent_id is None:
        return None

    parent = (
        pos_db.query(Category)
        .filter(
            Category.id == parent_id,
            Category.client_id == client_id,
            Category.is_active == True,
        )
        .first()
    )

    if not parent:
        raise HTTPException(
            status_code=400,
            detail="parent_id inválido para este cliente",
        )

    if category_id is not None:
        if int(parent_id) == int(category_id):
            raise HTTPException(
                status_code=400,
                detail="Una categoría no puede ser padre de sí misma",
            )

        visited = set()

        current = parent

        while current:

            if current.id in visited:
                break

            visited.add(current.id)

            if int(current.id) == int(category_id):
                raise HTTPException(
                    status_code=400,
                    detail="Loop jerárquico detectado",
                )

            current = current.parent

    return parent

def normalize_inventory_mode(value: str | None) -> str:
    allowed = {"pos_legacy", "stocks_api", "none"}
    normalized = (value or "pos_legacy").strip().lower()
    if normalized not in allowed:
        raise HTTPException(
            status_code=400,
            detail="inventory_mode inválido. Permitidos: pos_legacy, stocks_api, none",
        )
    return normalized


def build_sale_number() -> str:
    return f"POS-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"


def build_auth_headers(
    authorization: str | None,
    app_id: int,
    client_id: int,
) -> dict:
    headers = {
        "X-App-Id": str(app_id),
        "X-Client-Id": str(client_id),
    }
    if authorization:
        headers["Authorization"] = authorization
    return headers

def validate_internal_request(
    x_internal_request: str | None,
    x_internal_secret: str | None,
):
    internal_flag = str(
        x_internal_request or ""
    ).strip().lower()

    provided_secret = str(
        x_internal_secret or ""
    ).strip()

    if internal_flag != "true":
        raise HTTPException(
            status_code=403,
            detail=(
                "Internal endpoint "
                "requires internal request"
            ),
        )

    if not INTERNAL_SHARED_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Internal shared secret not configured",
        )

    if provided_secret != INTERNAL_SHARED_SECRET:
        raise HTTPException(
            status_code=403,
            detail="Invalid internal secret",
        )

def resolve_outbound_authorization(
    request: Request,
    authorization: str | None,
) -> str | None:
    """
    Resuelve el bearer para llamadas salientes POS -> Stocks.
    Prioridad:
    1) Authorization header entrante si ya viene como Bearer
    2) Cookie jwt del navegador -> se reconstruye como Bearer
    """
    if authorization and authorization.strip().lower().startswith("bearer "):
        return authorization.strip()

    token = request.cookies.get("jwt")
    if token:
        token = token.strip()
        if token:
            return f"Bearer {token}"

    return None

def get_session_context(
    request: Request,
    app_id: int,
    client_id: int,
    authorization: str | None,
) -> dict:
    """
    Wrapper local para session-context.
    Fuente oficial de rol/capacidades UI en POS.
    """
    return fetch_session_context(
        request=request,
        app_id=app_id,
        client_id=client_id,
        authorization=authorization,
    )


def get_client_settings(pos_db: Session, client_id: int) -> PosClientSettings | None:
    return (
        pos_db.query(PosClientSettings)
        .filter(PosClientSettings.client_id == client_id)
        .first()
    )


def get_catalog_source(pos_db: Session, client_id: int) -> str:
    settings = get_client_settings(pos_db, client_id)
    if not settings:
        return "pos"

    source = (getattr(settings, "catalog_source", None) or "pos").strip().lower()
    if source not in {"pos", "stocks"}:
        return "pos"
    return source

def resolve_inventory_source_for_stocks(
    pos_db: Session,
    client_id: int,
) -> str:
    """
    Resolver interoperable para STOCKS.

    Reglas:
    - Si NO existe configuración:
        → stocks
    - Si existe configuración:
        → respetar catalog_source
    """

    settings = get_client_settings(pos_db, client_id)

    if not settings:
        return "stocks"

    source = (
        getattr(settings, "catalog_source", None)
        or "stocks"
    ).strip().lower()

    if source not in {"pos", "stocks"}:
        return "stocks"

    return source

def resolve_inventory_source_for_stocks(
    pos_db: Session,
    client_id: int,
) -> str:
    """
    Resolver oficial interoperable para STOCKS.

    Reglas:
    - Si NO existe configuración POS:
        → asumir stocks
    - Si existe configuración:
        → respetar catalog_source configurado
    """

    settings = get_client_settings(pos_db, client_id)

    if not settings:
        return "stocks"

    source = (
        getattr(settings, "catalog_source", None)
        or "stocks"
    ).strip().lower()

    if source not in {"pos", "stocks"}:
        return "stocks"

    return source


def get_catalog_integration_url(pos_db: Session, client_id: int) -> str | None:
    settings = get_client_settings(pos_db, client_id)
    if not settings:
        return None

    value = (getattr(settings, "catalog_integration_url", None) or "").strip()
    return value or None


def require_catalog_integration_url(pos_db: Session, client_id: int) -> str:
    catalog_source = get_catalog_source(pos_db, client_id)

    if catalog_source != "stocks":
        raise HTTPException(
            status_code=409,
            detail="El cliente no está configurado con catalog_source=stocks.",
        )

    url = get_catalog_integration_url(pos_db, client_id)
    if not url:
        raise HTTPException(
            status_code=409,
            detail="Cliente configurado con catálogo Stocks pero sin catalog_integration_url.",
        )

    return url


def fetch_stocks_categories(
    catalog_integration_url: str,
    authorization: str | None,
    app_id: int,
    client_id: int,
) -> list[dict]:
    base_url = (catalog_integration_url or "").strip()
    if not base_url:
        raise HTTPException(
            status_code=409,
            detail="Cliente configurado con catálogo Stocks pero sin catalog_integration_url.",
        )

    url = f"{base_url.rstrip('/')}/api/categories"

    try:
        response = requests.get(
            url,
            headers=build_auth_headers(authorization, app_id, client_id),
            timeout=STOCKS_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo conectar con Stocks API: {exc.__class__.__name__}",
        )

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Sesión inválida al consultar Stocks")

    if not response.ok:
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo consultar categorías de Stocks ({response.status_code})",
        )

    payload = response.json()
    return payload.get("items", [])

def fetch_stock_item_by_id(
    *,
    catalog_integration_url: str,
    authorization: str | None,
    app_id: int,
    client_id: int,
    item_id: int,
):
    #print(f"[DEBUG] Fetching stock item by id: {item_id} from {catalog_integration_url}")
    
    base_url = (
        catalog_integration_url.rstrip("/")
    )

    url = (
        f"{base_url}/api/items/{item_id}"
    )

    headers = {
        "X-App-Id": str(app_id),
        "X-Client-Id": str(client_id),
    }

    if authorization:
        headers["Authorization"] = authorization

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=15,
        )

    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "No fue posible consultar "
                "el catálogo Stocks."
            ),
        ) from exc

    if response.status_code >= 400:
        try:
            detail = response.json()
        except Exception:
            detail = response.text

        raise HTTPException(
            status_code=502,
            detail={
                "message": (
                    "Stocks devolvió error "
                    "al consultar item."
                ),
                "stocks_response": detail,
            },
        )

    try:
        payload = response.json()

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Respuesta inválida "
                "desde Stocks."
            ),
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=502,
            detail=(
                "Payload inválido "
                "desde Stocks."
            ),
        )

    runtime_item = payload.get("item")

    if not isinstance(runtime_item, dict):
        raise HTTPException(
            status_code=502,
            detail=(
                "Runtime item inválido "
                "desde Stocks."
            ),
        )

    if not isinstance(runtime_item, dict):
        raise HTTPException(
            status_code=502,
            detail=(
                "Runtime item inválido "
                "desde Stocks."
            ),
        )

    #print(f"[DEBUG] Runtime stock item resolved: {runtime_item}")

    return runtime_item

def fetch_stocks_items(
    catalog_integration_url: str,
    authorization: str | None,
    app_id: int,
    client_id: int,
) -> list[dict]:
    base_url = (catalog_integration_url or "").strip()
    if not base_url:
        raise HTTPException(
            status_code=409,
            detail="Cliente configurado con catálogo Stocks pero sin catalog_integration_url.",
        )

    url = f"{base_url.rstrip('/')}/api/items"

    try:
        response = requests.get(
            url,
            headers=build_auth_headers(authorization, app_id, client_id),
            timeout=STOCKS_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo conectar con Stocks API: {exc.__class__.__name__}",
        )

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Sesión inválida al consultar items de Stocks")

    if not response.ok:
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo consultar items de Stocks ({response.status_code})",
        )

    payload = response.json()
    return payload.get("items", [])


def post_stock_movement(
    catalog_integration_url: str,
    authorization: str | None,
    app_id: int,
    client_id: int,
    stock_item_id: int,
    quantity: float,
    notes: str,
):
    base_url = (catalog_integration_url or "").strip()
    if not base_url:
        raise HTTPException(
            status_code=409,
            detail="Cliente configurado con catálogo Stocks pero sin catalog_integration_url.",
        )

    url = f"{base_url.rstrip('/')}/api/movements"
    payload = {
        "stock_item_id": stock_item_id,
        "movement_type": "manual_exit",
        "quantity": quantity,
        "notes": notes,
    }

    try:
        response = requests.post(
            url,
            headers={
                **build_auth_headers(authorization, app_id, client_id),
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=STOCKS_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo conectar con Stocks API: {exc.__class__.__name__}",
        )

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Sesión inválida al descontar inventario en Stocks")

    if not response.ok:
        detail = f"No se pudo descontar inventario en Stocks ({response.status_code})"
        try:
            body = response.json()
            detail = body.get("message") or body.get("detail") or detail
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=detail)

    return response.json()


def sync_pos_price_snapshot_for_product(
    pos_db: Session,
    client_id: int,
    product: Product,
):
    category_name = None
    if product.category_id:
        category = (
            pos_db.query(Category)
            .filter(
                Category.id == product.category_id,
                Category.client_id == client_id,
            )
            .first()
        )
        category_name = category.name if category else None

    pos_price = (
        pos_db.query(PosPrice)
        .filter(
            PosPrice.client_id == client_id,
            PosPrice.catalog_source == "pos",
            PosPrice.catalog_item_id == product.id,
        )
        .first()
    )

    if pos_price:
        pos_price.display_name_snapshot = product.name
        pos_price.sku_snapshot = product.sku
        pos_price.category_name_snapshot = category_name
        pos_price.product_type_snapshot = product.product_type or "physical"
        pos_price.inventory_mode_snapshot = product.inventory_mode or "pos_legacy"
        pos_price.stock_item_id_snapshot = product.stock_item_id
        pos_price.is_active = bool(product.is_active)


def get_pos_role_flags(
    request: Request,
    authorization: str | None,
    app_id: int,
    client_id: int,
) -> dict:
    """
    Matriz oficial INV-3B.1:
    - system_admin: full
    - app_client_admin: administra catálogos, ve Configuración POS
    - member: solo consulta catálogos, NO ve Configuración POS
    """
    return get_role_info(
        request=request,
        app_id=app_id,
        client_id=client_id,
        authorization=authorization,
    )


def render_pos_html(
    request: Request,
    user: str,
    authorization: str | None,
    x_app_id: int | None,
    x_client_id: int | None,
) -> HTMLResponse:
    app_id, client_id = resolve_context(request, x_app_id, x_client_id)

    if not app_id or not client_id:
        raise HTTPException(status_code=400, detail="Faltan app_id o client_id")

    validate_permission(request, user, app_id, client_id, authorization)

    context = get_context_info(request, app_id, client_id, authorization)
    role_flags = get_pos_role_flags(request, authorization, app_id, client_id)

    app_name = context.get("app_name", "POS")
    client_name = context.get("client_name", "Cliente")

    role = str(role_flags.get("role") or "member").strip().lower()
    is_system_admin = bool(role_flags.get("is_system_admin", False))
    is_app_client_admin = bool(role_flags.get("is_app_client_admin", False))
    is_member = bool(role_flags.get("is_member", True))

    can_manage_catalogs = bool(role_flags.get("can_manage_catalogs", False))
    can_view_pos_config = bool(role_flags.get("can_view_pos_config", False))
    can_edit_pos_config = bool(role_flags.get("can_edit_pos_config", False))

    app_menu_url = APP_MENU_URL
    logout_url = LOGOUT_URL
    login_fallback_url = LOGIN_FALLBACK_URL
    session_check_url = SESSION_CHECK_URL

    template_path = Path(__file__).resolve().parent / "templates" / "pos_template.html"
    if not template_path.exists():
        raise HTTPException(status_code=500, detail="Template de POS no encontrado")

    html_content = template_path.read_text(encoding="utf-8")

    html_content = html_content.replace("__APP_NAME__", app_name)
    html_content = html_content.replace("__CLIENT_NAME__", client_name)
    html_content = html_content.replace("__USER__", user)
    html_content = html_content.replace("__APP_MENU_URL__", app_menu_url)
    html_content = html_content.replace("__LOGOUT_URL__", logout_url)
    html_content = html_content.replace("__LOGIN_FALLBACK_URL__", login_fallback_url)
    html_content = html_content.replace("__SESSION_CHECK_URL__", session_check_url)
    html_content = html_content.replace("__APP_BASE_PATH__", APP_BASE_PATH)
    html_content = html_content.replace("__LOGOUT_REDIRECT_URL__", login_fallback_url)
    html_content = html_content.replace("__ROLE__", role)
    html_content = html_content.replace("__IS_SYSTEM_ADMIN__", "true" if is_system_admin else "false")
    html_content = html_content.replace("__IS_APP_CLIENT_ADMIN__", "true" if is_app_client_admin else "false")
    html_content = html_content.replace("__IS_MEMBER__", "true" if is_member else "false")
    html_content = html_content.replace("__CAN_MANAGE_CATALOGS__", "true" if can_manage_catalogs else "false")
    html_content = html_content.replace("__CAN_VIEW_POS_CONFIG__", "true" if can_view_pos_config else "false")
    html_content = html_content.replace("__CAN_EDIT_POS_CONFIG__", "true" if can_edit_pos_config else "false")

    response = HTMLResponse(content=html_content)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

def post_stocks_sale_apply(
    catalog_integration_url: str,
    authorization: str | None,
    app_id: int,
    client_id: int,
    payload: dict,
) -> dict:
    base_url = (catalog_integration_url or "").strip()
    if not base_url:
        raise HTTPException(
            status_code=409,
            detail="Cliente configurado con catálogo Stocks pero sin catalog_integration_url.",
        )

    url = f"{base_url.rstrip('/')}/api/movements"

    try:
        response = requests.post(
            url,
            headers={
                **build_auth_headers(authorization, app_id, client_id),
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=STOCKS_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo conectar con Stocks API: {exc.__class__.__name__}",
        )

    if response.status_code == 401:
        raise HTTPException(
            status_code=401,
            detail="Sesión inválida al aplicar venta en Stocks",
        )

    detail = None
    body = None

    try:
        body = response.json()
    except Exception:
        body = None

    if not response.ok:
        raise_upstream_contract_error(
            response=response,
            upstream="stocks",
            default_detail=(
                f"No se pudo aplicar venta en Stocks "
                f"({response.status_code})"
            ),
            status_code=502,
        )

    if isinstance(body, dict):
        if body.get("ok") is False:
            raise HTTPException(
                status_code=502,
                detail=body.get("message") or body.get("detail") or "Stocks devolvió error al aplicar movimientos",
            )
        return body

    return {"ok": True}


def post_stocks_sale_cancel(
    catalog_integration_url: str,
    authorization: str | None,
    app_id: int,
    client_id: int,
    payload: dict,
) -> dict:
    base_url = (catalog_integration_url or "").strip()
    if not base_url:
        raise HTTPException(
            status_code=409,
            detail="Cliente configurado con catálogo Stocks pero sin catalog_integration_url.",
        )

    url = f"{base_url.rstrip('/')}/api/movements"

    try:
        response = requests.post(
            url,
            headers={
                **build_auth_headers(authorization, app_id, client_id),
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=STOCKS_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo conectar con Stocks API: {exc.__class__.__name__}",
        )

    if response.status_code == 401:
        raise HTTPException(
            status_code=401,
            detail="Sesión inválida al cancelar venta en Stocks",
        )

    detail = None
    body = None

    try:
        body = response.json()
    except Exception:
        body = None

    if not response.ok:
        raise_upstream_contract_error(
            response=response,
            upstream="stocks",
            default_detail=(
                f"No se pudo cancelar venta en Stocks "
                f"({response.status_code})"
            ),
            status_code=502,
        )

    if isinstance(body, dict):
        if body.get("ok") is False:
            raise HTTPException(
                status_code=502,
                detail=body.get("message") or body.get("detail") or "Stocks devolvió error al cancelar movimientos",
            )
        return body

    return {"ok": True}

def require_pos_admin_for_sales_ops(
    request: Request,
    authorization: str | None,
    app_id: int,
    client_id: int,
):
    role_flags = get_pos_role_flags(
        request=request,
        authorization=authorization,
        app_id=app_id,
        client_id=client_id,
    )

    if not (
        bool(role_flags.get("is_system_admin", False))
        or bool(role_flags.get("is_app_client_admin", False))
    ):
        raise HTTPException(
            status_code=403,
            detail="Solo administradores pueden usar cancelación / reintentos en POS.",
        )

    return role_flags
