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
TEMP_2FA_MINUTES = int(os.getenv("JWT_2FA_TEMP_MINUTES", "5"))


def create_access_token(user_id, email, rol, nombre=""):
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": str(user_id),
        "email": email,
        "rol": rol,
        "nombre": nombre,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRATION_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

    t = payload.get("type")
    if t is not None and t != "access":
        return None

    return payload


def create_temp_token_2fa(user_id, email):
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": str(user_id),
        "email": email,
        "type": "2fa",
        "iat": now,
        "exp": now + timedelta(minutes=TEMP_2FA_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def get_temp_token_2fa_payload(token):
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

    if payload.get("type") != "2fa":
        return None

    return payload


def get_token_from_request():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


def get_current_user_from_request():
    token = get_token_from_request()
    if not token:
        return None
    return decode_access_token(token)