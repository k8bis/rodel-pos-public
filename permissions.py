import os
import requests
from fastapi import HTTPException, Request


CONTROL_PLANE_BASE_URL = os.getenv("CONTROL_PLANE_BASE_URL")
CONTROL_PLANE_TIMEOUT = float(os.getenv("CONTROL_PLANE_TIMEOUT", "5"))


def resolve_context(request: Request, x_app_id: int | None, x_client_id: int | None):
    app_id = x_app_id
    client_id = x_client_id

    if app_id is None:
        q = request.query_params.get("app_id")
        if q and q.isdigit():
            app_id = int(q)

    if client_id is None:
        q = request.query_params.get("client_id")
        if q and q.isdigit():
            client_id = int(q)

    return app_id, client_id


def _extract_bearer_or_cookie(request: Request, authorization: str | None = None) -> str | None:
    token = None

    if authorization and authorization.startswith("Bearer "):
        token = authorization

    if not token:
        raw_cookie = request.cookies.get("jwt")
        if raw_cookie:
            token = f"Bearer {raw_cookie}"

    return token


def _call_control_plane(
    request: Request,
    endpoint: str,
    app_id: int,
    client_id: int,
    authorization: str | None = None,
) -> requests.Response:
    bearer = _extract_bearer_or_cookie(request, authorization)

    if not bearer:
        raise HTTPException(status_code=401, detail="No token")

    try:
        response = requests.get(
            f"{CONTROL_PLANE_BASE_URL}{endpoint}",
            headers={
                "Authorization": bearer,
                "X-App-Id": str(app_id),
                "X-Client-Id": str(client_id),
            },
            timeout=CONTROL_PLANE_TIMEOUT,
        )
        return response
    except requests.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Control Plane no disponible: {e}")


def _extract_error_detail(response: requests.Response, fallback: str) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return payload.get("detail", fallback)
        return fallback
    except Exception:
        return fallback


def validate_permission(
    request: Request,
    username: str,
    app_id: int,
    client_id: int,
    authorization: str | None = None,
):
    response = _call_control_plane(
        request=request,
        endpoint="/internal/access-check",
        app_id=app_id,
        client_id=client_id,
        authorization=authorization,
    )

    if response.status_code == 200:
        return True

    detail = _extract_error_detail(response, "Acceso denegado por Control Plane")
    raise HTTPException(status_code=response.status_code, detail=detail)


def get_context_info(
    request: Request,
    app_id: int,
    client_id: int,
    authorization: str | None = None,
) -> dict:
    response = _call_control_plane(
        request=request,
        endpoint="/internal/context-info",
        app_id=app_id,
        client_id=client_id,
        authorization=authorization,
    )

    if response.status_code == 200:
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    detail = _extract_error_detail(response, "No se pudo obtener contexto desde Control Plane")
    raise HTTPException(status_code=response.status_code, detail=detail)


def get_session_context(
    request: Request,
    app_id: int,
    client_id: int,
    authorization: str | None = None,
) -> dict:
    """
    Fuente oficial de rol/capacidades para POS (INV-3B.1):
    - /public/session-context
    """
    response = _call_control_plane(
        request=request,
        endpoint="/public/session-context",
        app_id=app_id,
        client_id=client_id,
        authorization=authorization,
    )

    if response.status_code == 200:
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    detail = _extract_error_detail(response, "No se pudo obtener session-context desde Control Plane")
    raise HTTPException(status_code=response.status_code, detail=detail)


def get_role_info(
    request: Request,
    app_id: int,
    client_id: int,
    authorization: str | None = None,
) -> dict:
    """
    Matriz oficial INV-3B.1 para POS:
    - system_admin: full
    - app_client_admin: CRUD de catálogos + ve Configuración POS
    - member: solo consulta catálogos, NO ve Configuración POS

    Fuente oficial:
    - /public/session-context

    Sin fallbacks.
    Sin /internal/me/role.
    Sin inferencias por username.
    """
    session = get_session_context(
        request=request,
        app_id=app_id,
        client_id=client_id,
        authorization=authorization,
    )

    role = str(session.get("role") or "member").strip().lower()

    is_system_admin = bool(session.get("is_system_admin", False)) or role == "system_admin"
    is_app_client_admin = bool(session.get("is_app_client_admin", False)) or role == "app_client_admin"
    is_member = bool(session.get("is_member", False)) or (not is_system_admin and not is_app_client_admin)

    can_manage_catalogs = is_system_admin or is_app_client_admin
    can_view_pos_config = is_system_admin or is_app_client_admin
    can_edit_pos_config = is_system_admin

    return {
        "role": role,
        "is_system_admin": is_system_admin,
        "is_app_client_admin": is_app_client_admin,
        "is_member": is_member,
        "can_manage_catalogs": can_manage_catalogs,
        "can_view_pos_config": can_view_pos_config,
        "can_edit_pos_config": can_edit_pos_config,
    }