# ================================================================
# app/jwt_utils.py - Utilidades JWT para la API móvil
# ================================================================

import os
import jwt
from datetime import datetime, timedelta, timezone
from flask import request


JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CAMBIAR-ESTO-EN-PRODUCCION")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))


def create_access_token(user_id, email, rol, nombre=""):
    """Genera un JWT firmado con la identidad del usuario."""
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": str(user_id),
        "email": email,
        "rol": rol,
        "nombre": nombre,
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRATION_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token):
    """Verifica un JWT. Devuelve el payload o None."""
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_token_from_request():
    """Extrae el token del header 'Authorization: Bearer <token>'."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


def get_current_user_from_request():
    """Lee el JWT del request actual y devuelve el payload, o None."""
    token = get_token_from_request()
    if not token:
        return None
    return decode_access_token(token)