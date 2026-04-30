# auth.py

import os
from typing import Optional

import jwt
from fastapi import Header, HTTPException, Request

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")


def _extract_token(request: Request, authorization: Optional[str] = None) -> Optional[str]:
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1].strip()

    token = request.cookies.get("jwt")
    if token:
        return token.strip()

    return None


def verify_token(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> str:
    token = _extract_token(request, authorization)

    if not token:
        raise HTTPException(status_code=401, detail="Token no proporcionado")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")

        if not username:
            raise HTTPException(status_code=401, detail="Token inválido")

        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")


def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> str:
    return verify_token(request, authorization)